from pathlib import Path

import pytest

from loom.sandbox.firecracker_guest_agent import _safe_extract


def test_guest_agent_extract_blocks_absolute_and_parent_paths(tmp_path: Path):
    import tarfile

    archive = tmp_path / "bad.tar"
    source = tmp_path / "source"
    source.mkdir()
    (source / "ok.txt").write_text("ok")
    with tarfile.open(archive, "w") as tar:
        tar.add(source / "ok.txt", arcname="../escape.txt")

    with pytest.raises(ValueError):
        _safe_extract(archive, tmp_path / "out")


def test_guest_agent_extract_blocks_symlink_members(tmp_path: Path):
    import io
    import tarfile

    archive = tmp_path / "symlink.tar"
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("escape")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)

    with pytest.raises(ValueError):
        _safe_extract(archive, tmp_path / "out")
