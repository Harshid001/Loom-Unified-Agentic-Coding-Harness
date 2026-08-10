import asyncio
import json
import uuid
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from loom import __version__
from loom.adapters.router import ModelRouter
from loom.memory.models import MemoryItem, MemoryTier
from loom.memory.store import TieredMemoryStore
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import TaskGraph
from loom.repo_intel.mapper import RepoMapper
from loom.sandbox.local_process import LocalProcessSandbox
from loom.telemetry.ablation import AblationHarness
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer

app = typer.Typer(
    name="loom",
    help="Loom — Unified Agentic Coding Harness CLI",
    add_completion=False
)
console = Console()

@app.command()
def version():
    """Show Loom version."""
    console.print(f"[bold cyan]Loom CLI[/bold cyan] v{__version__}")

@app.command()
def init(
    repo_path: str = typer.Option(".", "--path", "-p", help="Path to repository root")
):
    """Intake repository, build file map, AST symbol index, and memory store."""
    path = Path(repo_path).resolve()
    console.print(f"[bold blue]Intaking repository at:[bold blue] {path}")

    mapper = RepoMapper()
    repo_map = mapper.map_repository(str(path))

    store = TieredMemoryStore()
    store.add(MemoryItem(
        tier=MemoryTier.PROJECT_CONVENTIONS,
        content=f"Build systems: {', '.join(repo_map.build_system)}; Test frameworks: {', '.join(repo_map.test_frameworks)}",
        source="loom_init"
    ))

    table = Table(title="Repository Intelligence Map")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Files", str(repo_map.total_files))
    table.add_row("Languages", ", ".join(f"{k}: {v}" for k, v in repo_map.languages.items()))
    table.add_row("Build Systems", ", ".join(repo_map.build_system) or "None detected")
    table.add_row("Test Frameworks", ", ".join(repo_map.test_frameworks) or "None detected")

    console.print(table)
    console.print("[bold green]Repository successfully intaken and mapped![/bold green]")

@app.command()
def fix(
    description: str = typer.Argument(None, help="Issue or feature description to resolve in 1 step"),
    repo_path: str = typer.Option(".", "--path", "-p", help="Path to repository root"),
    mock: bool = typer.Option(True, "--mock/--no-mock", help="Run in mock/offline mode"),
    model: str = typer.Option("claude-3-5-sonnet-20241022", "--model", "-m", help="Default model for task routing")
):
    """Single-command solution: Intakes repo, sets issue, and executes Loom harness in 1 shot!"""
    if not description:
        description = typer.prompt("What bug or feature should Loom resolve on this project?")

    init(repo_path=repo_path)
    issue(description=description, repo_path=repo_path)
    run(mock=mock, model=model)


@app.command()
def issue(
    description: str = typer.Argument(..., help="Issue or feature description to resolve"),
    repo_path: str = typer.Option(".", "--path", "-p", help="Path to repository root")
):
    """Set active issue description for harness execution."""
    issue_file = Path.home() / ".loom" / "active_issue.json"
    issue_file.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "description": description,
        "repo_path": str(Path(repo_path).resolve())
    }
    issue_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    console.print(Panel(f"[bold yellow]Active Issue Set:[/bold yellow]\n{description}", title="Loom Task Graph"))

@app.command()
def run(
    mock: bool = typer.Option(True, "--mock/--no-mock", help="Run in mock/offline mode without calling paid API keys"),
    model: str = typer.Option("claude-3-5-sonnet-20241022", "--model", "-m", help="Default model for task routing")
):
    """Execute the task graph through onboarding, reproduction, patching, verification, and reviewer report."""
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
        run_id=run_id,
        repo_path=repo_path,
        issue_description=issue_data.get("description", "Unspecified issue")
    )

    router = ModelRouter(default_model=model, mock_mode=mock)
    tracer = TelemetryTracer(run_id=run_id)
    cost_tracker = CostTracker(run_id=run_id)

    task_graph = TaskGraph(state, router, tracer, cost_tracker)
    final_state = asyncio.run(task_graph.run())

    # Print summary
    report = final_state.shared_data.get("reviewer_report", {})
    status_str = "[bold green]VERIFIED SUCCESS[/bold green]" if final_state.verification_passed else "[bold red]FAILED[/bold red]"

    console.print("\n" + "="*50)
    console.print(f"Loom Harness Execution Complete: {status_str}")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")
    if report:
        console.print(f"Reviewer Verdict: [magenta]{report.get('verdict', 'N/A')}[/magenta]")
    console.print(f"Rollback Command: [yellow]loom rollback {run_id}[/yellow]")
    console.print(f"Cost Report: ${final_state.shared_data.get('cost_report', {}).get('total_cost_usd', 0.0)}")
    console.print("="*50)

@app.command()
def trace(
    run_id: str = typer.Argument(..., help="Run ID to view trace events for")
):
    """Inspect execution trace logs, DAG node events, and evidence for a run."""
    trace_file = Path.home() / ".loom" / "traces" / f"trace_{run_id}.json"
    if not trace_file.exists():
        console.print(f"[bold red]Trace file not found for run ID: {run_id}[/bold red]")
        raise typer.Exit(1)

    events = json.loads(trace_file.read_text(encoding="utf-8"))

    tree = Tree(f"[bold magenta]Execution Trace (Run: {run_id})[/bold magenta]")
    for ev in events:
        tree.add(f"[cyan]{ev.get('event_type')}[/cyan] @ [yellow]{ev.get('node_name')}[/yellow] - {json.dumps(ev.get('data'))}")

    console.print(tree)

@app.command()
def rollback(
    run_id: str = typer.Argument(..., help="Run ID to revert workspace changes for")
):
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
            "ON" if cfg["verification_enabled"] else "OFF"
        )

    console.print(table)
    console.print("[bold green]Ablation matrix initialized successfully.[/bold green]")

@app.command()
def server(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address"),
    port: int = typer.Option(8000, "--port", "-p", help="Port number")
):
    """Start Loom API Backend Server connecting Web UI & Terminal."""
    import uvicorn
    console.print(f"[bold magenta]Starting Loom API Server on http://{host}:{port}[/bold magenta]")
    uvicorn.run("loom.api.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
