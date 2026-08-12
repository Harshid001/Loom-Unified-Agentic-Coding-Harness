from enum import Enum
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from loom.sandbox.base import BaseSandbox


class SASTSeverity(str, Enum):
    CLEAN = "clean"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SASTFinding(BaseModel):
    rule_id: str
    severity: SASTSeverity
    file_path: str
    line: int
    message: str


class TestResult(BaseModel):
    test_command: str
    passed: bool
    stdout: str
    stderr: str
    duration_seconds: float
    flaky_suspected: bool = False


class ReproductionEvidence(BaseModel):
    test_script: str
    failed_on_base: bool = False
    passed_after_patch: bool = False
    flip_confirmed: bool = False


class VerificationDecision(str, Enum):
    AUTO_MERGE = "auto_merge"
    HUMAN_REVIEW = "human_review"
    REJECT_REPRO_MISSING = "reject_repro_missing"
    REJECT_REGRESSION = "reject_regression"
    REJECT_BUILD_FAILURE = "reject_build_failure"
    SECURITY_HOLD = "security_hold"


class VerificationResult(BaseModel):
    build_passed: bool
    tests_passed: bool
    linter_passed: bool
    sast_severity: SASTSeverity = SASTSeverity.CLEAN
    repro_flip_confirmed: bool = False
    overall_success: bool
    test_results: List[TestResult] = Field(default_factory=list)
    sast_findings: List[SASTFinding] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    confidence_score: float = 0.0
    decision: VerificationDecision = VerificationDecision.HUMAN_REVIEW
    diff_line_count: int = 0
    model_self_reported_certainty: float = 0.0


CONFIDENCE_WEIGHTS = {
    "repro_test_strength": 0.40,
    "diff_minimality": 0.30,
    "historical_pattern_match": 0.20,
    "model_self_reported_certainty": 0.10,
}

AUTO_MERGE_THRESHOLD_MIN = 0.85
AUTO_MERGE_THRESHOLD_DEFAULT = 0.95


