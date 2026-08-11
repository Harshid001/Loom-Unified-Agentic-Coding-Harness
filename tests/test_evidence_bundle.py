import hashlib
import json

from loom.verification.bundle import (
    EvidenceBundle,
    EvidenceBundler,
)


class TestEvidenceBundle:
    def test_create_bundle_contains_required_fields(self):
        bundler = EvidenceBundler()
        bundle = bundler.create_bundle(
            run_id="run_123",
            patch_diff="+fixed line",
            verification_success=True,
            test_summary={"passed": 10, "failed": 0},
            cost_report={"total_cost_usd": 0.01},
            trace_events=[{"event_type": "test"}],
        )
        assert bundle.run_id == "run_123"
        assert bundle.verified_patch == "+fixed line"
        assert bundle.verification_success is True
        assert bundle.test_summary["passed"] == 10

    def test_export_bundle_writes_file(self, tmp_path):
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        bundle = EvidenceBundle(
            run_id="run_456",
            verified_patch="patch",
            verification_success=False,
            test_summary={},
            cost_report={},
            trace_events=[],
        )
        entry = bundler.export_bundle(bundle)
        assert entry.run_id == "run_456"
        assert entry.index == 0
        bundle_file = tmp_path / "evidence_run_456.json"
        assert bundle_file.exists()

    def test_chain_is_linked_across_multiple_exports(self, tmp_path):
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        e1 = bundler.export_bundle(
            EvidenceBundle(
                run_id="r1",
                verified_patch="p1",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            )
        )
        e2 = bundler.export_bundle(
            EvidenceBundle(
                run_id="r2",
                verified_patch="p2",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            )
        )
        e3 = bundler.export_bundle(
            EvidenceBundle(
                run_id="r3",
                verified_patch="p3",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            )
        )
        assert e1.index == 0
        assert e2.index == 1
        assert e3.index == 2
        assert e2.prev_hash == e1.chain_hash
        assert e3.prev_hash == e2.chain_hash

    def test_genesis_prev_hash(self, tmp_path):
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        e1 = bundler.export_bundle(
            EvidenceBundle(
                run_id="r1",
                verified_patch="p1",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            )
        )
        expected_genesis = hashlib.sha256(b"GENESIS").hexdigest()
        assert e1.prev_hash == expected_genesis

    def test_verify_chain_passes_for_valid_chain(self, tmp_path):
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        for i in range(5):
            bundler.export_bundle(
                EvidenceBundle(
                    run_id=f"r{i}",
                    verified_patch=f"p{i}",
                    verification_success=True,
                    test_summary={},
                    cost_report={},
                    trace_events=[],
                )
            )
        ok, msg, indices = bundler.verify_chain()
        assert ok is True
        assert msg is None
        assert indices == []

    def test_verify_chain_detects_tampered_payload_hash(self, tmp_path):
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        bundler.export_bundle(
            EvidenceBundle(
                run_id="r0",
                verified_patch="p0",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            )
        )
        bundler.export_bundle(
            EvidenceBundle(
                run_id="r1",
                verified_patch="p1",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            )
        )

        chain_path = tmp_path / "evidence_chain.json"
        raw = json.loads(chain_path.read_text())
        raw[1]["payload_hash"] = "deadbeef"
        chain_path.write_text(json.dumps(raw))

        ok, msg, indices = bundler.verify_chain()
        assert ok is False
        assert 1 in indices

    def test_verify_chain_detects_tampered_prev_hash(self, tmp_path):
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        bundler.export_bundle(
            EvidenceBundle(
                run_id="r0",
                verified_patch="p0",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            )
        )
        bundler.export_bundle(
            EvidenceBundle(
                run_id="r1",
                verified_patch="p1",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            )
        )

        chain_path = tmp_path / "evidence_chain.json"
        raw = json.loads(chain_path.read_text())
        raw[1]["prev_hash"] = "0000ffff"
        chain_path.write_text(json.dumps(raw))

        ok, msg, indices = bundler.verify_chain()
        assert ok is False
        assert 1 in indices

    def test_verify_chain_detects_broken_chain_hash(self, tmp_path):
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        bundler.export_bundle(
            EvidenceBundle(
                run_id="r0",
                verified_patch="p0",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            )
        )

        chain_path = tmp_path / "evidence_chain.json"
        raw = json.loads(chain_path.read_text())
        raw[0]["chain_hash"] = "altered_hash_here"
        chain_path.write_text(json.dumps(raw))

        ok, _, indices = bundler.verify_chain()
        assert ok is False
        assert 0 in indices

    def test_verify_empty_chain_passes(self, tmp_path):
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        ok, msg, indices = bundler.verify_chain()
        assert ok is True
        assert indices == []

    def test_hmac_signature_verification(self, tmp_path):
        hmac_key = "super-secret-key"
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        bundler.export_bundle(
            EvidenceBundle(
                run_id="r0",
                verified_patch="p0",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            ),
            hmac_key=hmac_key,
        )
        bundler.export_bundle(
            EvidenceBundle(
                run_id="r1",
                verified_patch="p1",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            ),
            hmac_key=hmac_key,
        )
        ok, msg, indices = bundler.verify_chain(hmac_key=hmac_key)
        assert ok is True
        assert not indices

    def test_hmac_detects_unsigned_tamper(self, tmp_path):
        hmac_key = "secret"
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        bundler.export_bundle(
            EvidenceBundle(
                run_id="r0",
                verified_patch="p0",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            ),
            hmac_key=hmac_key,
        )

        chain_path = tmp_path / "evidence_chain.json"
        raw = json.loads(chain_path.read_text())
        raw[0]["signature"] = "bogus_signature"
        chain_path.write_text(json.dumps(raw))

        ok, _, indices = bundler.verify_chain(hmac_key=hmac_key)
        assert ok is False
        assert 0 in indices

    def test_verify_bundle_payload_matches(self, tmp_path):
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        bundle = EvidenceBundle(
            run_id="rX",
            verified_patch="real_patch",
            verification_success=True,
            test_summary={"passed": 1},
            cost_report={"total_cost_usd": 0.05},
            trace_events=[],
        )
        bundler.export_bundle(bundle)
        assert bundler.verify_bundle_payload(bundle) is True

    def test_verify_bundle_payload_detects_tamper(self, tmp_path):
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        bundle = EvidenceBundle(
            run_id="rX",
            verified_patch="real_patch",
            verification_success=True,
            test_summary={"passed": 1},
            cost_report={"total_cost_usd": 0.05},
            trace_events=[],
        )
        bundler.export_bundle(bundle)

        tampered = bundle.model_copy(update={"verified_patch": "evil_patch"})
        assert bundler.verify_bundle_payload(tampered) is False

    def test_rollback_snapshot_id_is_optional(self):
        bundler = EvidenceBundler()
        bundle = bundler.create_bundle(
            run_id="run_789",
            patch_diff="diff",
            verification_success=True,
            test_summary={},
            cost_report={},
            trace_events=[],
        )
        assert bundle.rollback_snapshot_id is None

        bundle2 = bundler.create_bundle(
            run_id="run_789",
            patch_diff="diff",
            verification_success=True,
            test_summary={},
            cost_report={},
            trace_events=[],
            rollback_snapshot_id="snap_001",
        )
        assert bundle2.rollback_snapshot_id == "snap_001"

    def test_chain_length(self, tmp_path):
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        assert bundler.chain_length() == 0
        bundler.export_bundle(
            EvidenceBundle(
                run_id="r0",
                verified_patch="p0",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            )
        )
        bundler.export_bundle(
            EvidenceBundle(
                run_id="r1",
                verified_patch="p1",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            )
        )
        assert bundler.chain_length() == 2

    def test_get_entry_by_run_id(self, tmp_path):
        bundler = EvidenceBundler(output_dir=str(tmp_path))
        bundler.export_bundle(
            EvidenceBundle(
                run_id="find_me",
                verified_patch="p",
                verification_success=True,
                test_summary={},
                cost_report={},
                trace_events=[],
            )
        )
        entry = bundler.get_entry("find_me")
        assert entry is not None
        assert entry.run_id == "find_me"

        assert bundler.get_entry("nonexistent") is None
