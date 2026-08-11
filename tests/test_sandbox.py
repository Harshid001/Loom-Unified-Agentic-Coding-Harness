from loom.sandbox.local_process import LocalProcessSandbox


def test_local_sandbox(tmp_path):
    sandbox = LocalProcessSandbox(str(tmp_path))
    res = sandbox.run_command("python -c \"print('hello')\"")
    assert res.exit_code == 0
    assert "hello" in res.stdout


def test_cross_instance_rollback(tmp_path):
    test_file = tmp_path / "app.py"
    test_file.write_text("original content", encoding="utf-8")

    # Instance 1: Create snapshot
    sandbox1 = LocalProcessSandbox(str(tmp_path))
    snap_id = sandbox1.create_snapshot("test_snap")

    # Mutate file
    test_file.write_text("mutated content", encoding="utf-8")
    assert test_file.read_text(encoding="utf-8") == "mutated content"

    # Instance 2: Restore snapshot across fresh instance/process boundary
    sandbox2 = LocalProcessSandbox(str(tmp_path))
    success = sandbox2.restore_snapshot(snap_id)

    assert success is True
    assert test_file.read_text(encoding="utf-8") == "original content"
