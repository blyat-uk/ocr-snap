"""Keyword arguments every child process the app starts is given.

The packaged Windows build runs under pythonw.exe, which has no console, so
Windows gives each console program it starts (pip, nvidia-smi) a console
window of its own that flashes up for the child's lifetime.
CREATE_NO_WINDOW starts it without one; no other platform needs anything.

Every child that reads text also passes TEXT_ENCODING: text mode otherwise
decodes with the locale's encoding (cp1252 on Windows).
"""
from __future__ import annotations

import subprocess
import sys
from typing import Any

# subprocess.CREATE_NO_WINDOW's value; the constant only exists on Windows.
_CREATE_NO_WINDOW = 0x08000000

TEXT_ENCODING: dict[str, Any] = {"encoding": "utf-8", "errors": "replace"}


def hidden_child() -> dict[str, Any]:
    """subprocess.run()/Popen() kwargs that start a child without a console
    window on Windows; empty everywhere else."""
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", _CREATE_NO_WINDOW)}
    return {}
