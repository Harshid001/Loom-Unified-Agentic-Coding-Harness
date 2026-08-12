import json
import time

import httpx
import pytest

from loom.api.webhooks import WebhookEngine, WebhookEventType, WebhookSubscription
from loom.business.audit_log import AuditLogger
from loom.business.models import AuditAction
from loom.business.post_merge import (
    PostMergeMonitor,
    RevertPatchError,
    auto_rollback_triggered,
    generate_revert_patch,
)

SAMPLE_DIFF = (
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1,3 +1,2 @@\n"
    " import os\n"
    "-old_line\n"
    "-another_old\n"
    "+new_line\n"
    " context\n"
    "@@ -20,1 +20,2 @@\n"
    " keep\n"
    "+added_second_hunk\n"
)


class TestAutoRollbackRule:
    def test_no_ci_failure_never_triggers(self):
        assert auto_rollback_triggered(merge_time=time.time(), ci_failure_detected=False) is False

    def test_failure_inside_window_triggers(self):
        now = 1_000_000.0
        assert auto_rollback_triggered(merge_time=now - 300, ci_failure_detected=True, now=now) is True

    def test_failure_after_window_does_not_trigger(self):
        now = 1_000_000.0
        assert (
            auto_rollback_triggered(
                merge_time=now - 7200, ci_failure_detected=True, monitor_timeout_seconds=3600, now=now
            )
            is False
        )


class TestGenerateRevertPatch:
    def test_reverses_hunk_markers(self):
        revert = generate_revert_patch(SAMPLE_DIFF)
        assert revert.startswith("--- b/app.py\n+++ a/app.py\n")
        assert "@@ -1,2 +1,3 @@" in revert
        assert "-new_line" in revert
        assert "+old_line" in revert
        assert "+another_old" in revert
        assert "+added_second_hunk" not in revert.split("@@ -1,2 +1,3 @@")[0]

    def test_double_revert_is_identity(self):
        assert generate_revert_patch(generate_revert_patch(SAMPLE_DIFF)) == SAMPLE_DIFF

    def test_empty_input_returns_empty(self):
        assert generate_revert_patch("") == ""

    def test_no_change_diff_returns_empty(self):
        assert generate_revert_patch("--- a/x\n+++ b/x\n@@ -1 +1 @@\n same\n") == ""

    def test_new_file_addition_reverts_to_deletion(self):
        add_file = "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1,1 @@\n+hello\n"
        revert = generate_revert_patch(add_file)
        assert revert.startswith("--- b/new.txt\n+++ /dev/null\n")
        assert "-hello" in revert

    def test_malformed_diff_raises(self):
        with pytest.raises(RevertPatchError):
            generate_revert_patch("--- a/only_header\n")


class FakeAsyncClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, content=None, headers=None, timeout=None):
        self.calls.append({"url": url, "content": content, "headers": headers})
        return httpx.Response(200, text="ok")

    async def aclose(self):
        pass


def test_post_merge_monitor_evaluate(tmp_path):
    monitor = PostMergeMonitor(revert_log_dir=str(tmp_path / "reverts"))
    now = 1_000_000.0
    report = monitor.evaluate(
        run_id="run_x",
        merge_time=now - 60,
        ci_failure_detected=True,
        patch_diff=SAMPLE_DIFF,
        now=now,
    )
    assert report["rollback_needed"] is True
    assert report["revert_patch"] != ""
    assert report["elapsed_seconds"] == 60.0

    ok_report = monitor.evaluate(
        run_id="run_y",
        merge_time=now - 60,
        ci_failure_detected=False,
        patch_diff=SAMPLE_DIFF,
        now=now,
    )
    assert ok_report["rollback_needed"] is False
    assert ok_report["revert_patch"] == ""


def test_post_merge_monitor_record_rollback(tmp_path):
    audit = AuditLogger(storage_dir=str(tmp_path / "audit"))
    engine = WebhookEngine(storage_dir=str(tmp_path / "webhooks"))
    engine._http = FakeAsyncClient()
    engine.register(
        WebhookSubscription(
            id="sub_rb",
            org_id="org_rb",
            url="https://example.com/rb",
            events={WebhookEventType.RUN_ROLLED_BACK},
            max_retries=1,
            retry_backoff_base_seconds=0.01,
        )
    )

    monitor = PostMergeMonitor(
        webhook_engine=engine,
        audit_logger=audit,
        revert_log_dir=str(tmp_path / "reverts"),
    )
    report = monitor.evaluate(
        run_id="run_rb",
        merge_time=time.time() - 30,
        ci_failure_detected=True,
        patch_diff=SAMPLE_DIFF,
    )
    record = monitor.record_rollback(org_id="org_rb", report=report, actor_id="ci_bot")

    assert record["id"].startswith("revert_")
    assert record["revert_patch"] == report["revert_patch"]

    entries = audit.get_entries(org_id="org_rb", action=AuditAction.RUN_ROLLED_BACK)
    assert len(entries) == 1
    assert entries[0].actor_id == "ci_bot"
    assert entries[0].metadata["revert_id"] == record["id"]

    revert_log = json.loads((tmp_path / "reverts" / "revert_log.jsonl").read_text(encoding="utf-8").strip())
    assert revert_log["run_id"] == "run_rb"

    assert len(engine._http.calls) == 1
    payload = json.loads(engine._http.calls[0]["content"])
    assert payload["event"] == WebhookEventType.RUN_ROLLED_BACK.value
    assert payload["data"]["revert_record"]["id"] == record["id"]


def test_runner_delegates_auto_rollback_rule(tmp_path):
    from loom.sandbox.local_process import LocalProcessSandbox
    from loom.verification.runner import VerificationRunner

    runner = VerificationRunner(sandbox=LocalProcessSandbox(str(tmp_path)))
    now = time.time()
    assert runner.should_auto_rollback(merge_time=now, ci_failure_detected=True) is True
    assert runner.should_auto_rollback(merge_time=now - 7200, ci_failure_detected=True) is False
    assert runner.should_auto_rollback(merge_time=now, ci_failure_detected=False) is False
