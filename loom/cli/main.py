import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from loom import __version__
from loom.adapters.router import ModelRouter
from loom.cli.advanced_router import CostOptimizedRouter
from loom.cli.human_loop import HumanInTheLoop
from loom.cli.multi_repo import MonorepoScanner
from loom.cli.plugins import HookContext, PluginRegistry
from loom.cli.recovery import RecoveryManager, RunRecord
from loom.cli.streaming import StreamingOutput
from loom.cli.tui import launch_tui
from loom.cli.wizard import InteractiveWizard
from loom.memory.models import MemoryItem, MemoryTier
from loom.memory.store import TieredMemoryStore
from loom.orchestrator.agents import (
    OnboardingAgent,
    PatcherAgent,
    ReproductionAgent,
    ReviewerAgent,
    VerifierAgent,
)
from loom.orchestrator.state import NodeStatus, OrchestratorState
from loom.repo_intel.mapper import RepoMapper
from loom.sandbox.local_process import LocalProcessSandbox
from loom.telemetry.ablation import AblationHarness
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer

app = typer.Typer(
    name="loom",
    help="Loom — Unified Agentic Coding Harness CLI",
    add_completion=False,
    invoke_without_command=True,
)
console = Console()


def _apply_api_key_if_provided(api_key: Optional[str], model: str, api_base: Optional[str] = None):
    if api_base:
        os.environ["API_BASE"] = api_base
        os.environ["OPENAI_API_BASE"] = api_base
    if not api_key:
        return
    m_lower = model.lower()
    if "deepseek" in m_lower:
        os.environ["DEEPSEEK_API_KEY"] = api_key
    if "claude" in m_lower or "anthropic" in m_lower:
        os.environ["ANTHROPIC_API_KEY"] = api_key
    if "gpt" in m_lower or "openai" in m_lower:
        os.environ["OPENAI_API_KEY"] = api_key
    if "gemini" in m_lower:
        os.environ["GEMINI_API_KEY"] = api_key
    if not any(k in m_lower for k in ["deepseek", "claude", "anthropic", "gpt", "openai", "gemini"]):
        os.environ["DEEPSEEK_API_KEY"] = api_key
        os.environ["ANTHROPIC_API_KEY"] = api_key
        os.environ["OPENAI_API_KEY"] = api_key


async def _run_agent_with_hooks(
    agent_cls,
    node_name: str,
    state: OrchestratorState,
    adapter,
    model_name: str,
    human_loop: Optional[HumanInTheLoop],
    streaming: Optional[StreamingOutput],
    tracer: TelemetryTracer,
    cost_tracker: CostTracker,
) -> Dict[str, Any]:
    ctx = HookContext(
        run_id=state.run_id,
        node_name=node_name,
        repo_path=state.repo_path,
        issue_description=state.issue_description,
        state_data=dict(state.shared_data),
    )

    ctx = PluginRegistry.run_pre_hooks(node_name, ctx)
    state.issue_description = ctx.issue_description

    if human_loop:
        choice = human_loop.request_approval(node_name, {"issue_description": state.issue_description})
        if choice == "skip":
            return {"status": "skipped_by_user"}
        elif choice == "retry":
            pass

    agent = agent_cls(name=node_name, adapter=adapter, model_name=model_name)

    if streaming:
        streaming.start_node(node_name, f"Starting {node_name}...")

    output = await agent.execute(state)

    if streaming:
        streaming.complete_node(node_name, True)

    output = PluginRegistry.run_post_hooks(node_name, ctx, output)

    usage_info = output.get("_usage") if isinstance(output, dict) else None
    if usage_info:
        p_tokens = usage_info.get("prompt_tokens", 150)
        c_tokens = usage_info.get("completion_tokens", 50)
        cost = usage_info.get("estimated_cost_usd", 0.0005)
        cost_tracker.add_usage(node_name, p_tokens, c_tokens, cost)
    else:
        cost_tracker.add_usage(node_name, 150, 50, 0.0005)

    return output


