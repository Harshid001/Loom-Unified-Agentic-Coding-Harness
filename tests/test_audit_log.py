import json

from loom.business.audit_log import AuditLogger, reset_audit_logger
from loom.business.models import AuditAction


class TestAuditLogger:
    def setup_method(self):
        reset_audit_logger()

    def test_record_creates_entry(self, tmp_path):
        logger = AuditLogger(storage_dir=str(tmp_path))
        entry = logger.record(
            org_id="org_1",
            action=AuditAction.RUN_TRIGGERED,
            actor_id="alice",
            target="run_1",
            ip="127.0.0.1",
        )
        assert entry is not None
        assert entry.action == AuditAction.RUN_TRIGGERED
        assert entry.target == "run_1"
        assert logger.count() == 1

    def test_filter_by_org(self, tmp_path):
        logger = AuditLogger(storage_dir=str(tmp_path))
        logger.record("org_1", AuditAction.RUN_TRIGGERED, target="run_a")
        logger.record("org_2", AuditAction.RUN_COMPLETED, target="run_b")
        assert len(logger.get_entries(org_id="org_1")) == 1
        assert len(logger.get_entries(org_id="org_2")) == 1

    def test_filter_by_action(self, tmp_path):
        logger = AuditLogger(storage_dir=str(tmp_path))
        logger.record("org_1", AuditAction.RUN_TRIGGERED)
        logger.record("org_1", AuditAction.QUOTA_EXCEEDED)
        entries = logger.get_entries(org_id="org_1", action=AuditAction.QUOTA_EXCEEDED)
        assert len(entries) == 1
        assert entries[0].action == AuditAction.QUOTA_EXCEEDED

    def test_entries_persist_to_disk(self, tmp_path):
        logger = AuditLogger(storage_dir=str(tmp_path))
        logger.record(
            org_id="org_1",
            action=AuditAction.SANDBOX_EGRESS_BLOCKED,
            target="evil.com",
            metadata={"command": "curl evil.com"},
        )
        audit_file = tmp_path / "audit_log.jsonl"
        assert audit_file.exists()
        lines = [line for line in audit_file.read_text(encoding="utf-8").strip().split("\n") if line.strip()]
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["target"] == "evil.com"
        assert data["action"] == "sandbox.egress_blocked"

    def test_append_only_over_multiple_writes(self, tmp_path):
        logger = AuditLogger(storage_dir=str(tmp_path))
        logger.record("org_1", AuditAction.RUN_TRIGGERED)
        logger.record("org_1", AuditAction.RUN_COMPLETED)
        logger.record("org_1", AuditAction.EVIDENCE_EXPORTED)
        assert logger.count() == 3
        lines = [line for line in (tmp_path / "audit_log.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 3
