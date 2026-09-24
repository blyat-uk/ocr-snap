"""What runs before anything else in `python -m ocr_snap` (Qt-free).

1. stdout/stderr: under pythonw.exe (no console) or a Finder launch there is
   nowhere for output to go; `ocr_snap.runtime.logfile` sends both to
   `<data>/logs/ocr-snap.log` (previous run kept as `.log.1`).
2. The bundle (`$OCR_SNAP_BUNDLE`) and, in a bundle, the installed OCR
   engine is activated -- before anything imports paddle.

In developer mode (no bundle) paddle comes from the environment and step 2
does nothing, so a venv's CUDA build is never shadowed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ocr_snap.runtime import activate_installed
from ocr_snap.runtime.engine import EngineState
from ocr_snap.runtime.logfile import redirect_if_needed
from ocr_snap.runtime.paths import Bundle, BundleError, current_bundle, log_file


@dataclass
class Boot:
    bundle: Bundle | None = None
    bundle_error: str | None = None
    state: EngineState | None = None        # the activated engine (bundles only)
    log_path: Path | None = None            # where stdout/stderr went, when redirected

    @property
    def bundled(self) -> bool:
        return self.bundle is not None

    @property
    def needs_engine(self) -> bool:
        return self.bundle is not None and self.state is None


def boot() -> Boot:
    result = Boot()
    try:
        result.bundle = current_bundle()
    except BundleError as exc:
        result.bundle_error = str(exc)
    result.log_path = redirect_if_needed(log_file(), discard_devnull=result.bundle is not None)
    if result.bundle is not None:
        result.state = activate_installed()
    return result


def reactivate(result: Boot) -> Boot:
    """After the setup dialog installed an engine: activate it."""
    if result.bundle is not None:
        result.state = activate_installed()
    return result