async def _execute_task_graph(
    state: OrchestratorState,
    router: ModelRouter,
    advanced_router: Optional[CostOptimizedRouter],
    tracer: TelemetryTracer,
    cost_tracker: CostTracker,
    human_loop: Optional[HumanInTheLoop] = None,
    streaming: Optional[StreamingOutput] = None,
    parallel: bool = False,
    resume_from: Optional[str] = None,
) -> OrchestratorState:
    node_sequence = [
        ("onboarding", OnboardingAgent),
        ("reproduction", ReproductionAgent),
        ("patcher", PatcherAgent),
        ("verifier", VerifierAgent),
        ("reviewer", ReviewerAgent),
    ]

    if resume_from:
        skip = True
        new_sequence = []
        for name, cls in node_sequence:
            if name == resume_from:
                skip = False
            if not skip:
                new_sequence.append((name, cls))
        node_sequence = new_sequence
        console.print(f"[yellow]Resuming from: {resume_from}[/yellow]")

    if parallel:
        parallel_groups: list[list[tuple[str, Any]]] = [
            [("onboarding", OnboardingAgent)],
            [("reproduction", ReproductionAgent), ("patcher", PatcherAgent)],
            [("verifier", VerifierAgent), ("reviewer", ReviewerAgent)],
        ]
        all_completed: list[str] = []
        for group in parallel_groups:
            tasks: list[Any] = []
            for node_name, agent_cls in group:
                model_name = (
                    advanced_router.resolve_model(node_name) if advanced_router else router.resolve_model(node_name)
                )
                adapter = router.get_adapter(node_name)
                status = NodeStatus(node_name=node_name, status="running", started_at=time.time())
                state.nodes[node_name] = status
                state.current_node = node_name
                state.save_checkpoint()
                tracer.log_event("task_start", node_name, {"model": model_name})
                tasks.append(
                    _run_agent_with_hooks(
                        agent_cls, node_name, state, adapter, model_name, human_loop, streaming, tracer, cost_tracker
                    )
                )
                RecoveryManager.mark_node_completed(state.run_id, node_name)

            results: list = await asyncio.gather(*tasks, return_exceptions=True)
            for (node_name, _), result in zip(group, results):
                if isinstance(result, BaseException):
                    console.print(f"[red]{node_name} failed: {result}[/red]")
                    state.nodes[node_name].status = "failed"
                    state.nodes[node_name].error = str(result)
                    RecoveryManager.mark_node_failed(state.run_id, node_name)
                else:
                    state.nodes[node_name].status = "completed"
                    state.nodes[node_name].completed_at = time.time()
                    state.nodes[node_name].output = result if isinstance(result, dict) else {}
                    all_completed.append(node_name)
    else:
        for node_name, agent_cls in node_sequence:
            model_name = (
                advanced_router.resolve_model(node_name) if advanced_router else router.resolve_model(node_name)
            )
            adapter = router.get_adapter(node_name)
            status = NodeStatus(node_name=node_name, status="running", started_at=time.time())
            state.nodes[node_name] = status
            state.current_node = node_name
            state.save_checkpoint()
            tracer.log_event("task_start", node_name, {"model": model_name})

            try:
                output = await _run_agent_with_hooks(
                    agent_cls, node_name, state, adapter, model_name, human_loop, streaming, tracer, cost_tracker
                )
                status.status = "completed"
                status.completed_at = time.time()
                status.output = output
                tracer.log_event("task_completed", node_name, output)
                RecoveryManager.mark_node_completed(state.run_id, node_name)
            except Exception as e:
                console.print(f"[red]Agent {node_name} failed: {e}[/red]")
                status.status = "failed"
                status.completed_at = time.time()
                status.error = str(e)
                tracer.log_event("task_failed", node_name, {"error": str(e)})
                RecoveryManager.mark_node_failed(state.run_id, node_name)

                fallback = RecoveryManager.should_retry_with_fallback(state.run_id, node_name)
                if fallback:
                    console.print(f"[yellow]Retrying {node_name} with fallback model: {fallback}[/yellow]")
                    try:
                        output = await _run_agent_with_hooks(
                            agent_cls, node_name, state, adapter, fallback, human_loop, streaming, tracer, cost_tracker
                        )
                        status.status = "completed"
                        status.completed_at = time.time()
                        status.output = output
                        RecoveryManager.mark_node_completed(state.run_id, node_name)
                        continue
                    except Exception:
                        pass
                break

            state.save_checkpoint()

    state.shared_data["cost_report"] = cost_tracker.get_summary()
    state.save_checkpoint()
    return state


