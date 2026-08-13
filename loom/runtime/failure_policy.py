"""Failure classification and retry policy for autonomous run execution."""

from __future__ import annotations

from enum import Enum


class FailureClass(str, Enum):
    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    SANDBOX = "sandbox"
    PATCH_CONFLICT = "patch_conflict"
    SECURITY = "security"
    CONFIGURATION = "configuration"
    INVALID_INPUT = "invalid_input"
    UNKNOWN = "unknown"


NON_RETRYABLE = {FailureClass.SECURITY, FailureClass.CONFIGURATION, FailureClass.INVALID_INPUT}


def classify_failure(error: BaseException) -> FailureClass:
    message = str(error).lower()
    name = type(error).__name__.lower()
    if "security" in message or "forbidden" in message or "permission" in message:
        return FailureClass.SECURITY
    if "config" in message or "environment" in message or "required" in message:
        return FailureClass.CONFIGURATION
    if "invalid" in message or "validation" in message:
        return FailureClass.INVALID_INPUT
    if "rate limit" in message or "429" in message or "ratelimit" in name:
        return FailureClass.RATE_LIMIT
    if "sandbox" in message or "microvm" in message or "firecracker" in message:
        return FailureClass.SANDBOX
    if "conflict" in message or ("patch" in message and "apply" in message):
        return FailureClass.PATCH_CONFLICT
    if any(token in message for token in ("timeout", "timed out", "connection", "temporarily", "unavailable", "503")):
        return FailureClass.TRANSIENT
    return FailureClass.UNKNOWN


def should_retry(error: BaseException) -> bool:
    return classify_failure(error) not in NON_RETRYABLE
