"""Pytest configuration. Ensures WAVEOS_LICENSE_KEY is set for CLI and integration tests."""

import os
import sys
from pathlib import Path

# Ensure src/ is on path so "waveos" is importable when the package isn't installed (e.g. fresh .venv).
_repo_root = Path(__file__).resolve().parents[1]
_src = _repo_root / "src"
if _src.exists() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))
# So subprocesses (waveos entry point, python -m waveos.cli) find the package too.
if _src.exists():
    _prev = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = str(_src) + (os.pathsep + _prev if _prev else "")

# Use CI/test license key so subprocess CLI invocations (e.g. test_cli_e2e) pass license check.
# CI already sets this; local runs get it here.
if "WAVEOS_LICENSE_KEY" not in os.environ and "WAVEOS_LICENSE_SKIP" not in os.environ:
    os.environ["WAVEOS_LICENSE_KEY"] = "WAVEOS-CI-20991231-TEST"
