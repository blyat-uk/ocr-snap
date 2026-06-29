"""Emit PyInstaller ``--hidden-import`` flags for the whole standard library.

The release binary ships WITHOUT paddle/paddleocr and pip-installs them into a
user-data dir at first run (see ``ocr_snap.runtime_bootstrap``). Those packages
— and their deep dependency tree (pandas, pydantic, paddlex, ...) — then run on
the *frozen* PyInstaller interpreter. PyInstaller only bundles the stdlib
modules that its statically-analyzed bundled deps import, so any stdlib module
the runtime-installed packages need but the frozen app does not (e.g.
``zoneinfo``, imported at module level by both pandas and pydantic) is absent,
surfacing as ``ModuleNotFoundError: No module named '<mod>'`` when the OCR
engine loads.

Forcing the entire stdlib in as hidden imports closes that gap once, instead of
chasing one missing module at a time. Must run on the target OS (CI builds each
flavor on its own runner) so ``sys.stdlib_module_names`` matches the platform.

Usage (in .github/workflows/release.yml):
    STDLIB_HIDDEN=$(python tools/stdlib_hidden_imports.py)
    pyinstaller ... $STDLIB_HIDDEN src/ocr_snap/__main__.py
"""
from __future__ import annotations

import sys

# Skipped because they are huge, GUI-only, joke/demo modules, or already passed
# to PyInstaller as --exclude-module. tkinter (and its dependents idlelib /
# turtle / turtledemo) pull in Tk, which the Qt app never uses and the build
# deliberately excludes. Underscore-prefixed accelerators (_zoneinfo, _ssl, ...)
# are filtered separately — their public wrappers pull them in transitively.
SKIP = frozenset(
    {
        "antigravity",
        "this",
        "tkinter",
        "turtle",
        "turtledemo",
        "idlelib",
        "lib2to3",
        "test",
        "pydoc_data",
        "ensurepip",
    }
)


def hidden_import_args() -> list[str]:
    """Return ``--hidden-import=NAME`` tokens for every public stdlib module."""
    names = sorted(
        name
        for name in sys.stdlib_module_names
        if not name.startswith("_") and name not in SKIP
    )
    return [f"--hidden-import={name}" for name in names]


def main(argv: list[str]) -> int:
    print(" ".join(hidden_import_args()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
