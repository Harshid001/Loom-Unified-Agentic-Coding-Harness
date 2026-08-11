import sys
from typing import Any, Dict, Optional

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


class HumanInTheLoop:
    """Pauses execution at each agent step for human review and approval."""

    def __init__(self, console: Optional[Console] = None, auto_approve: bool = False):
        self.console = console or Console()
        self.auto_approve = auto_approve
        self.approved_nodes: set = set()

    def request_approval(self, node_name: str, context: Dict[str, Any], output: Optional[Dict[str, Any]] = None) -> str:
        if self.auto_approve:
            return "approve"

        self.console.clear()
        self.console.rule(f"[bold cyan]Agent: {node_name}[/bold cyan]")

        if context:
            self.console.print(
                Panel(str(context.get("issue_description", "No issue")), title="Issue", border_style="yellow")
            )

        if output:
            self._display_output(output)

        options = Text()
        options.append("\n[A]pprove  ", style="bold green")
        options.append("[S]kip  ", style="bold yellow")
        options.append("[R]etry  ", style="bold blue")
        options.append("[Q]uit  ", style="bold red")
        options.append("[C]ontinue without further prompts", style="dim")
        self.console.print(options)

        while True:
            try:
                choice = input("\n> ").strip().lower()
                if choice in ("a", "approve"):
                    self.approved_nodes.add(node_name)
                    return "approve"
                elif choice in ("s", "skip"):
                    return "skip"
                elif choice in ("r", "retry"):
                    return "retry"
                elif choice in ("q", "quit"):
                    sys.exit(0)
                elif choice in ("c", "continue"):
                    self.auto_approve = True
                    return "approve"
                else:
                    self.console.print("[red]Invalid choice. Use A/S/R/Q/C[/red]")
            except (KeyboardInterrupt, EOFError):
                sys.exit(0)

    def _display_output(self, output: Dict[str, Any]):
        for key, value in output.items():
            if key.startswith("_"):
                continue

            if key in ("patch_diff", "test_script") and isinstance(value, str) and value:
                try:
                    lang = "diff" if key == "patch_diff" else "python"
                    self.console.print(Syntax(value, lang, theme="monokai", line_numbers=False))
                except Exception:
                    self.console.print(str(value)[:500])
            elif isinstance(value, dict):
                self.console.print(
                    Panel(
                        "\n".join(f"{k}: {v}" for k, v in value.items()),
                        title=key.replace("_", " ").title(),
                        border_style="green",
                    )
                )
            elif isinstance(value, list):
                self.console.print(f"[bold]{key}:[/bold] {', '.join(str(v) for v in value)}")
            elif isinstance(value, bool):
                status = "[green]PASSED" if value else "[red]FAILED"
                self.console.print(f"[bold]{key}:[/bold] {status}")
            else:
                self.console.print(f"[bold]{key}:[/bold] {value}")
