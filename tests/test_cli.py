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
