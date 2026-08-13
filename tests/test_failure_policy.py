from loom.runtime.failure_policy import FailureClass, classify_failure, should_retry


def test_security_failure_is_not_retried():
    error = RuntimeError("security sandbox policy denied execution")
    assert classify_failure(error) == FailureClass.SECURITY
    assert should_retry(error) is False


def test_timeout_is_retried():
    error = TimeoutError("provider timed out")
    assert classify_failure(error) == FailureClass.TRANSIENT
    assert should_retry(error) is True
