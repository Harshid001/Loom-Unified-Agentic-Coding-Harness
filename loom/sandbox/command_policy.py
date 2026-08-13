"""Policy for commands produced by the agentic verification pipeline."""

from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath
from typing import Iterable, List


_SHELL_META = re.compile(r"[;&|`$<>"])
_SAFE_ARGUMENT = re.compile(r"^[A-Za-z0-9_./:@+%=-]+$")


class CommandPolicyError(ValueError):
    """Raised when a verification command violates the sandbox policy."""


def _split(command: str) -> List[str]:
    if not command or not command.strip():
        raise CommandPolicyError("Verification command is empty")
    if _SHELL_META.search(command):
        raise CommandPolicyError("Shell operators and substitutions are not permitted in verification commands")
    try:
        parts = shlex.split(command, posix=True)
    except ValueError as exc:
        raise CommandPolicyError(f"Invalid verification command syntax: {exc}") from exc
    if not parts:
        raise CommandPolicyError("Verification command is empty")
    return parts


def _safe_repo_path(value: str) -> bool:
    if value.startswith("/") or value.startswith("\\") or ".." in PurePosixPath(value).parts:
        return False
    return bool(_SAFE_ARGUMENT.fullmatch(value))


def _validate_pytest(parts: List[str]) -> None:
    allowed_flags = {"-q", "-v", "-x", "--tb=short", "--maxfail=1"}
    for arg in parts[1:]:
        if arg in allowed_flags:
            continue
        if arg.startswith("-"):
            raise CommandPolicyError(f"Pytest flag is not allowlisted: {arg}")
        if not _safe_repo_path(arg):
            raise CommandPolicyError(f"Pytest path/selector is not allowed: {arg}")


def _validate_python(parts: List[str]) -> None:
    args = parts[1:]
    if len(args) == 2 and args[0] == "-m" and args[1] in {"pytest", "unittest"}:
        return
    if len(args) == 1 and _safe_repo_path(args[0]) and args[0].endswith(".py"):
        return
    raise CommandPolicyError("Python verification is limited to -m pytest/-m unittest or a repository .py file")


def _validate_npm(parts: List[str]) -> None:
    allowed = {
        ("npm", "test"),
        ("npm", "run", "test"),
        ("npm", "run", "lint"),
        ("npm", "run", "build"),
    }
    if tuple(parts) not in allowed:
        raise CommandPolicyError(f"npm verification command is not allowlisted: {' '.join(parts)}")


def validate_verification_command(command: str) -> List[str]:
    """Parse and validate one command, returning argv suitable for shell-free execution."""
    parts = _split(command)
    executable = parts[0]
    if executable == "pytest":
        _validate_pytest(parts)
    elif executable == "python":
        _validate_python(parts)
    elif executable == "npm":
        _validate_npm(parts)
    else:
        raise CommandPolicyError(f"Executable is not allowlisted for verification: {executable}")
    return parts


def validate_verification_commands(commands: Iterable[str]) -> List[List[str]]:
    parsed: List[List[str]] = []
    for command in commands:
        parsed.append(validate_verification_command(command))
    return parsed
