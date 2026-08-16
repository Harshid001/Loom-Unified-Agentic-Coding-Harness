import tempfile

from typer.testing import CliRunner

from loom.cli.main import app

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Loom CLI" in result.stdout


def test_cli_init():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(app, ["init", "--path", tmpdir])
        assert result.exit_code == 0
        assert "Repository Intelligence Map" in result.stdout
        assert "Repository successfully intaken" in result.stdout


def test_cli_issue_and_run():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set issue
        issue_res = runner.invoke(app, ["issue", "Fix null pointer in auth handler", "--path", tmpdir])
        assert issue_res.exit_code == 0
        assert "Active Issue Set" in issue_res.stdout

        # Execute run
        run_res = runner.invoke(app, ["run", "--mock"])
        assert run_res.exit_code == 0
        assert "Loom Harness Execution Complete" in run_res.stdout
        assert "Cost Report" in run_res.stdout


def test_cli_trace():
    # Test trace command with non-existent run ID
    result = runner.invoke(app, ["trace", "nonexistent_run_999"])
    assert result.exit_code == 1
    assert "Trace file not found" in result.stdout


def test_cli_rollback():
    # Test rollback command with non-existent checkpoint
    result = runner.invoke(app, ["rollback", "nonexistent_run_999"])
    assert result.exit_code == 1
    assert "Checkpoint file not found" in result.stdout


def test_cli_bench():
    result = runner.invoke(app, ["bench"])
    assert result.exit_code == 0
    assert "Controlled Ablation Matrix Benchmark" in result.stdout
    assert "baseline_naive" in result.stdout


def test_cli_fix():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(app, ["fix", "Resolve memory leak issue", "--path", tmpdir, "--mock"])
        assert result.exit_code == 0
        assert "Repository Intelligence Map" in result.stdout
        assert "Active Issue Set" in result.stdout
        assert "Loom Harness Execution Complete" in result.stdout


def test_cli_token_commands(tmp_path, monkeypatch):
    from loom.auth.api_tokens import reset_api_token_store

    reset_api_token_store()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # 1. Create token
    create_res = runner.invoke(app, ["token-create", "--label", "test_cli_key", "--user-id", "cli_user"])
    assert create_res.exit_code == 0
    assert "Loom API Key Generated" in create_res.stdout

    # Extract token_id from stdout output (e.g. "Token ID │ tok_...")
    import re

    match = re.search(r"tok_[a-f0-9]+", create_res.stdout)
    assert match is not None
    token_id = match.group(0)

    # 2. List tokens
    list_res = runner.invoke(app, ["token-list"])
    assert list_res.exit_code == 0
    assert "Active Loom API Keys" in list_res.stdout
    assert "test_cli_key" in list_res.stdout

    # 3. Revoke token
    revoke_res = runner.invoke(app, ["token-revoke", token_id])
    assert revoke_res.exit_code == 0
    assert "Successfully revoked API key" in revoke_res.stdout