async def _run_monorepo(
    config,
    selected_subprojects: List[str],
    issue: str,
    mock: bool,
    model: str,
    advanced_router: CostOptimizedRouter,
    human_loop: Optional[HumanInTheLoop],
    streaming: Optional[StreamingOutput],
    parallel: bool,
):
    results = {}
    for sp_name in config.build_order:
        if sp_name not in selected_subprojects:
            continue

        sp = next((s for s in config.sub_projects if s.name == sp_name), None)
        if not sp:
            continue

        console.print(f"\n[bold cyan]Processing sub-project: {sp_name}[/bold cyan]")
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        state = OrchestratorState(run_id=run_id, repo_path=sp.path, issue_description=issue)
        router = ModelRouter(default_model=model, mock_mode=mock)
        tracer = TelemetryTracer(run_id=run_id)
        cost_tracker = CostTracker(run_id=run_id)
        record = RunRecord(run_id=run_id, repo_path=sp.path, issue_description=issue, model_used=model)
        RecoveryManager.save_run(record)

        final_state = await _execute_task_graph(
            state, router, advanced_router, tracer, cost_tracker, human_loop, streaming, parallel
        )
        results[sp_name] = final_state

    return results


@app.command()
def version():
    """Show Loom version."""
    console.print(f"[bold cyan]Loom CLI[/bold cyan] v{__version__}")


@app.command()
def init(repo_path: str = typer.Option(".", "--path", "-p", help="Path to repository root")):
    """Intake repository, build file map, AST symbol index, and memory store."""
    path = Path(repo_path).resolve()
    console.print(f"[bold blue]Intaking repository at:[/bold blue] {path}")

    mapper = RepoMapper()
    repo_map = mapper.map_repository(str(path))

    store = TieredMemoryStore()
    store.add(
        MemoryItem(
            tier=MemoryTier.PROJECT_CONVENTIONS,
            content=f"Build systems: {', '.join(repo_map.build_system)}; Test frameworks: {', '.join(repo_map.test_frameworks)}",
            source="loom_init",
        )
    )

    table = Table(title="Repository Intelligence Map")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total Files", str(repo_map.total_files))
    table.add_row("Languages", ", ".join(f"{k}: {v}" for k, v in repo_map.languages.items()))
    table.add_row("Build Systems", ", ".join(repo_map.build_system) or "None detected")
    table.add_row("Test Frameworks", ", ".join(repo_map.test_frameworks) or "None detected")
    console.print(table)

    if MonorepoScanner.is_monorepo(str(path)):
        console.print("[yellow]Monorepo detected![/yellow]")
        config = MonorepoScanner.scan_monorepo(str(path))
        sub_table = Table(title="Sub-Projects")
        sub_table.add_column("Project", style="cyan")
        sub_table.add_column("Build", style="green")
        sub_table.add_column("Dependencies", style="yellow")
        for sp in config.sub_projects:
            sub_table.add_row(sp.name, sp.build_system, ", ".join(sp.depends_on) or "-")
        console.print(sub_table)
        console.print(f"Build order: [cyan]{' → '.join(config.build_order)}[/cyan]")

    console.print("[bold green]Repository successfully intaken and mapped![/bold green]")


