from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "stdlib_hidden_imports.py"


def _run() -> list[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def test_emits_zoneinfo() -> None:
    # The reported crash: pandas/pydantic (runtime-installed paddleocr deps)
    # import zoneinfo, which the frozen interpreter lacks. It MUST be bundled.
    assert "--hidden-import=zoneinfo" in _run()


def test_every_token_is_a_hidden_import_flag() -> None:
    assert all(tok.startswith("--hidden-import=") for tok in _run())


def test_skips_excluded_and_private_modules() -> None:
    tokens = _run()
    # Excluded in the PyInstaller invocation; bundling them here would conflict
    # or pull in Tk / the CPython test suite.
    for skipped in ("tkinter", "test", "pydoc_data", "idlelib"):
        assert f"--hidden-import={skipped}" not in tokens
    # Underscore accelerators are pulled transitively by their public wrappers.
    assert not any(tok.startswith("--hidden-import=_") for tok in tokens)


def test_includes_common_runtime_stdlib_gaps() -> None:
    # Modules paddleocr's dependency tree can reach that the Qt-only frozen app
    # would not otherwise bundle.
    tokens = set(_run())
    for mod in ("lzma", "bz2", "sqlite3", "decimal"):
        assert f"--hidden-import={mod}" in tokens
