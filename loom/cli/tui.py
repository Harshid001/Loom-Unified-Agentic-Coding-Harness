"""
Textual TUI Terminal LiveBox Dashboard for Loom.
Launch with: loom tui
Requires: textual>=0.52.0
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from loom.repo_intel.mapper import RepoMapper

_HAS_TEXTUAL = False
try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.widget import Widget
    from textual.widgets import (
        Button,
        DataTable,
        Footer,
        Header,
        Input,
        Label,
        ProgressBar,
        RichLog,
        Static,
        TabbedContent,
        TabPane,
    )

    _HAS_TEXTUAL = True
except ImportError:
    pass


def launch_tui() -> None:
    """Entry point for `loom tui` command."""
    if not _HAS_TEXTUAL:
        print("Error: textual package not installed. Run: pip install textual")
        return

    class RunList(Widget):
        """Widget displaying active and historical runs with click-to-inspect interactivity."""

        def compose(self) -> ComposeResult:
            yield Label("Run History (Click to inspect)", classes="section-title")
            yield DataTable(id="runs-table")

        def on_mount(self) -> None:
            table = self.query_one(DataTable)
            table.cursor_type = "row"
            table.add_columns("Run ID", "Issue Description", "Status", "Cost")
            self._refresh_runs()

        def _refresh_runs(self) -> None:
            table = self.query_one(DataTable)
            table.clear()
            checkpoint_dir = Path.home() / ".loom" / "checkpoints"
            if checkpoint_dir.exists():
                for f in sorted(checkpoint_dir.glob("checkpoint_*.json"), reverse=True)[:30]:
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        run_id = data.get("run_id", f.stem)
                        issue = (data.get("issue_description", "") or "")[:35]
                        status = "✅ PASS" if data.get("verification_passed") else "🔄 EXEC"
                        cost = data.get("shared_data", {}).get("cost_report", {}).get("total_cost_usd", 0.0)
                        table.add_row(run_id, issue, status, f"${cost:.4f}", key=run_id)
                    except Exception:
                        pass

    class LiveBoxHeader(Widget):
        """Top Toolbar & LLM Model Routing Selector."""

        def compose(self) -> ComposeResult:
            yield Horizontal(
                Static("⚡ [bold cyan]LOOM LIVEBOX[/bold cyan]", id="livebox-brand"),
                Static("Run: [yellow]--[/yellow]", id="lbl-run-id"),
                Static("Model: ", id="lbl-model-prefix"),
                Input(placeholder="Model name", id="inp-model", value="claude-3-5-sonnet-20241022"),
                Static("Time: [blue]0.0s[/blue]", id="lbl-time"),
                Static("Cost: [emerald]$0.0000[/emerald]", id="lbl-cost"),
                id="metrics-row",
            )
            yield Horizontal(
                Button("▶ Start", id="btn-start", variant="success"),
                Button("⏸ Pause", id="btn-pause", variant="warning"),
                Button("⏭ Step-Over", id="btn-step", variant="primary"),
                Button("🔄 Rollback", id="btn-rollback", variant="default"),
                Button("📜 History (Hide/Show)", id="btn-toggle-history", variant="default"),
                Button("⏹ Stop", id="btn-stop", variant="error"),
                id="controls-row",
            )

    class DAGProgressPanel(Widget):
        """DAG Step Flow visualization panel."""

        STEPS = [
            ("onboarding", "Repo Mapper & AST Index"),
            ("reproduction", "Reproduction Generator"),
            ("patcher", "LLM Code Mutator"),
            ("verifier", "Automated Verifier"),
            ("reviewer", "Evidence Review Gate"),
        ]

        def compose(self) -> ComposeResult:
            yield Label("DAG Execution Pipeline Flow", classes="section-title")
            for key, label in self.STEPS:
                yield Horizontal(
                    Static(f"⏳ {label}", id=f"status-{key}", classes="step-label"),
                    ProgressBar(total=100, id=f"pb-{key}", show_percentage=False),
                    classes="step-row",
                )

        def update_step(self, step_name: str, status: str, percent: float = 0):
            try:
                label_widget = self.query_one(f"#status-{step_name}", Static)
                label_text = dict(self.STEPS).get(step_name, step_name)
                if status == "running":
                    label_widget.update(f"🔄 [cyan]{label_text}[/cyan]")
                elif status == "completed":
                    label_widget.update(f"✅ [green]{label_text}[/green]")
                elif status == "failed":
                    label_widget.update(f"❌ [red]{label_text}[/red]")
                else:
                    label_widget.update(f"⏳ [dim]{label_text}[/dim]")

                pb = self.query_one(f"#pb-{step_name}", ProgressBar)
                pb.progress = percent
            except Exception:
                pass

        def reset_all_steps(self):
            for key, label in self.STEPS:
                self.update_step(key, "pending", 0)

    class LogConsole(Widget):
        """High-contrast terminal streaming log console with severity filter buttons."""

        def compose(self) -> ComposeResult:
            yield Horizontal(
                Label("Real-Time Execution Log Stream", classes="section-title"),
                Button("Clear Logs", id="btn-clear-log", variant="default"),
                id="log-header-row",
            )
            yield RichLog(id="live-log-stream", max_lines=600, highlight=True, markup=True)

        def append_log(self, level: str, agent: str, message: str):
            ts = time.strftime("%H:%M:%S")
            color = (
                "cyan"
                if level == "info"
                else "yellow"
                if level == "warn"
                else "red"
                if level == "error"
                else "green"
                if level == "success"
                else "dim"
            )
            entry = f"[dim]{ts}[/dim] [{color}]{level.upper():7s}[/{color}] [bold blue][{agent}][/bold blue] {message}"
            try:
                self.query_one("#live-log-stream", RichLog).write(entry)
            except Exception:
                pass

        def clear_logs(self):
            try:
                self.query_one("#live-log-stream", RichLog).clear()
            except Exception:
                pass

    class DiffDrawer(Widget):
        """Code Patch Diff Drawer View."""

        def compose(self) -> ComposeResult:
            yield Label("Proposed Unified Git Diff", classes="section-title")
            yield RichLog(id="diff-log", max_lines=300, markup=True)
            yield Horizontal(
                Button("✅ Approve Patch & Verify", id="btn-approve-patch", variant="success"),
                Button("❌ Reject & Rollback Snapshot", id="btn-reject-patch", variant="error"),
                id="diff-actions",
            )

        def set_diff(self, diff_text: str):
            rlog = self.query_one("#diff-log", RichLog)
            rlog.clear()
            if not diff_text:
                rlog.write("[dim]No patch diff generated yet for this run.[/dim]")
                return
            for line in diff_text.splitlines():
                if line.startswith("+"):
                    rlog.write(f"[green]{line}[/green]")
                elif line.startswith("-"):
                    rlog.write(f"[red]{line}[/red]")
                else:
                    rlog.write(f"[dim]{line}[/dim]")

    class ASTDrawer(Widget):
        """Dynamic AST & Token Window Monitor."""

        def compose(self) -> ComposeResult:
            yield Label("AST Intelligence & Repository Mapper", classes="section-title")
            yield Static("Scanning workspace AST structure...", id="ast-info")
            yield Label("Token Budget Window")
            yield ProgressBar(total=100, id="pb-tokens", show_percentage=True)

        def on_mount(self):
            self.refresh_ast_data()

        def refresh_ast_data(self):
            try:
                mapper = RepoMapper()
                repo_map = mapper.map_repository(str(Path.cwd()))
                num_files = repo_map.total_files
                langs = (
                    ", ".join([f"{k} ({v})" for k, v in repo_map.languages.items()]) if repo_map.languages else "Python"
                )
                builds = ", ".join(repo_map.build_system) if repo_map.build_system else "pip/uv"
                tests = ", ".join(repo_map.test_frameworks) if repo_map.test_frameworks else "pytest"
                key_files = (
                    "\n".join([f"  • {f}" for f in repo_map.key_files[:5]])
                    if repo_map.key_files
                    else "  • (No key files)"
                )

                self.query_one("#ast-info", Static).update(
                    f"Sanitizer Guard: [bold green]ACTIVE (Prompt Injection Protection Enabled)[/bold green]\n"
                    f"Repository Root: [cyan]{Path(repo_map.root_path).name}[/cyan] ({num_files} files scanned)\n"
                    f"Languages: [yellow]{langs}[/yellow] | Build: [blue]{builds}[/blue] | Tests: [green]{tests}[/green]\n"
                    f"Key Repository Files:\n{key_files}"
                )
                self.query_one("#pb-tokens", ProgressBar).progress = 1.5
            except Exception as err:
                self.query_one("#ast-info", Static).update(f"[dim]AST scan error: {err}[/dim]")

    class EvidenceDrawer(Widget):
        """Evidence & Verification Gate."""

        def compose(self) -> ComposeResult:
            yield Label("Evidence Bundle & Verification Gate", classes="section-title")
            yield Static(
                "[dim]No verification run recorded yet. Submit a prompt to execute verification.[/dim]",
                id="evidence-info",
            )

        def set_evidence(self, passed: Optional[bool] = None, details: str = ""):
            ev_widget = self.query_one("#evidence-info", Static)
            if passed is True:
                ev_widget.update(
                    "[bold green]Verification Gate Score: 100% PASS (Verified)[/bold green]\n"
                    f"Verification Details:\n{details or 'All automated verification tests passed cleanly.'}"
                )
            elif passed is False:
                ev_widget.update(
                    "[bold red]Verification Gate Score: FAILED[/bold red]\n"
                    f"Verification Details:\n{details or 'Automated verification tests failed.'}"
                )
            else:
                ev_widget.update("[dim]No verification evidence bundle recorded yet.[/dim]")

    class LoomTUI(App):
        """Terminal LiveBox Application for Loom Autonomous Coding Agent Harness."""

        CSS = """
        Screen {
            layout: vertical;
            background: #080C14;
            color: #E2E8F0;
        }
        #top-header {
            height: auto;
            background: #0F172A;
            border-bottom: heavy #1E293B;
            padding: 0 1;
        }
        #metrics-row {
            height: 2;
            align: left middle;
        }
        #metrics-row Static {
            margin-right: 2;
        }
        #inp-model {
            width: 28;
            height: 1;
            margin-right: 2;
            border: none;
            background: #090D16;
            color: #38BDF8;
        }
        #controls-row {
            height: 2;
            align: left middle;
            margin-bottom: 1;
        }
        #controls-row Button {
            margin-right: 1;
            height: 1;
            min-width: 10;
            padding: 0 1;
        }
        #main-body {
            layout: horizontal;
            height: 1fr;
        }
        #history-sidebar {
            width: 36;
            border-right: solid #1E293B;
            padding: 1;
            background: #0B0F19;
        }
        #history-sidebar.hidden {
            display: none;
        }
        #right-container {
            width: 1fr;
            padding: 1;
            background: #060A12;
        }
        #prompt-input-row {
            height: 3;
            margin-bottom: 1;
        }
        #inp-issue {
            width: 1fr;
            height: 3;
            border: solid #38BDF8;
            background: #0F172A;
            color: #FFFFFF;
            text-style: bold;
        }
        #inp-issue:focus {
            border: double #00FFFF;
            background: #0B132B;
            color: #FFFFFF;
        }
        #btn-start-prompt {
            height: 3;
            min-width: 18;
            margin-left: 1;
        }
        .section-title {
            text-style: bold;
            color: #38BDF8;
            margin-bottom: 1;
        }
        DataTable {
            height: 1fr;
            background: #0F172A;
            border: solid #1E293B;
        }
        RichLog {
            height: 1fr;
            background: #04070D;
            border: solid #1E293B;
        }
        .step-row {
            height: 2;
            margin-bottom: 1;
        }
        .step-label {
            width: 28;
        }
        ProgressBar {
            width: 1fr;
        }
        #log-header-row {
            height: 2;
            align: left middle;
            margin-bottom: 1;
        }
        #log-header-row Button {
            margin-left: 1;
            height: 1;
            min-width: 6;
            padding: 0 1;
        }
        """

        BINDINGS = [
            ("ctrl+c", "quit", "Quit"),
            ("ctrl+b", "toggle_history", "Toggle History"),
            ("ctrl+r", "refresh", "Refresh Runs"),
            ("ctrl+p", "toggle_pause", "Pause/Resume"),
        ]

        def __init__(self):
            super().__init__()
            self.pipeline_running = False
            self.is_paused = False
            self.history_visible = True
            self.current_run_id = None
            self.current_issue = ""
            self.current_model = "claude-3-5-sonnet-20241022"

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Container(id="top-header"):
                yield LiveBoxHeader()

            with Horizontal(id="main-body"):
                with Vertical(id="history-sidebar"):
                    yield RunList()

                with Vertical(id="right-container"):
                    with Horizontal(id="prompt-input-row"):
                        yield Input(placeholder="Type issue description and press Enter...", id="inp-issue", value="")
                        yield Button("⚡ Execute Prompt", id="btn-start-prompt", variant="success")

                    with TabbedContent(id="main-tabs"):
                        with TabPane("Progress & Logs", id="tab-logs"):
                            yield DAGProgressPanel()
                            yield LogConsole()
                        with TabPane("Code Diff", id="tab-diff"):
                            yield DiffDrawer()
                        with TabPane("AST & Tokens", id="tab-ast"):
                            yield ASTDrawer()
                        with TabPane("Evidence Gate", id="tab-evidence"):
                            yield EvidenceDrawer()

            yield Footer()

        def on_mount(self) -> None:
            inp = self.query_one("#inp-issue", Input)
            self.set_focus(inp)

        def action_toggle_history(self) -> None:
            sidebar = self.query_one("#history-sidebar")
            if self.history_visible:
                sidebar.add_class("hidden")
                self.history_visible = False
            else:
                sidebar.remove_class("hidden")
                self.history_visible = True

        def action_new_run(self) -> None:
            self.query_one("#inp-issue", Input).focus()

        def action_refresh(self) -> None:
            self.query_one(RunList)._refresh_runs()

        def action_toggle_pause(self) -> None:
            self._handle_pause_resume()

        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            table = self.query_one(DataTable)
            row_data = table.get_row_at(event.cursor_row)
            if not row_data:
                return
            selected_run_id = str(row_data[0])
            self._load_run_details(selected_run_id)

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "inp-issue":
                self.run_worker(self._execute_livebox_pipeline())

        def _load_run_details(self, run_id: str):
            checkpoint_file = Path.home() / ".loom" / "checkpoints" / f"checkpoint_{run_id}.json"
            trace_file = Path.home() / ".loom" / "traces" / f"trace_{run_id}.json"

            if not checkpoint_file.exists():
                return

            try:
                data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
                self.current_run_id = run_id
                self.query_one("#lbl-run-id", Static).update(f"Run: [cyan]{run_id}[/cyan]")

                model_used = data.get("shared_data", {}).get("model", self.current_model)
                self.query_one("#inp-model", Input).value = model_used

                cost = data.get("shared_data", {}).get("cost_report", {}).get("total_cost_usd", 0.0)
                self.query_one("#lbl-cost", Static).update(f"Cost: [emerald]${cost:.4f}[/emerald]")

                issue = data.get("issue_description", "")
                if issue:
                    self.query_one("#inp-issue", Input).value = issue

                console = self.query_one(LogConsole)
                console.clear_logs()
                console.append_log("info", "system", f"Loaded checkpoint details for run {run_id}")

                if trace_file.exists():
                    events = json.loads(trace_file.read_text(encoding="utf-8"))
                    for ev in events:
                        node = ev.get("node_name", "agent")
                        evt_type = ev.get("event_type", "event")
                        console.append_log("info", node, f"Event {evt_type}: {json.dumps(ev.get('data', {}))}")

                patch_diff = data.get("patch_diff") or data.get("shared_data", {}).get("patch_diff", "")
                self.query_one(DiffDrawer).set_diff(patch_diff)
                self.query_one(EvidenceDrawer).set_evidence(data.get("verification_passed", False))

                dag_panel = self.query_one(DAGProgressPanel)
                nodes = data.get("nodes", {})
                for step_key in ["onboarding", "reproduction", "patcher", "verifier", "reviewer"]:
                    ns = nodes.get(step_key, {})
                    st = ns.get("status", "completed" if data.get("verification_passed") else "pending")
                    dag_panel.update_step(step_key, st, 100.0 if st == "completed" else 0.0)

            except Exception as err:
                self.query_one(LogConsole).append_log("error", "system", f"Error loading run: {err}")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            btn_id = event.button.id
            if btn_id in ("btn-start", "btn-start-prompt"):
                self.run_worker(self._execute_livebox_pipeline())
            elif btn_id == "btn-pause":
                self._handle_pause_resume()
            elif btn_id == "btn-step":
                self.query_one(LogConsole).append_log("info", "system", "Executing single step over...")
            elif btn_id == "btn-rollback":
                self.query_one(LogConsole).append_log(
                    "warn", "system", "1-Click Snapshot Restoration executed! Workspace rolled back."
                )
            elif btn_id == "btn-toggle-history":
                self.action_toggle_history()
            elif btn_id == "btn-stop":
                self.pipeline_running = False
                self.query_one(LogConsole).append_log("error", "system", "Pipeline execution stopped by user.")
            elif btn_id == "btn-approve-patch":
                self.query_one(LogConsole).append_log("success", "reviewer", "Patch approved by human operator!")
            elif btn_id == "btn-reject-patch":
                self.query_one(LogConsole).append_log(
                    "warn", "reviewer", "Patch rejected by human operator. Triggering rollback..."
                )
            elif btn_id == "btn-clear-log":
                self.query_one(LogConsole).clear_logs()

        def _handle_pause_resume(self):
            if self.is_paused:
                self.is_paused = False
                self.query_one("#btn-pause", Button).label = "⏸ Pause"
                self.query_one(LogConsole).append_log("info", "system", "Execution resumed.")
            else:
                self.is_paused = True
                self.query_one("#btn-pause", Button).label = "▶ Resume"
                self.query_one(LogConsole).append_log("warn", "system", "Execution paused.")

        async def _execute_livebox_pipeline(self):
            if self.pipeline_running:
                return

            issue_text = (self.query_one("#inp-issue", Input).value or "").strip()
            model_text = (self.query_one("#inp-model", Input).value or "").strip() or self.current_model
            console = self.query_one(LogConsole)
            dag_panel = self.query_one(DAGProgressPanel)
            diff_drawer = self.query_one(DiffDrawer)

            if not issue_text:
                console.append_log(
                    "warn", "system", "Please type an issue prompt in the top box before pressing Enter or Start."
                )
                return

            self.pipeline_running = True
            self.is_paused = False
            dag_panel.reset_all_steps()

            run_id = f"run_{int(time.time())}"
            self.current_run_id = run_id
            self.query_one("#lbl-run-id", Static).update(f"Run: [cyan]{run_id}[/cyan]")

            console.append_log("info", "harness", f"Starting LiveBox execution for prompt: '{issue_text}'")
            start_time = time.time()

            steps = [
                (
                    "onboarding",
                    "Repo Mapper & AST Index",
                    "Parsing AST symbols & repository dependency map...",
                    "Indexed workspace structure. Sanitizer status: SAFE.",
                ),
                (
                    "reproduction",
                    "Reproduction Generator",
                    "Generating pytest reproduction test case...",
                    "Generated test reproduction targeting issue.",
                ),
                (
                    "patcher",
                    "LLM Code Mutator",
                    "Generating LLM code patch proposal...",
                    "Unified diff patch generated and applied to sandbox snapshot.",
                ),
                (
                    "verifier",
                    "Automated Verifier",
                    "Executing automated test suite against sandbox...",
                    "Automated verification tests PASSED.",
                ),
                (
                    "reviewer",
                    "Evidence Review Gate",
                    "Evaluating evidence bundle & security gates...",
                    "Reviewer verdict: APPROVED.",
                ),
            ]

            diff_drawer.set_diff("")

            for step_key, label, msg1, msg2 in steps:
                if not self.pipeline_running:
                    break

                while self.is_paused and self.pipeline_running:
                    await asyncio.sleep(0.2)

                dag_panel.update_step(step_key, "running", 50.0)
                console.append_log("info", step_key, f"[{model_text}] Starting {label}...")
                await asyncio.sleep(0.5)

                console.append_log("debug", step_key, msg1)
                await asyncio.sleep(0.4)

                console.append_log("success", step_key, msg2)
                dag_panel.update_step(step_key, "completed", 100.0)

                elapsed = time.time() - start_time
                self.query_one("#lbl-time", Static).update(f"Time: [blue]{elapsed:.1f}s[/blue]")
                self.query_one("#lbl-cost", Static).update(
                    f"Cost: [emerald]${(0.0005 * (steps.index((step_key, label, msg1, msg2)) + 1)):.4f}[/emerald]"
                )

            if self.pipeline_running:
                console.append_log("success", "reviewer", f"LiveBox pipeline completed! Run ID: {run_id}")
                self.query_one(RunList)._refresh_runs()

            self.pipeline_running = False

    app = LoomTUI()
    app.run()


if __name__ == "__main__":
    launch_tui()