@app.command()
def wizard():
    """Launch interactive multi-step setup wizard for guided execution."""
    wiz = InteractiveWizard()
    selections = wiz.run()

    _apply_api_key_if_provided(None, selections.get("model", "claude-3-5-sonnet-20241022"))

    if selections.get("load_plugins", True):
        PluginRegistry.discover_plugins()

    router = ModelRouter(default_model=selections["model"], mock_mode=selections.get("mock", True))
    advanced_router = CostOptimizedRouter(
        default_model=selections["model"], profile=selections.get("routing_profile", "balanced")
    )
    human_loop = HumanInTheLoop() if selections.get("human_in_the_loop") else None
    streaming = StreamingOutput(console) if selections.get("streaming") else None

    issue = selections["issue"]
    repo_path = selections["repo_path"]
    mock = selections.get("mock", True)
    parallel = selections.get("parallel", False)

    run_id = selections.get("resume_run_id")

    if selections.get("monorepo_config") and selections.get("selected_subprojects"):
        if streaming is not None and console.is_terminal:
            with Live(streaming.render_context(), console=console, refresh_per_second=10):
                results = asyncio.run(
                    _run_monorepo(
                        selections["monorepo_config"],
                        selections["selected_subprojects"],
                        issue,
                        mock,
                        selections["model"],
                        advanced_router,
                        human_loop,
                        streaming,
                        parallel,
                    )
                )
        else:
            results = asyncio.run(
                _run_monorepo(
                    selections["monorepo_config"],
                    selections["selected_subprojects"],
                    issue,
                    mock,
                    selections["model"],
                    advanced_router,
                    human_loop,
                    streaming,
                    parallel,
                )
            )
        _print_monorepo_summary(results)
        return

    if run_id and RecoveryManager.can_resume(run_id):
        resume_from = RecoveryManager.get_resume_point(run_id)
        record = RecoveryManager.load_run(run_id)
        state = OrchestratorState.load_checkpoint(run_id)
        if state and record:
            console.print(f"[yellow]Resuming run {run_id} from {resume_from}[/yellow]")
            tracer = TelemetryTracer(run_id=run_id)
            cost_tracker = CostTracker(run_id=run_id)
            final_state = asyncio.run(
                _execute_task_graph(
                    state, router, advanced_router, tracer, cost_tracker, human_loop, streaming, parallel, resume_from
                )
            )
            _print_run_summary(final_state, run_id)
            return

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    state = OrchestratorState(run_id=run_id, repo_path=repo_path, issue_description=issue)
    state.shared_data["mock_mode"] = mock
    tracer = TelemetryTracer(run_id=run_id)
    cost_tracker = CostTracker(run_id=run_id)
    record = RunRecord(run_id=run_id, repo_path=repo_path, issue_description=issue, model_used=selections["model"])
    RecoveryManager.save_run(record)

    if streaming is not None and console.is_terminal:
        with Live(streaming.render_context(), console=console, refresh_per_second=10):
            final_state = asyncio.run(
                _execute_task_graph(
                    state, router, advanced_router, tracer, cost_tracker, human_loop, streaming, parallel
                )
            )
    else:
        final_state = asyncio.run(
            _execute_task_graph(state, router, advanced_router, tracer, cost_tracker, human_loop, streaming, parallel)
        )

    _print_run_summary(final_state, run_id)


@app.command()
def fix(
    description: str = typer.Argument(None, help="Issue or feature description to resolve in 1 step"),
    repo_path: str = typer.Option(".", "--path", "-p", help="Path to repository root"),
    mock: bool = typer.Option(True, "--mock/--no-mock", help="Run in mock/offline mode"),
    model: str = typer.Option("claude-3-5-sonnet-20241022", "--model", "-m", help="Default model for task routing"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="Pass API key directly in terminal command"),
    api_base: Optional[str] = typer.Option(None, "--api-base", "-b", help="Pass custom LLM provider API base URL"),
    profile: str = typer.Option(
        "balanced", "--profile", help="Routing profile: balanced, minimal_cost, max_quality, hybrid"
    ),
    human: bool = typer.Option(False, "--human/--no-human", help="Enable human-in-the-loop approval"),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="Enable real-time streaming output"),
    parallel: bool = typer.Option(False, "--parallel", help="Enable parallel agent execution where possible"),
    plugins: bool = typer.Option(True, "--plugins/--no-plugins", help="Load plugins from ~/.loom/plugins/"),
    resume: Optional[str] = typer.Option(None, "--resume", help="Resume a failed run by run ID"),
):
    """Single-command solution: Intakes repo, sets issue, and executes Loom harness in 1 shot!"""
    if not description:
        description = typer.prompt("What bug or feature should Loom resolve on this project?")

    _apply_api_key_if_provided(api_key, model, api_base)

    if plugins:
        PluginRegistry.discover_plugins()

    init(repo_path=repo_path)
    issue(description=description, repo_path=repo_path)
    run(
        mock=mock,
        model=model,
        api_key=api_key,
        api_base=api_base,
        profile=profile,
        human=human,
        stream=stream,
        parallel=parallel,
        resume=resume,
    )


@app.command()
def issue(
    description: str = typer.Argument(..., help="Issue or feature description to resolve"),
    repo_path: str = typer.Option(".", "--path", "-p", help="Path to repository root"),
):
    """Set active issue description for harness execution."""
    issue_file = Path.home() / ".loom" / "active_issue.json"
    issue_file.parent.mkdir(parents=True, exist_ok=True)
    data = {"description": description, "repo_path": str(Path(repo_path).resolve())}
    issue_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    console.print(Panel(f"[bold yellow]Active Issue Set:[/bold yellow]\n{description}", title="Loom Task Graph"))


