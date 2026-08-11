from loom.verification.runner import (
    SASTSeverity,
    VerificationDecision,
    VerificationRunner,
)


class FakeSandbox:
    def __init__(self, exit_codes=None):
        self._codes = exit_codes or {}
        self._counter = {}
        self.commands = []

    def run_command(self, cmd, cwd=None, timeout=60, env=None):
        self.commands.append(cmd)
        for prefix, code in self._codes.items():
            if cmd.startswith(prefix):
                count = self._counter.get(cmd, 0) + 1
                self._counter[cmd] = count
                if isinstance(code, list):
                    idx = min(count - 1, len(code) - 1)
                    actual_code = code[idx]
                else:
                    actual_code = code
                from loom.sandbox.base import CommandResult
                return CommandResult(
                    command=cmd, exit_code=actual_code,
                    stdout="ok" if actual_code == 0 else "FAILED",
                    stderr="",
                    duration_seconds=0.1,
                )
        from loom.sandbox.base import CommandResult
        return CommandResult(command=cmd, exit_code=0, stdout="ok", stderr="", duration_seconds=0.1)

    def create_snapshot(self, label):
        return label

    def restore_snapshot(self, snapshot_id):
        return True


class TestVerificationRunner:
    def test_build_failure_stops_early(self):
        sandbox = FakeSandbox({"build": 1})
        runner = VerificationRunner(sandbox)
        result = runner.run_verification(["pytest"], build_command="build")
        assert not result.build_passed
        assert result.decision == VerificationDecision.REJECT_BUILD_FAILURE

    def test_tests_pass_returns_success(self):
        sandbox = FakeSandbox({"pytest": 0})
        runner = VerificationRunner(sandbox)
        result = runner.run_verification(["pytest"])
        assert result.tests_passed
        assert result.overall_success

    def test_linter_failure_still_reports(self):
        sandbox = FakeSandbox({"pytest": 0, "lint": 1})
        runner = VerificationRunner(sandbox)
        result = runner.run_verification(["pytest"], lint_command="lint")
        assert not result.linter_passed
        assert not result.overall_success


class TestReproductionEvaluation:
    def test_flip_confirmed(self):
        sandbox = FakeSandbox({"pre_test": 1, "post_test": 0})
        runner = VerificationRunner(sandbox)
        repro = runner.evaluate_reproduction("test.py", ["pre_test"], ["post_test"])
        assert repro.failed_on_base
        assert repro.passed_after_patch
        assert repro.flip_confirmed

    def test_no_flip_when_pre_passes(self):
        sandbox = FakeSandbox({"pre_test": 0, "post_test": 0})
        runner = VerificationRunner(sandbox)
        repro = runner.evaluate_reproduction("test.py", ["pre_test"], ["post_test"])
        assert not repro.flip_confirmed

    def test_no_flip_when_post_fails(self):
        sandbox = FakeSandbox({"pre_test": 1, "post_test": 1})
        runner = VerificationRunner(sandbox)
        repro = runner.evaluate_reproduction("test.py", ["pre_test"], ["post_test"])
        assert not repro.flip_confirmed


class TestSASTCheck:
    def test_clean_diff_no_findings(self):
        runner = VerificationRunner(FakeSandbox())
        findings = runner.run_sast_check("+x = 1\n+y = 2")
        assert len(findings) == 0

    def test_critical_pattern_detected(self):
        runner = VerificationRunner(FakeSandbox())
        findings = runner.run_sast_check("+password = 'admin123'")
        assert len(findings) > 0
        assert any(f.severity == SASTSeverity.CRITICAL for f in findings)

    def test_shell_true_is_critical(self):
        runner = VerificationRunner(FakeSandbox())
        findings = runner.run_sast_check("+subprocess.call(cmd, shell=true)")
        crits = [f for f in findings if f.severity == SASTSeverity.CRITICAL]
        assert len(crits) > 0

    def test_eval_is_high(self):
        runner = VerificationRunner(FakeSandbox())
        findings = runner.run_sast_check("+result = eval(user_input)")
        highs = [f for f in findings if f.severity == SASTSeverity.HIGH]
        assert len(highs) > 0

    def test_empty_diff_has_no_findings(self):
        runner = VerificationRunner(FakeSandbox())
        findings = runner.run_sast_check("")
        assert findings == []


