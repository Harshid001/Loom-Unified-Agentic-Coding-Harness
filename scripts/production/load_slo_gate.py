"""Production entry point for Load & SLO Gate validation."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "load_slo_gate.py"
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    runpy.run_path(str(script_path), run_name="__main__")


if __name__ == "__main__":
    main()