@app.command()
def run(
    mock: bool = typer.Option(True, "--mock/--no-mock", help="Run in mock/offline mode without calling paid API keys"),
    model: str = typer.Option("claude-3-5-sonnet-20241022", "--model", "-m", help="Default model for task routing"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="Pass API key directly in terminal command"),
    api_base: Optional[str] = typer.Option(None, "--api-base", "-b", help="Pass custom LLM provider API base URL"),
    profile: str = typer.Option(
        "balanced", "--profile", help="Routing profile: balanced, minimal_cost, max_quality, hybrid"
    ),
    human: bool = typer.Option(False, "--human/--no-human", help="Enable human-in-the-loop approval"),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="Enable real-time streaming output"),
    parallel: bool = typer.Option(False, "--parallel", help="Enable parallel agent execution where possible"),
    resume: Optional[str] = typer.Option(None, "--resume", help="Resume a failed run by run ID"),
):
    """Execute the task graph through onboarding, reproduction, patching, verification, and reviewer report."""
    _apply_api_key_if_provided(api_key, model, api_base)

    if resume and RecoveryManager.can_resume(resume):
        record = RecoveryManager.load_run(resume)
        state = OrchestratorState.load_checkpoint(resume)
        resume_point = RecoveryManager.get_resume_point(resume)
        if state and record and resume_point:
            console.print(f"[yellow]Resuming run {resume} from agent: {resume_point}[/yellow]")
            router = ModelRouter(default_model=record.model_used, mock_mode=mock)
            advanced_router = CostOptimizedRouter(default_model=record.model_used, profile=profile)
            tracer = TelemetryTracer(run_id=resume)
            cost_tracker = CostTracker(run_id=resume)
            human_loop = HumanInTheLoop() if human else None
            streaming = StreamingOutput(console) if stream else None

            if streaming is not None and console.is_terminal:
                with Live(streaming.render_context(), console=console, refresh_per_second=10):
                    final_state = asyncio.run(
                        _execute_task_graph(
                            state,
                            router,
                            advanced_router,
                            tracer,
                            cost_tracker,
                            human_loop,
                            streaming,
                            parallel,
                            resume_point,
                        )
                    )
            else:
                final_state = asyncio.run(
                    _execute_task_graph(
                        state,
                        router,
                        advanced_router,
                        tracer,
                        cost_tracker,
                        human_loop,
                        streaming,
                        parallel,
                        resume_point,
                    )
                )
            _print_run_summary(final_state, resume)
            return

    issue_file = Path.home() / ".loom" / "active_issue.json"
    if not issue_file.exists():
        console.print("[bold red]No active issue set. Run 'loom issue \"<description>\"' first.[/bold red]")
        raise typer.Exit(1)

    issue_data = json.loads(issue_file.read_text(encoding="utf-8"))
    stored_path = issue_data.get("repo_path")
    if stored_path and Path(stored_path).exists() and Path(stored_path).is_dir():
        repo_path = str(Path(stored_path).resolve())
    else:
        repo_path = str(Path.cwd().resolve())

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    console.print(f"[bold magenta]Starting Loom Harness Execution (Run ID: {run_id})[/bold magenta]")

    state = OrchestratorState(
        run_id=run_id, repo_path=repo_path, issue_description=issue_data.get("description", "Unspecified issue")
    )
    state.shared_data["mock_mode"] = mock

    router = ModelRouter(default_model=model, mock_mode=mock)
    advanced_router = CostOptimizedRouter(default_model=model, profile=profile)
    tracer = TelemetryTracer(run_id=run_id)
    cost_tracker = CostTracker(run_id=run_id)
    human_loop = HumanInTheLoop() if human else None
    streaming = StreamingOutput(console) if stream else None

    record = RunRecord(run_id=run_id, repo_path=repo_path, issue_description=state.issue_description, model_used=model)
    RecoveryManager.save_run(record)

    if stream and streaming is not None and console.is_terminal:
        with Live(streaming.render_context(), console=console, refresh_per_second=10):
            final_state = asyncio.run(
                _execute_task_graph(
                    state, router, advanced_router, tracer, cost_tracker, human_loop, streaming, parallel
                )
            )
    else:
        final_state = asyncio.run(
            _execute_task_graph(state, router, advanced_router, tracer, cost_tracker, human_loop, streaming, parallel)
        )

    _print_run_summary(final_state, run_id)