class TestConfidenceScoring:
    def test_perfect_scenario(self):
        runner = VerificationRunner(FakeSandbox())
        score = runner.compute_confidence(
            repro_flip_confirmed=True,
            diff_line_count=5,
            historical_pattern_match=1.0,
            model_self_reported_certainty=1.0,
        )
        assert score > 0.9

    def test_no_repro_low_confidence(self):
        runner = VerificationRunner(FakeSandbox())
        score = runner.compute_confidence(
            repro_flip_confirmed=False,
            diff_line_count=5,
            historical_pattern_match=0.5,
            model_self_reported_certainty=0.5,
        )
        assert score < 0.6

    def test_large_diff_penalty(self):
        runner = VerificationRunner(FakeSandbox())
        good = runner.compute_confidence(True, 10, 0.5, 0.5)
        bad = runner.compute_confidence(True, 200, 0.5, 0.5)
        assert good > bad

    def test_zero_diff_gets_neutral(self):
        runner = VerificationRunner(FakeSandbox())
        score = runner.compute_confidence(True, 0, 0.5, 0.5)
        assert 0.4 < score < 0.8

    def test_model_certainty_weighted_least(self):
        runner = VerificationRunner(FakeSandbox())
        high_certainty = runner.compute_confidence(True, 10, 0.5, 1.0)
        low_certainty = runner.compute_confidence(True, 10, 0.5, 0.0)
        assert high_certainty > low_certainty


class TestDecisionMatrix:
    def test_auto_merge_when_confident(self):
        runner = VerificationRunner(FakeSandbox(), auto_merge_threshold=0.95)
        decision = runner.evaluate_decision(
            build_passed=True,
            tests_passed=True,
            repro_flip_confirmed=True,
            sast_severity=SASTSeverity.CLEAN,
            confidence_score=0.97,
        )
        assert decision == VerificationDecision.AUTO_MERGE

    def test_human_review_when_below_threshold(self):
        runner = VerificationRunner(FakeSandbox(), auto_merge_threshold=0.95)
        decision = runner.evaluate_decision(
            build_passed=True,
            tests_passed=True,
            repro_flip_confirmed=True,
            sast_severity=SASTSeverity.CLEAN,
            confidence_score=0.90,
        )
        assert decision == VerificationDecision.HUMAN_REVIEW

    def test_security_hold_on_critical(self):
        runner = VerificationRunner(FakeSandbox())
        decision = runner.evaluate_decision(
            build_passed=True,
            tests_passed=True,
            repro_flip_confirmed=True,
            sast_severity=SASTSeverity.CRITICAL,
            confidence_score=0.99,
        )
        assert decision == VerificationDecision.SECURITY_HOLD

    def test_security_hold_on_high(self):
        runner = VerificationRunner(FakeSandbox())
        decision = runner.evaluate_decision(
            build_passed=True,
            tests_passed=True,
            repro_flip_confirmed=True,
            sast_severity=SASTSeverity.HIGH,
            confidence_score=0.99,
        )
        assert decision == VerificationDecision.SECURITY_HOLD

    def test_reject_repro_missing(self):
        runner = VerificationRunner(FakeSandbox())
        decision = runner.evaluate_decision(
            build_passed=True,
            tests_passed=True,
            repro_flip_confirmed=False,
            sast_severity=SASTSeverity.CLEAN,
            confidence_score=0.95,
        )
        assert decision == VerificationDecision.REJECT_REPRO_MISSING

    def test_reject_regression(self):
        runner = VerificationRunner(FakeSandbox())
        decision = runner.evaluate_decision(
            build_passed=True,
            tests_passed=False,
            repro_flip_confirmed=True,
            sast_severity=SASTSeverity.CLEAN,
            confidence_score=0.95,
        )
        assert decision == VerificationDecision.REJECT_REGRESSION

    def test_reject_build_failure(self):
        runner = VerificationRunner(FakeSandbox())
        decision = runner.evaluate_decision(
            build_passed=False,
            tests_passed=True,
            repro_flip_confirmed=True,
            sast_severity=SASTSeverity.CLEAN,
            confidence_score=0.99,
        )
        assert decision == VerificationDecision.REJECT_BUILD_FAILURE

    def test_threshold_cannot_go_below_floor(self):
        runner = VerificationRunner(FakeSandbox(), auto_merge_threshold=0.70)
        assert runner.auto_merge_threshold == 0.85

    def test_medium_sast_does_not_trigger_hold(self):
        runner = VerificationRunner(FakeSandbox())
        decision = runner.evaluate_decision(
            build_passed=True,
            tests_passed=True,
            repro_flip_confirmed=True,
            sast_severity=SASTSeverity.MEDIUM,
            confidence_score=0.97,
        )
        assert decision == VerificationDecision.AUTO_MERGE


