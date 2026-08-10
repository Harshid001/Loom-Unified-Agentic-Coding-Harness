from typing import List, Optional

from pydantic import BaseModel, Field

from loom.sandbox.base import BaseSandbox


class TestResult(BaseModel):
    test_command: str
    passed: bool
    stdout: str
    stderr: str
    duration_seconds: float
    flaky_suspected: bool = False

class VerificationResult(BaseModel):
    build_passed: bool
    tests_passed: bool
    linter_passed: bool
    overall_success: bool
    test_results: List[TestResult] = Field(default_factory=list)
    failure_reason: Optional[str] = None

class VerificationRunner:
    """Runs build, tests, linters, and baseline regression checks."""

    def __init__(self, sandbox: BaseSandbox):
        self.sandbox = sandbox

    def run_verification(
        self,
        test_commands: List[str],
        build_command: Optional[str] = None,
        lint_command: Optional[str] = None
    ) -> VerificationResult:
        build_passed = True
        tests_passed = True
        linter_passed = True
        results: List[TestResult] = []
        failure_reason = None

        # 1. Run build command if defined
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
                    failure_reason=failure_reason
                )

        # 2. Run linter command if defined
        if lint_command:
            l_res = self.sandbox.run_command(lint_command)
            if l_res.exit_code != 0:
                linter_passed = False

        # 3. Run test commands
        for cmd in test_commands:
            t_res = self.sandbox.run_command(cmd)
            passed = (t_res.exit_code == 0)
            if not passed:
                tests_passed = False
                if not failure_reason:
                    failure_reason = f"Test failed: {cmd}\n{t_res.stderr or t_res.stdout}"

            results.append(TestResult(
                test_command=cmd,
                passed=passed,
                stdout=t_res.stdout,
                stderr=t_res.stderr,
                duration_seconds=t_res.duration_seconds
            ))

        overall = build_passed and tests_passed and linter_passed
        return VerificationResult(
            build_passed=build_passed,
            tests_passed=tests_passed,
            linter_passed=linter_passed,
            overall_success=overall,
            test_results=results,
            failure_reason=failure_reason
        )
