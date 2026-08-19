"""Production Textual terminal operator console for Loom."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import cast

from loom.cli.tui_controller import ControllerEvent, TUIRunController
from loom.repo_intel.mapper import RepoMapper

_HAS_TEXTUAL = False
try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical
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
    """Launch ``loom tui``."""
    if not _HAS_TEXTUAL:
        print("Error: textual package not installed. Run: pip install textual")
        return

    class RunList(Vertical):
        def compose(self) -> ComposeResult:
            yield Label("Run History", classes="section-title")
            yield DataTable(id="runs-table")

        def on_mount(self) -> None:
            table = self.query_one("#runs-table", DataTable)
            table.cursor_type = "row"
            table.add_columns("Run ID", "Status", "Issue", "Cost")
            self.refresh_runs()

        def refresh_runs(self) -> None:
            table = self.query_one("#runs-table", DataTable)
            table.clear()
            directory = Path.home() / ".loom" / "checkpoints"
            if not directory.exists():
                return
            for path in sorted(directory.glob("checkpoint_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    run_id = data.get("run_id", path.stem)
                    status = str(data.get("shared_data", {}).get("run_status", "unknown")).split(".")[-1].upper()
                    if data.get("verification_passed") and status in {"UNKNOWN", "EVIDENCE_REVIEW"}:
                        status = "VERIFIED"
                    elif status == "UNKNOWN":
                        nodes = data.get("nodes", {})
                        status = "FAILED" if any(node.get("status") == "failed" for node in nodes.values()) else "EXECUTED"
                    issue = (data.get("issue_description") or "")[:28]
                    cost = data.get("shared_data", {}).get("cost_report", {}).get("total_cost_usd", 0.0)
                    table.add_row(run_id, status, issue, f"${float(cost):.4f}", key=run_id)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue

    class LiveBoxHeader(Vertical):
        def compose(self) -> ComposeResult:
            yield Horizontal(
                Static("⚡ LOOM LIVEBOX", id="brand"),
                Static("Run: --", id="lbl-run-id"),
                Static("Status: IDLE", id="lbl-status"),
                Static("Node: --", id="lbl-node"),
                Static("Time: 0.0s", id="lbl-time"),
                Static("Tokens: 0", id="lbl-tokens"),
                Static("Cost: $0.0000", id="lbl-cost"),
                id="metrics-row",
            )
            yield Horizontal(
                Button("▶ Start", id="btn-start", variant="success"),
                Button("⏸ Pause", id="btn-pause", variant="warning", disabled=True),
                Button("⏭ Step", id="btn-step", variant="primary", disabled=True),
                Button("↩ Rollback", id="btn-rollback", disabled=True),
                Button("⏹ Stop", id="btn-stop", variant="error", disabled=True),
                Button("History", id="btn-toggle-history"),
                id="controls-row",
            )

    class DAGProgressPanel(Vertical):
        STEPS = [
            ("onboarding", "Repository Mapping"),
            ("reproduction", "Reproduction Test"),
            ("planner", "Fix Strategy"),
            ("patcher", "Code Mutation"),
            ("verifier", "Automated Verification"),
            ("reviewer", "Evidence Review"),
        ]

        def compose(self) -> ComposeResult:
            yield Label("DAG Execution Pipeline", classes="section-title")
            for key, label in self.STEPS:
                yield Horizontal(
                    Static(f"○ {label}", id=f"status-{key}", classes="step-label"),
                    ProgressBar(total=100, id=f"pb-{key}", show_percentage=False),
                    classes="step-row",
                )

        def reset(self) -> None:
            for key, _ in self.STEPS:
                self.update_step(key, "pending", 0)

        def update_step(self, key: str, status: str, percent: float) -> None:
            if key not in dict(self.STEPS):
                return
            widget = self.query_one(f"#status-{key}", Static)
            label = dict(self.STEPS)[key]
            icon = {"running": "◉", "completed": "✓", "failed": "✕"}.get(status, "○")
            widget.update(f"{icon} {label}")
            self.query_one(f"#pb-{key}", ProgressBar).progress = max(0, min(100, percent))

    class LogConsole(Vertical):
        def __init__(self) -> None:
            super().__init__()
            self.level_filter = "ALL"
            self.entries: list[tuple[str, str]] = []

        def compose(self) -> ComposeResult:
            yield Horizontal(
                Label("Live Execution Log", classes="section-title"),
                Button("ALL", id="log-all"),
                Button("INFO", id="log-info"),
                Button("WARN", id="log-warn"),
                Button("ERROR", id="log-error"),
                Button("Clear", id="btn-clear-log"),
                id="log-header-row",
            )
            yield RichLog(id="live-log-stream", max_lines=700, highlight=True, markup=False)

        def append_log(self, level: str, node: str, message: str) -> None:
            self.entries.append((level.upper(), f"{time.strftime('%H:%M:%S')} {level.upper():7s} [{node}] {message}"))
            self._render_logs()

        def _render_logs(self) -> None:
            log = self.query_one("#live-log-stream", RichLog)
            log.clear()
            for level, text in self.entries[-700:]:
                if self.level_filter != "ALL" and level != self.level_filter:
                    continue
                log.write(text)

        def clear(self) -> None:
            self.entries.clear()
            self._render_logs()

        def set_filter(self, level: str) -> None:
            self.level_filter = level
            self._render_logs()

    class DiffDrawer(Vertical):
        def compose(self) -> ComposeResult:
            yield Label("Proposed Unified Git Diff", classes="section-title")
            yield Static("No patch diff generated yet.", id="diff-summary")
            yield RichLog(id="diff-log", max_lines=500, markup=False)
            yield Horizontal(
                Button("Approve Patch", id="btn-approve-patch", variant="success", disabled=True),
                Button("Reject & Rollback", id="btn-reject-patch", variant="error", disabled=True),
                id="diff-actions",
            )

        def set_diff(self, diff_text: str) -> None:
            log = self.query_one("#diff-log", RichLog)
            log.clear()
            if not diff_text:
                self.query_one("#diff-summary", Static).update("No patch diff generated yet.")
                return
            added = deleted = 0
            for line in diff_text.splitlines():
                if line.startswith("+++") or line.startswith("---"):
                    prefix = "FILE "
                elif line.startswith("@@"):
                    prefix = "HUNK "
                elif line.startswith("+"):
                    prefix, added = "ADD ", added + 1
                elif line.startswith("-"):
                    prefix, deleted = "DEL ", deleted + 1
                else:
                    prefix = "     "
                log.write(prefix + line)
            files = sum(1 for diff_line in diff_text.splitlines() if diff_line.startswith("+++ "))
            self.query_one("#diff-summary", Static).update(f"Files: {files}   Added: +{added}   Removed: -{deleted}")

    class ASTDrawer(Vertical):
        def compose(self) -> ComposeResult:
            yield Label("AST Intelligence & Token Window", classes="section-title")
            yield Static("Scanning repository...", id="ast-info")
            yield Static("Token usage", id="token-label")
            yield ProgressBar(total=100, id="pb-tokens", show_percentage=True)

        def on_mount(self) -> None:
            self.run_worker(self._scan, thread=True, exclusive=True)

        def _scan(self) -> None:
            try:
                repo_map = RepoMapper().map_repository(str(Path.cwd()))
                langs = ", ".join(f"{k} ({v})" for k, v in repo_map.languages.items()) or "Unknown"
                builds = ", ".join(repo_map.build_system) or "Unknown"
                tests = ", ".join(repo_map.test_frameworks) or "Unknown"
                cast(App, self.app).call_from_thread(
                    self.query_one("#ast-info", Static).update,
                    f"Repository: {Path(repo_map.root_path).name}\nFiles: {repo_map.total_files}\nLanguages: {langs}\nBuild: {builds}\nTests: {tests}",
                )
            except Exception as exc:
                cast(App, self.app).call_from_thread(self.query_one("#ast-info", Static).update, f"AST scan failed: {exc}")

        def update_tokens(self, tokens: int, context_window: int | None = None) -> None:
            self.query_one("#token-label", Static).update(f"Token usage: {tokens:,}")
            if context_window and context_window > 0:
                self.query_one("#pb-tokens", ProgressBar).progress = min(100, tokens / context_window * 100)

    class EvidenceDrawer(Vertical):
        def compose(self) -> ComposeResult:
            yield Label("Evidence & Verification Gate", classes="section-title")
            yield Static("No verification evidence yet.", id="evidence-info")

        def update(self, passed: bool | None, details: str = "") -> None:
            if passed is True:
                text = "✓ VERIFICATION PASSED\n" + (details or "Automated verification completed successfully.")
            elif passed is False:
                text = "✕ VERIFICATION FAILED\n" + (details or "Automated verification failed.")
            else:
                text = "No verification evidence yet."
            self.query_one("#evidence-info", Static).update(text)

    class LoomTUI(App):
        CSS = """
        Screen { layout: vertical; }
        #top-header { height: auto; padding: 0 1; border-bottom: solid $panel; }
        #metrics-row { height: 2; }
        #metrics-row Static { margin-right: 2; }
        #controls-row { height: 2; margin-bottom: 1; }
        #controls-row Button { margin-right: 1; min-width: 10; }
        #main-body { height: 1fr; }
        #history-sidebar { width: 32; min-width: 26; border-right: solid $panel; padding: 1; }
        #history-sidebar.hidden { display: none; }
        #right-container { width: 1fr; padding: 1; }
        #prompt-input-row { height: 3; margin-bottom: 1; }
        #inp-issue { width: 1fr; }
        #btn-start-prompt { min-width: 18; margin-left: 1; }
        .section-title { text-style: bold; margin-bottom: 1; }
        .step-row { height: 2; margin-bottom: 1; }
        .step-label { width: 28; }
        ProgressBar { width: 1fr; }
        RichLog { height: 1fr; }
        #log-header-row { height: 2; }
        #log-header-row Button { margin-right: 1; }
        #diff-actions { height: 3; }
        #diff-actions Button { margin-right: 1; }
        """

        BINDINGS = [
            ("ctrl+c", "quit", "Quit"),
            ("ctrl+b", "toggle_history", "History"),
            ("ctrl+r", "refresh_runs", "Refresh"),
            ("ctrl+p", "pause_resume", "Pause/Resume"),
            ("s", "step", "Step"),
            ("k", "stop_run", "Stop"),
            ("d", "show_diff", "Diff"),
            ("e", "show_evidence", "Evidence"),
            ("l", "show_logs", "Logs"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.controller = TUIRunController(self._on_controller_event)
            self.history_visible = True
            self.current_status = "IDLE"

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Container(id="top-header"):
                yield LiveBoxHeader()
            with Horizontal(id="main-body"):
                with Vertical(id="history-sidebar"):
                    yield RunList()
                with Vertical(id="right-container"):
                    with Horizontal(id="prompt-input-row"):
                        yield Input(placeholder="Describe the issue to solve...", id="inp-issue")
                        yield Button("⚡ Execute", id="btn-start-prompt", variant="success")
                    with TabbedContent(id="main-tabs"):
                        with TabPane("Progress & Logs", id="tab-logs"):
                            yield DAGProgressPanel()
                            yield LogConsole()
                        with TabPane("Code Diff", id="tab-diff"):
                            yield DiffDrawer()
                        with TabPane("AST & Tokens", id="tab-ast"):
                            yield ASTDrawer()
                        with TabPane("Evidence", id="tab-evidence"):
                            yield EvidenceDrawer()
            yield Footer()

        def on_mount(self) -> None:
            self.query_one("#inp-issue", Input).focus()

        def _on_controller_event(self, event: ControllerEvent) -> None:
            log = self.query_one(LogConsole)
            if event.kind == "run_started":
                self.current_status = "RUNNING"
                state = self.controller.state
                if state is not None:
                    self.query_one("#lbl-run-id", Static).update(f"Run: {state.run_id}")
                self._set_controls(running=True, paused=False)
                self.query_one(DAGProgressPanel).reset()
            elif event.kind == "node_started":
                self.query_one("#lbl-status", Static).update("Status: RUNNING")
                self.query_one("#lbl-node", Static).update(f"Node: {event.node}")
                self.query_one(DAGProgressPanel).update_step(event.node, "running", 50)
                log.append_log("info", event.node, f"Agent started: {event.data.get('model', '') if event.data else ''}")
            elif event.kind == "log":
                log.append_log(event.level, event.node, event.message)
            elif event.kind == "node_completed":
                self.query_one(DAGProgressPanel).update_step(event.node, "completed", 100)
                self._refresh_diff_and_evidence()
            elif event.kind == "node_failed":
                self.query_one(DAGProgressPanel).update_step(event.node, "failed", 0)
                self.current_status = "FAILED"
                self.query_one("#lbl-status", Static).update("Status: FAILED")
                log.append_log("error", event.node, event.message)
                self._set_controls(running=False, paused=False)
            elif event.kind == "state":
                log.append_log(event.level, event.node, event.message)
                self.query_one("#lbl-status", Static).update(f"Status: {event.message.upper()}")
            elif event.kind == "approval":
                log.append_log(event.level, event.node, event.message)
            elif event.kind == "run_completed":
                self.current_status = "COMPLETED"
                self.query_one("#lbl-status", Static).update("Status: COMPLETED")
                log.append_log("success", "system", event.message)
                self._set_controls(running=False, paused=False)
                self.query_one(RunList).refresh_runs()
                self._refresh_diff_and_evidence()
            elif event.kind == "run_cancelled":
                self.current_status = "CANCELLED"
                self.query_one("#lbl-status", Static).update("Status: CANCELLED")
                log.append_log("warn", "system", event.message)
                self._set_controls(running=False, paused=False)
            elif event.kind == "run_failed":
                self.current_status = "FAILED"
                self.query_one("#lbl-status", Static).update("Status: FAILED")
                log.append_log("error", "system", event.message)
                self._set_controls(running=False, paused=False)

            self._update_metrics()

        def _update_metrics(self) -> None:
            metrics = self.controller.metrics()
            self.query_one("#lbl-time", Static).update(f"Time: {metrics['elapsed']:.1f}s")
            self.query_one("#lbl-tokens", Static).update(f"Tokens: {metrics['tokens']:,}")
            self.query_one("#lbl-cost", Static).update(f"Cost: ${metrics['cost']:.4f}")
            self.query_one(ASTDrawer).update_tokens(metrics["tokens"])

        def _set_controls(self, running: bool, paused: bool) -> None:
            self.query_one("#btn-start", Button).disabled = running
            self.query_one("#btn-start-prompt", Button).disabled = running
            self.query_one("#btn-pause", Button).disabled = not running
            self.query_one("#btn-step", Button).disabled = not running
            self.query_one("#btn-stop", Button).disabled = not running
            self.query_one("#btn-rollback", Button).disabled = not bool(self.controller.state)
            self.query_one("#btn-pause", Button).label = "▶ Resume" if paused else "⏸ Pause"

        def _refresh_diff_and_evidence(self) -> None:
            state = self.controller.state
            if not state:
                return
            diff = state.patch_diff or state.shared_data.get("patch_diff", "")
            self.query_one(DiffDrawer).set_diff(diff or "")
            self.query_one(EvidenceDrawer).update(state.verification_passed)
            ready = bool(diff)
            self.query_one("#btn-approve-patch", Button).disabled = not ready
            self.query_one("#btn-reject-patch", Button).disabled = not ready

        def action_toggle_history(self) -> None:
            sidebar = self.query_one("#history-sidebar")
            self.history_visible = not self.history_visible
            if self.history_visible:
                sidebar.remove_class("hidden")
            else:
                sidebar.add_class("hidden")

        def action_refresh_runs(self) -> None:
            self.query_one(RunList).refresh_runs()

        def action_pause_resume(self) -> None:
            if self.controller.graph and self.controller.graph.is_paused:
                self.controller.resume()
                self._set_controls(running=True, paused=False)
            else:
                self.controller.pause()
                self._set_controls(running=True, paused=True)

        def action_step(self) -> None:
            self.controller.step()

        def action_stop_run(self) -> None:
            self.controller.cancel()

        def action_show_diff(self) -> None:
            cast(TabbedContent, self.query_one("#main-tabs")).active = "tab-diff"

        def action_show_evidence(self) -> None:
            cast(TabbedContent, self.query_one("#main-tabs")).active = "tab-evidence"

        def action_show_logs(self) -> None:
            cast(TabbedContent, self.query_one("#main-tabs")).active = "tab-logs"

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "inp-issue":
                self._start_run()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            button_id = event.button.id
            if button_id in {"btn-start", "btn-start-prompt"}:
                self._start_run()
            elif button_id == "btn-pause":
                self.action_pause_resume()
            elif button_id == "btn-step":
                self.action_step()
            elif button_id == "btn-stop":
                self.action_stop_run()
            elif button_id == "btn-rollback":
                self.controller.rollback()
            elif button_id == "btn-toggle-history":
                self.action_toggle_history()
            elif button_id == "btn-clear-log":
                self.query_one(LogConsole).clear()
            elif button_id in {"log-all", "log-info", "log-warn", "log-error"}:
                self.query_one(LogConsole).set_filter(button_id.removeprefix("log-").upper())
            elif button_id == "btn-approve-patch":
                self.controller.approve_patch()
                self.query_one("#btn-approve-patch", Button).disabled = True
                self.query_one("#btn-reject-patch", Button).disabled = True
            elif button_id == "btn-reject-patch":
                self.controller.reject_patch()

        def _start_run(self) -> None:
            issue = self.query_one("#inp-issue", Input).value.strip()
            model = os.getenv("LOOM_TUI_MODEL", "claude-3-7-sonnet-20250219")
            self.controller.start(issue, str(Path.cwd()), model)

    LoomTUI().run()


if __name__ == "__main__":
    launch_tui()