class TestFullPipeline:
    def test_pipeline_returns_result_and_repro(self):
        sandbox = FakeSandbox({"pytest": 0, "pre": 1, "post": 0})
        runner = VerificationRunner(sandbox, auto_merge_threshold=0.90)
        v_result, repro = runner.full_verification_pipeline(
            test_commands=["pytest"],
            repro_script="test_repro.py",
            pre_patch_test_commands=["pre"],
            post_patch_test_commands=["post"],
            diff_text="+x = 1\n+y = 2",
            historical_pattern_match=1.0,
            model_self_reported_certainty=1.0,
        )
        assert v_result.decision == VerificationDecision.AUTO_MERGE
        assert repro.flip_confirmed
        assert v_result.confidence_score >= 0.90

    def test_pipeline_security_hold(self):
        sandbox = FakeSandbox({"pytest": 0, "pre": 1, "post": 0})
        runner = VerificationRunner(sandbox)
        v_result, repro = runner.full_verification_pipeline(
            test_commands=["pytest"],
            repro_script="test.py",
            pre_patch_test_commands=["pre"],
            post_patch_test_commands=["post"],
            diff_text="+password = 'hardcoded_secret'",
        )
        assert v_result.decision == VerificationDecision.SECURITY_HOLD
        assert v_result.sast_severity == SASTSeverity.CRITICAL

    def test_pipeline_build_failure(self):
        sandbox = FakeSandbox({"build": 1, "pytest": 0, "pre": 1, "post": 0})
        runner = VerificationRunner(sandbox)
        v_result, repro = runner.full_verification_pipeline(
            test_commands=["pytest"],
            repro_script="test.py",
            pre_patch_test_commands=["pre"],
            post_patch_test_commands=["post"],
            diff_text="+x = 1",
            build_command="build",
        )
        assert v_result.decision == VerificationDecision.REJECT_BUILD_FAILURE


class TestAutoRollback:
    def test_recent_merge_ci_failure_triggers(self):
        runner = VerificationRunner(FakeSandbox())
        assert runner.should_auto_rollback(
            merge_time=__import__("time").time(),
            ci_failure_detected=True,
            monitor_timeout_seconds=3600,
        )

    def test_old_merge_no_rollback(self):
        runner = VerificationRunner(FakeSandbox())
        old_time = __import__("time").time() - 7200
        assert not runner.should_auto_rollback(
            merge_time=old_time,
            ci_failure_detected=True,
            monitor_timeout_seconds=3600,
        )

    def test_no_ci_failure_no_rollback(self):
        runner = VerificationRunner(FakeSandbox())
        assert not runner.should_auto_rollback(
            merge_time=__import__("time").time(),
            ci_failure_detected=False,
            monitor_timeout_seconds=3600,
        )