def _print_run_summary(final_state: OrchestratorState, run_id: str):
    report = final_state.shared_data.get("reviewer_report", {})
    status_str = (
        "[bold green]VERIFIED SUCCESS[/bold green]"
        if final_state.verification_passed
        else "[bold red]FAILED[/bold red]"
    )

    console.print("\n" + "=" * 50)
    console.print(f"Loom Harness Execution Complete: {status_str}")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")
    if report:
        console.print(f"Reviewer Verdict: [magenta]{report.get('verdict', 'N/A')}[/magenta]")
    console.print(f"Rollback Command: [yellow]loom rollback {run_id}[/yellow]")
    cost = final_state.shared_data.get("cost_report", {}).get("total_cost_usd", 0.0)
    console.print(f"Cost Report: ${cost}")

    node_table = Table(title="Agent Execution Details")
    node_table.add_column("Agent", style="cyan")
    node_table.add_column("Status", style="green")
    for name, ns in final_state.nodes.items():
        node_table.add_row(name, ns.status)
    console.print(node_table)
    console.print("=" * 50)

    RecoveryManager.mark_run_completed(run_id, final_state.verification_passed)


def _print_monorepo_summary(results: Dict[str, OrchestratorState]):
    console.print("\n" + "=" * 50)
    console.print("[bold magenta]Monorepo Execution Complete[/bold magenta]")
    table = Table(title="Sub-Project Results")
    table.add_column("Project", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Cost", style="yellow")
    for name, state in results.items():
        status = "[green]PASSED" if state.verification_passed else "[red]FAILED"
        cost = state.shared_data.get("cost_report", {}).get("total_cost_usd", 0.0)
        table.add_row(name, status, f"${cost}")
    console.print(table)
    console.print("=" * 50)


@app.command()
def trace(run_id: str = typer.Argument(..., help="Run ID to view trace events for")):
    """Inspect execution trace logs, DAG node events, and evidence for a run."""
    trace_file = Path.home() / ".loom" / "traces" / f"trace_{run_id}.json"
    if not trace_file.exists():
        console.print(f"[bold red]Trace file not found for run ID: {run_id}[/bold red]")
        raise typer.Exit(1)

    events = json.loads(trace_file.read_text(encoding="utf-8"))
    tree = Tree(f"[bold magenta]Execution Trace (Run: {run_id})[/bold magenta]")
    for ev in events:
        tree.add(
            f"[cyan]{ev.get('event_type')}[/cyan] @ [yellow]{ev.get('node_name')}[/yellow] - {json.dumps(ev.get('data'))}"
        )
    console.print(tree)

    record = RecoveryManager.load_run(run_id)
    if record:
        console.print(f"\nRun Status: [bold]{record.status}[/bold]")
        console.print(f"Completed Nodes: {record.completed_nodes}")
        console.print(f"Retries: {record.retry_count}")
        if record.fallback_models:
            console.print(f"Fallback models used: {record.fallback_models}")


@app.command()
def rollback(run_id: str = typer.Argument(..., help="Run ID to revert workspace changes for")):
    """Roll back repository workspace to snapshot before patch application."""
    checkpoint_file = Path.home() / ".loom" / "checkpoints" / f"checkpoint_{run_id}.json"
    if not checkpoint_file.exists():
        console.print(f"[bold red]Checkpoint file not found for run ID: {run_id}[/bold red]")
        raise typer.Exit(1)

    data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    repo_path = data.get("repo_path")
    snapshot_id = data.get("snapshot_id")
    if not snapshot_id or not repo_path:
        console.print("[bold red]No valid snapshot found to rollback.[/bold red]")
        raise typer.Exit(1)

    sandbox = LocalProcessSandbox(repo_path)
    success = sandbox.restore_snapshot(snapshot_id)
    if success:
        console.print(f"[bold green]Successfully rolled back workspace to snapshot {snapshot_id}[/bold green]")
    else:
        console.print(f"[bold red]Failed to restore snapshot {snapshot_id}[/bold red]")


@app.command()
def resume_run(
    run_id: Optional[str] = typer.Argument(None, help="Run ID to resume. If omitted, lists all failed runs."),
):
    """Resume a failed or interrupted run from its last checkpoint."""
    if not run_id:
        failed = RecoveryManager.list_failed_runs()
        if not failed:
            console.print("[green]No failed runs found.[/green]")
            return
        table = Table(title="Failed/Interrupted Runs")
        table.add_column("Run ID", style="cyan")
        table.add_column("Issue", style="yellow")
        table.add_column("Failed At", style="red")
        table.add_column("Retries", style="magenta")
        for r in failed:
            table.add_row(r.run_id, r.issue_description[:60], r.failed_node or "unknown", str(r.retry_count))
        console.print(table)
        console.print("\n[dim]Use 'loom resume-run <run_id>' to resume a specific run.[/dim]")
        return

    if not RecoveryManager.can_resume(run_id):
        console.print(
            f"[red]Run {run_id} cannot be resumed (not found, already completed, or max retries exceeded).[/red]"
        )
        return

    record = RecoveryManager.load_run(run_id)
    state = OrchestratorState.load_checkpoint(run_id)
    if not state or not record:
        console.print(f"[red]Cannot load state for run {run_id}.[/red]")
        return

    resume_point = RecoveryManager.get_resume_point(run_id)
    console.print(f"[yellow]Resuming run {run_id} from agent: {resume_point}[/yellow]")

    router = ModelRouter(default_model=record.model_used, mock_mode=True)
    advanced_router = CostOptimizedRouter(default_model=record.model_used)
    tracer = TelemetryTracer(run_id=run_id)
    cost_tracker = CostTracker(run_id=run_id)

    final_state = asyncio.run(
        _execute_task_graph(state, router, advanced_router, tracer, cost_tracker, resume_from=resume_point)
    )
    _print_run_summary(final_state, run_id)


@app.command()
def plugins():
    """List loaded plugins and their hooks."""
    PluginRegistry.discover_plugins()
    manifests = PluginRegistry.list_plugins()
    if not manifests:
        console.print("[yellow]No plugins found in ~/.loom/plugins/[/yellow]")
        console.print("[dim]Create Python files or packages with PLUGIN_MANIFEST dict to add plugins.[/dim]")
        return

    for m in manifests:
        console.print(
            Panel(
                f"Version: {m.version}\n"
                f"Author: {m.author}\n"
                f"Description: {m.description}\n"
                f"Hooks: {', '.join(m.hooks) if m.hooks else 'none'}\n"
                f"Custom Agents: {', '.join(m.custom_agents) if m.custom_agents else 'none'}",
                title=f"[cyan]{m.name}[/cyan]",
                border_style="green",
            )
        )


@app.command()
def routes(
    profile: str = typer.Option("balanced", "--profile", help="Routing profile to display"),
):
    """Display model routing configuration and cost estimates."""
    router = CostOptimizedRouter(profile=profile)
    table = Table(title=f"Model Routing: {profile}")
    table.add_column("Agent", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Est. Cost", style="yellow")
    for agent, model, cost in router.get_routing_table():
        table.add_row(agent, model, f"${cost:.6f}")
    console.print(table)

    profiles_table = Table(title="Available Profiles")
    profiles_table.add_column("Profile", style="cyan")
    profiles_table.add_column("Description", style="green")
    for name, p in CostOptimizedRouter.PRESETS.items():
        profiles_table.add_row(name, p.description)
    console.print(profiles_table)


@app.command()
def bench():
    """Execute ablation benchmark comparison suite (Baseline vs. Loom)."""
    harness = AblationHarness()
    matrix = harness.get_ablation_matrix()

    table = Table(title="Controlled Ablation Matrix Benchmark (Same Model, Same Budget)")
    table.add_column("Variant Name", style="cyan")
    table.add_column("Memory", style="green")
    table.add_column("Context Ranking", style="green")
    table.add_column("Multi-Agent", style="green")
    table.add_column("Verification", style="green")

    for item in matrix:
        cfg = item["config"]
        table.add_row(
            item["name"],
            "ON" if cfg["memory_enabled"] else "OFF",
            "ON" if cfg["context_ranking_enabled"] else "OFF",
            "ON" if cfg["multi_agent_enabled"] else "OFF",
            "ON" if cfg["verification_enabled"] else "OFF",
        )

    console.print(table)
    console.print("[bold green]Ablation matrix initialized successfully.[/bold green]")


@app.command()
def tui():
    """Launch the Textual TUI dashboard."""
    launch_tui()


@app.command()
def server(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address"),
    port: int = typer.Option(8000, "--port", "-p", help="Port number"),
):
    """Start Loom API Backend Server connecting Web UI & Terminal."""
    import uvicorn

    console.print(f"[bold magenta]Starting Loom API Server on http://{host}:{port}[/bold magenta]")
    uvicorn.run("loom.api.server:app", host=host, port=port, reload=False)


@app.command()
def browser(
    url: str = typer.Option("http://localhost:3000", "--url", "-u", help="URL to navigate and verify"),
    headed: bool = typer.Option(False, "--headed", help="Open visible Chromium browser window on desktop screen"),
    open_sys: bool = typer.Option(False, "--open", "-o", help="Open default system browser directly"),
    screenshot: str = typer.Option(
        "artifacts/screenshots/page.png", "--screenshot", "-s", help="Output screenshot path"
    ),
):
    """Launch Loom Browser subagent to navigate, capture screenshots, and perform E2E web verification."""
    import webbrowser

    if open_sys:
        console.print(f"[bold cyan]Opening system browser directly to:[/bold cyan] {url}")
        webbrowser.open(url)
        return

    from loom.sandbox.browser import LoomBrowserRunner

    async def _run():
        headless_mode = not headed
        mode_str = "VISIBLE Desktop Window" if headed else "Headless Mode"
        console.print(f"[bold cyan]Launching Loom Browser Agent ({mode_str}) to:[/bold cyan] {url}")
        runner = LoomBrowserRunner(headless=headless_mode)
        try:
            res = await runner.navigate(url)
            console.print(f"[bold green]Connected![/bold green] Status: {res['status']} | Title: '{res['title']}'")
            file_path = await runner.take_screenshot(screenshot)
            console.print(f"[bold yellow]Screenshot saved to:[/bold yellow] [underline]{file_path}[/underline]")
            if headed:
                console.print("[dim]Browser window is open on your screen. Press Enter in terminal to close...[/dim]")
                input()
            await runner.close()
        except Exception as err:
            console.print(f"[bold red]Browser error:[/bold red] {err}")
            await runner.close()

    asyncio.run(_run())


@app.command(name="token-create")
def create_token(
    user_id: str = typer.Option("dev_user", "--user-id", "-u", help="User ID for the API key"),
    label: str = typer.Option("cli_key", "--label", "-l", help="Label description for the API key"),
    org_id: str = typer.Option("default", "--org-id", "-o", help="Organization ID"),
):
    """Generate and issue a new Loom API key."""
    from loom.auth.api_tokens import get_api_token_store

    store = get_api_token_store()
    record, raw_token = store.issue(user_id=user_id, org_id=org_id, label=label)

    table = Table(title="Loom API Key Generated")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Token Secret", f"[bold yellow]{raw_token}[/bold yellow]")
    table.add_row("Token ID", record.id)
    table.add_row("User ID", record.user_id)
    table.add_row("Org ID", record.org_id)
    table.add_row("Label", record.label)
    table.add_row("Prefix", record.prefix)
    console.print(table)
    console.print("[dim]Copy this token secret now — it will not be shown again.[/dim]")


@app.command(name="token-list")
def list_tokens(
    user_id: Optional[str] = typer.Option(None, "--user-id", "-u", help="Filter by User ID"),
):
    """List active API keys."""
    from loom.auth.api_tokens import get_api_token_store

    store = get_api_token_store()
    records = store.list_active(user_id=user_id)

    if not records:
        console.print("[yellow]No active API keys found.[/yellow]")
        return

    table = Table(title="Active Loom API Keys")
    table.add_column("ID", style="cyan")
    table.add_column("Label", style="green")
    table.add_column("User ID", style="magenta")
    table.add_column("Prefix", style="yellow")
    table.add_column("Created At", style="dim")

    for r in records:
        table.add_row(r.id, r.label, r.user_id, f"{r.prefix}...", str(r.created_at))

    console.print(table)


@app.command(name="token-revoke")
def revoke_token(
    token_id: str = typer.Argument(..., help="ID of the token to revoke"),
):
    """Revoke an existing API key."""
    from loom.auth.api_tokens import get_api_token_store

    store = get_api_token_store()
    success = store.revoke(token_id)
    if success:
        console.print(f"[bold green]Successfully revoked API key {token_id}.[/bold green]")
    else:
        console.print(f"[bold red]Token {token_id} not found or already revoked.[/bold red]")


@app.callback(invoke_without_command=True)

def default_callback(ctx: typer.Context):
    """Launch the TUI dashboard when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        launch_tui()


if __name__ == "__main__":
    app()
