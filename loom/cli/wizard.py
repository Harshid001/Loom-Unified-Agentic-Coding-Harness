import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import questionary
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from loom.cli.advanced_router import CostOptimizedRouter
from loom.cli.multi_repo import MonorepoScanner
from loom.cli.recovery import RecoveryManager
from loom.repo_intel.mapper import RepoMapper

console = Console()


class InteractiveWizard:
    """Multi-step interactive wizard for guided Loom execution."""

    def __init__(self):
        self.console = Console()
        self._selections: Dict[str, Any] = {}

    def _ask(self, question: str, default: str = "") -> str:
        if HAS_QUESTIONARY:
            result = questionary.text(question, default=default).ask()
            return result if result is not None else default
        return input(f"{question} [{default}]: ") or default

    def _select(self, question: str, choices: List[str], default: Optional[str] = None) -> str:
        if HAS_QUESTIONARY:
            result = questionary.select(question, choices=choices, default=default).ask()
            return result if result is not None else choices[0]
        self.console.print(f"\n{question}")
        for i, c in enumerate(choices, 1):
            self.console.print(f"  {i}. {c}")
        choice = input(f"Select [1-{len(choices)}]: ").strip()
        try:
            idx = int(choice) - 1
            return choices[idx]
        except (ValueError, IndexError):
            return choices[0]

    def _confirm(self, question: str, default: bool = True) -> bool:
        if HAS_QUESTIONARY:
            return questionary.confirm(question, default=default).ask() or False
        default_str = "Y/n" if default else "y/N"
        result = input(f"{question} [{default_str}]: ").strip().lower()
        if not result:
            return default
        return result in ("y", "yes")

    def _checkbox(self, question: str, choices: List[str]) -> List[str]:
        if HAS_QUESTIONARY:
            result = questionary.checkbox(question, choices=choices).ask()
            return result if result else []
        self.console.print(f"\n{question}")
        for i, c in enumerate(choices, 1):
            self.console.print(f"  {i}. {c}")
        selected = input("Select numbers (comma-separated): ").strip()
        try:
            indices = [int(x.strip()) - 1 for x in selected.split(",") if x.strip()]
            return [choices[i] for i in indices if 0 <= i < len(choices)]
        except (ValueError, IndexError):
            return []

    def run(self) -> Dict[str, Any]:
        self.console.clear()
        self.console.rule("[bold magenta]Loom Interactive Wizard[/bold magenta]")
        self.console.print("[dim]Guided setup for autonomous code fixing[/dim]\n")

        self._step_repo()
        self._step_issue()
        self._step_model()
        self._step_routing()
        self._step_options()
        self._step_summary()

        return self._selections

    def _step_repo(self):
        self.console.rule("[cyan]Step 1: Repository[/cyan]")
        repo_path = self._ask("Repository path", default=".")
        repo_path = str(Path(repo_path).resolve())
        self._selections["repo_path"] = repo_path

        if MonorepoScanner.is_monorepo(repo_path):
            self.console.print("[yellow]Monorepo detected![/yellow]")
            config = MonorepoScanner.scan_monorepo(repo_path)

            if config.sub_projects:
                project_names = [sp.name for sp in config.sub_projects]
                selected = self._checkbox("Select sub-projects to process:", project_names)
                self._selections["monorepo_config"] = config
                self._selections["selected_subprojects"] = selected or project_names

                table = Table(title="Build Order")
                table.add_column("Order", style="cyan")
                table.add_column("Project", style="green")
                for i, name in enumerate(config.build_order, 1):
                    table.add_row(str(i), name)
                self.console.print(table)

        mapper = RepoMapper()
        repo_map = mapper.map_repository(repo_path)
        self._selections["repo_map"] = repo_map
        self.console.print(f"[green]Found {repo_map.total_files} files, languages: {list(repo_map.languages.keys())}[/green]")

    def _step_issue(self):
        self.console.rule("[cyan]Step 2: Issue[/cyan]")
        issue = self._ask("Describe the bug or feature to resolve")
        self._selections["issue"] = issue

    def _step_model(self):
        self.console.rule("[cyan]Step 3: Model Selection[/cyan]")
        available = CostOptimizedRouter.available_models()
        model = self._select("Select default model:", available, default=available[0] if available else None)
        self._selections["model"] = model

        mock = self._confirm("Run in mock/offline mode? (no API calls)", default=False)
        self._selections["mock"] = mock

    def _step_routing(self):
        self.console.rule("[cyan]Step 4: Routing Strategy[/cyan]")
        profiles = CostOptimizedRouter.list_profiles()
        profile = self._select("Select routing profile:", profiles, default="balanced")

        router = CostOptimizedRouter(
            default_model=self._selections.get("model", "claude-3-5-sonnet-20241022"),
            profile=profile
        )
        self._selections["routing_profile"] = profile

        table = Table(title=f"Routing Plan: {profile}")
        table.add_column("Agent", style="cyan")
        table.add_column("Model", style="green")
        table.add_column("Est. Cost", style="yellow")
        for agent, model, cost in router.get_routing_table():
            table.add_row(agent, model, f"${cost:.6f}")
        self.console.print(table)

    def _step_options(self):
        self.console.rule("[cyan]Step 5: Execution Options[/cyan]")

        human_loop = self._confirm("Enable human-in-the-loop? (approve each agent step)", default=False)
        self._selections["human_in_the_loop"] = human_loop

        streaming = self._confirm("Enable real-time streaming output?", default=True)
        self._selections["streaming"] = streaming

        resume = self._confirm("Check for resumable failed runs?", default=True)
        self._selections["auto_resume"] = resume

        if resume:
            failed = RecoveryManager.list_failed_runs()
            if failed:
                self.console.print(f"[yellow]{len(failed)} failed runs found[/yellow]")
                choices = [f"{r.run_id} - {r.issue_description[:50]}..." for r in failed[:5]]
                choices.append("Start fresh")
                choice = self._select("Resume a failed run?", choices)
                if choice != "Start fresh":
                    run_id = choice.split(" - ")[0]
                    self._selections["resume_run_id"] = run_id

        parallelism = self._confirm("Enable parallel agent execution where possible?", default=False)
        self._selections["parallel"] = parallelism

        plugins = self._confirm("Load plugins from ~/.loom/plugins/?", default=True)
        self._selections["load_plugins"] = plugins

    def _step_summary(self):
        self.console.rule("[cyan]Summary[/cyan]")
        summary = Panel(
            f"Repository: {self._selections.get('repo_path')}\n"
            f"Issue: {self._selections.get('issue', 'N/A')}\n"
            f"Model: {self._selections.get('model', 'default')}\n"
            f"Profile: {self._selections.get('routing_profile', 'balanced')}\n"
            f"Mock: {self._selections.get('mock', True)}\n"
            f"Human-in-loop: {self._selections.get('human_in_the_loop', False)}\n"
            f"Streaming: {self._selections.get('streaming', True)}\n"
            f"Parallel: {self._selections.get('parallel', False)}\n"
            f"Plugins: {self._selections.get('load_plugins', True)}",
            title="Configuration",
            border_style="green"
        )
        self.console.print(summary)

        if not self._confirm("\nProceed with execution?", default=True):
            self.console.print("[red]Aborted.[/red]")
            sys.exit(0)