class VerificationRunner:
    def __init__(self, sandbox: BaseSandbox, auto_merge_threshold: float = AUTO_MERGE_THRESHOLD_DEFAULT):
        self.sandbox = sandbox
        self.auto_merge_threshold = max(auto_merge_threshold, AUTO_MERGE_THRESHOLD_MIN)

    def run_verification(
        self,
        test_commands: List[str],
        build_command: Optional[str] = None,
        lint_command: Optional[str] = None,
    ) -> VerificationResult:
        build_passed = True
        tests_passed = True
        linter_passed = True
        results: List[TestResult] = []
        failure_reason: Optional[str] = None

        if build_command:
            b_res = self.sandbox.run_command(build_command)
            if b_res.exit_code != 0:
                build_passed = False
                failure_reason = f"Build command failed: {b_res.stderr or b_res.stdout}"
                return VerificationResult(
                    build_passed=False,
                    tests_passed=False,
                    linter_passed=True,
                    overall_success=False,
                    failure_reason=failure_reason,
                    decision=VerificationDecision.REJECT_BUILD_FAILURE,
                )

        if lint_command:
            l_res = self.sandbox.run_command(lint_command)
            if l_res.exit_code != 0:
                linter_passed = False

        for cmd in test_commands:
            t_res = self.sandbox.run_command(cmd)
            passed = t_res.exit_code == 0
            if not passed:
                tests_passed = False
                if not failure_reason:
                    failure_reason = f"Test failed: {cmd}\n{t_res.stderr or t_res.stdout}"

            results.append(
                TestResult(
                    test_command=cmd,
                    passed=passed,
                    stdout=t_res.stdout,
                    stderr=t_res.stderr,
                    duration_seconds=t_res.duration_seconds,
                )
            )

        overall = build_passed and tests_passed and linter_passed
        return VerificationResult(
            build_passed=build_passed,
            tests_passed=tests_passed,
            linter_passed=linter_passed,
            overall_success=overall,
            test_results=results,
            failure_reason=failure_reason,
            decision=VerificationDecision.HUMAN_REVIEW if overall else VerificationDecision.REJECT_REGRESSION,
        )

    def evaluate_reproduction(
        self,
        repro_script: str,
        pre_patch_test_commands: List[str],
        post_patch_test_commands: List[str],
    ) -> ReproductionEvidence:
        failed_on_base = False
        for cmd in pre_patch_test_commands:
            res = self.sandbox.run_command(cmd)
            if res.exit_code != 0:
                failed_on_base = True
                break

        passed_after = True
        for cmd in post_patch_test_commands:
            res = self.sandbox.run_command(cmd)
            if res.exit_code != 0:
                passed_after = False
                break

        flip = failed_on_base and passed_after

        return ReproductionEvidence(
            test_script=repro_script,
            failed_on_base=failed_on_base,
            passed_after_patch=passed_after,
            flip_confirmed=flip,
        )

    def run_sast_check(self, diff_text: str) -> List[SASTFinding]:
        findings: List[SASTFinding] = []
        diff_lower = diff_text.lower()

        secrets_patterns = [
            ("SAST-001", "api_key", SASTSeverity.CRITICAL),
            ("SAST-002", "password", SASTSeverity.CRITICAL),
            ("SAST-003", "secret", SASTSeverity.CRITICAL),
            ("SAST-004", "token", SASTSeverity.HIGH),
            ("SAST-005", "eval(", SASTSeverity.HIGH),
            ("SAST-006", "exec(", SASTSeverity.HIGH),
            ("SAST-007", "subprocess", SASTSeverity.MEDIUM),
            ("SAST-008", "os.system", SASTSeverity.MEDIUM),
            ("SAST-009", "shell=true", SASTSeverity.CRITICAL),
            ("SAST-010", "unsafe", SASTSeverity.LOW),
        ]

        for rule_id, pattern, severity in secrets_patterns:
            if pattern in diff_lower:
                findings.append(
                    SASTFinding(
                        rule_id=rule_id,
                        severity=severity,
                        file_path="<diff>",
                        line=0,
                        message=f"Potential {severity.value}-severity issue: '{pattern}' found in diff",
                    )
                )

        return findings

    def compute_confidence(
        self,
        repro_flip_confirmed: bool,
        diff_line_count: int,
        historical_pattern_match: float,
        model_self_reported_certainty: float,
    ) -> float:
        repro_score = 1.0 if repro_flip_confirmed else 0.0

        if diff_line_count <= 0:
            diff_score = 0.5
        elif diff_line_count <= 20:
            diff_score = 1.0
        elif diff_line_count <= 50:
            diff_score = 0.8
        elif diff_line_count <= 100:
            diff_score = 0.6
        elif diff_line_count <= 150:
            diff_score = 0.4
        else:
            diff_score = 0.2

        historical = max(0.0, min(1.0, historical_pattern_match))
        model_certainty = max(0.0, min(1.0, model_self_reported_certainty))

        return (
            CONFIDENCE_WEIGHTS["repro_test_strength"] * repro_score
            + CONFIDENCE_WEIGHTS["diff_minimality"] * diff_score
            + CONFIDENCE_WEIGHTS["historical_pattern_match"] * historical
            + CONFIDENCE_WEIGHTS["model_self_reported_certainty"] * model_certainty
        )

    def evaluate_decision(
        self,
        build_passed: bool,
        tests_passed: bool,
        repro_flip_confirmed: bool,
        sast_severity: SASTSeverity,
        confidence_score: float,
    ) -> VerificationDecision:
        if sast_severity in (SASTSeverity.HIGH, SASTSeverity.CRITICAL):
            return VerificationDecision.SECURITY_HOLD

        if not build_passed:
            return VerificationDecision.REJECT_BUILD_FAILURE

        if not repro_flip_confirmed:
            return VerificationDecision.REJECT_REPRO_MISSING

        if not tests_passed:
            return VerificationDecision.REJECT_REGRESSION

        if confidence_score >= self.auto_merge_threshold:
            return VerificationDecision.AUTO_MERGE

        return VerificationDecision.HUMAN_REVIEW

    def full_verification_pipeline(
        self,
        test_commands: List[str],
        repro_script: str,
        pre_patch_test_commands: List[str],
        post_patch_test_commands: List[str],
        diff_text: str,
        build_command: Optional[str] = None,
        lint_command: Optional[str] = None,
        historical_pattern_match: float = 0.5,
        model_self_reported_certainty: float = 0.5,
    ) -> Tuple[VerificationResult, ReproductionEvidence]:
        v_result = self.run_verification(test_commands, build_command, lint_command)

        repro = self.evaluate_reproduction(repro_script, pre_patch_test_commands, post_patch_test_commands)

        sast_findings = self.run_sast_check(diff_text)
        sast_severity = SASTSeverity.CLEAN
        for f in sast_findings:
            if f.severity == SASTSeverity.CRITICAL:
                sast_severity = SASTSeverity.CRITICAL
                break
            if f.severity == SASTSeverity.HIGH and sast_severity in (
                SASTSeverity.CLEAN,
                SASTSeverity.LOW,
                SASTSeverity.MEDIUM,
            ):
                sast_severity = SASTSeverity.HIGH
            elif f.severity == SASTSeverity.MEDIUM and sast_severity in (SASTSeverity.CLEAN, SASTSeverity.LOW):
                sast_severity = SASTSeverity.MEDIUM
            elif f.severity == SASTSeverity.LOW and sast_severity == SASTSeverity.CLEAN:
                sast_severity = SASTSeverity.LOW

        diff_line_count = len(diff_text.strip().split("\n")) if diff_text else 0
        confidence = self.compute_confidence(
            repro.flip_confirmed,
            diff_line_count,
            historical_pattern_match,
            model_self_reported_certainty,
        )

        decision = self.evaluate_decision(
            v_result.build_passed,
            v_result.tests_passed,
            repro.flip_confirmed,
            sast_severity,
            confidence,
        )

        v_result.repro_flip_confirmed = repro.flip_confirmed
        v_result.sast_severity = sast_severity
        v_result.sast_findings = sast_findings
        v_result.confidence_score = confidence
        v_result.decision = decision
        v_result.diff_line_count = diff_line_count
        v_result.model_self_reported_certainty = model_self_reported_certainty

        return v_result, repro

    def should_auto_rollback(
        self,
        merge_time: float,
        ci_failure_detected: bool,
        monitor_timeout_seconds: int = 3600,
    ) -> bool:
        from loom.business.post_merge import auto_rollback_triggered

        return auto_rollback_triggered(merge_time, ci_failure_detected, monitor_timeout_seconds)
