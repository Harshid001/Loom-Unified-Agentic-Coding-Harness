import time
from typing import Any, AsyncIterator, Dict, Optional

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table


class StreamingOutput:
    """Real-time streaming output for agent execution with live progress display."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
        )
        self._tasks: Dict[str, Any] = {}

    def start_node(self, node_name: str, description: str = ""):
        task_id = self.progress.add_task(
            f"[cyan]{node_name}[/cyan] {description}",
            total=100
        )
        self._tasks[node_name] = task_id
        return task_id

    def update_node(self, node_name: str, advance: int = 0, description: str = ""):
        if node_name in self._tasks:
            desc = f"[cyan]{node_name}[/cyan] {description}" if description else None
            self.progress.update(self._tasks[node_name], advance=advance, description=desc)

    def complete_node(self, node_name: str, success: bool = True):
        if node_name in self._tasks:
            status = "[green]DONE" if success else "[red]FAILED"
            self.progress.update(
                self._tasks[node_name],
                completed=100,
                description=f"[cyan]{node_name}[/cyan] {status}"
            )

    def render_context(self):
        return self.progress

    def stop(self):
        self.progress.stop()

    def print_stream_chunk(self, node_name: str, chunk: str, end: str = ""):
        self.console.print(f"[dim]{node_name}:[/dim] {chunk}", end=end)

    def print_summary_table(self, results: Dict[str, Any]):
        table = Table(title="Execution Summary", show_header=True, header_style="bold magenta")
        table.add_column("Agent", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Tokens", style="yellow")
        table.add_column("Cost", style="red")
        table.add_column("Duration", style="blue")

        for node_name, data in results.items():
            status = data.get("status", "unknown")
            status_style = "[green]OK" if status == "completed" else "[red]FAIL"
            tokens = data.get("tokens", 0)
            cost = data.get("cost_usd", 0)
            duration = data.get("duration", 0)

            table.add_row(
                node_name,
                status_style,
                str(tokens),
                f"${cost:.4f}",
                f"{duration:.1f}s"
            )

        self.console.print(table)


class AsyncStreamProcessor:
    """Processes LLM response streams and yields tokens as they arrive."""

    @staticmethod
    async def stream_tokens(response_stream: Any, node_name: str) -> AsyncIterator[str]:
        try:
            if hasattr(response_stream, "__aiter__"):
                async for chunk in response_stream:
                    if hasattr(chunk, "choices") and chunk.choices:
                        delta = chunk.choices[0].delta
                        content = getattr(delta, "content", None)
                        if content:
                            yield content
            else:
                yield str(response_stream)
        except Exception:
            yield "[stream error]"

    @staticmethod
    def simulate_stream(content: str, delay: float = 0.01, chunk_size: int = 3):
        """Simulate streaming for mock mode by yielding content character by character."""
        for i in range(0, len(content), chunk_size):
            time.sleep(delay)
            yield content[i:i + chunk_size]
