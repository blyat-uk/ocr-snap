"""`python -m ocr_snap` / `ocr-snap`: the OCR Snap window.

Startup order (`main`): `ocr_snap.bootstrap.boot()` first -- stdout/stderr
to the log file when there is no console, then the bundle's OCR engine
activated before anything imports paddle -- then the flags:

- `--version` prints the version and exits.
- `--self-test`, `--install-engine {auto,cpu,gpu}`, `--ocr-smoke`: headless
  CI modes, see `ocr_snap/cli.py` for what they do and their exit codes.
- `--setup-engine` opens the engine setup dialog even when an engine is
  installed (bundles only; a note and the window in developer mode).
- `--quit-after SECONDS` closes the window after that long (the smoke
  test's hook).

In a bundle without an installed engine the setup dialog
(`ocr_snap/engine_setup.py`) comes first; leaving it without an engine
quits. The main window is imported only after that. In developer mode
paddle comes from the environment (the `ocr` / `ocr-gpu` extras).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ocr_snap.bootstrap import Boot, boot, reactivate
from ocr_snap.version import __version__

APP_NAME = "OCR Snap"
ICON_FILE = Path(__file__).resolve().parent / "resources" / "app-icon.png"


def _program_name() -> str:
    """How this run was started, for --help."""
    name = os.path.basename(sys.argv[0]) if sys.argv else ""
    return "python -m ocr_snap" if name in ("", "__main__.py", "main.py") else name


def _parse(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(prog=_program_name(), description=APP_NAME)
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    parser.add_argument("--setup-engine", action="store_true",
                        help="open the OCR engine setup (install, reinstall or switch GPU/CPU)")
    parser.add_argument("--self-test", action="store_true", help="headless checks, JSON report (CI)")
    parser.add_argument("--install-engine", choices=("auto", "cpu", "gpu"), default=None,
                        help="install the OCR engine without a window (CI)")
    parser.add_argument("--ocr-smoke", action="store_true", help="OCR one rendered line and exit (CI)")
    parser.add_argument("--quit-after", type=float, default=None, help=argparse.SUPPRESS)
    return parser.parse_known_args(argv)


def run_engine_setup(started: Boot) -> bool:
    """The engine setup dialog; True when an engine is installed afterwards."""
    from PyQt6.QtWidgets import QDialog

    from ocr_snap.engine_setup import EngineSetup, EngineSetupDialog

    assert started.bundle is not None
    setup = EngineSetup(started.bundle)
    dialog = EngineSetupDialog(setup, have_engine=started.state is not None)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    setup.cancel()
    setup.wait(60)
    dialog.deleteLater()
    if accepted:
        reactivate(started)
    return started.state is not None


def main(argv: list[str] | None = None) -> int:
    started = boot()
    args, qt_args = _parse(sys.argv[1:] if argv is None else list(argv))
    if args.version:
        print(__version__, flush=True)
        return 0
    if args.self_test or args.install_engine or args.ocr_smoke:
        from ocr_snap import cli

        if args.self_test:
            return cli.self_test(started)
        if args.install_engine:
            return cli.install_engine(started, args.install_engine)
        return cli.ocr_smoke(started)

    from dotenv import load_dotenv
    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication, QMessageBox

    load_dotenv()
    app = QApplication([sys.argv[0] if sys.argv else "ocr-snap", *qt_args])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    if ICON_FILE.is_file():
        app.setWindowIcon(QIcon(str(ICON_FILE)))

    if started.bundle_error:
        QMessageBox.critical(None, f"{APP_NAME} — broken installation",
                             f"{started.bundle_error}\n\nReinstall {APP_NAME}.")
        return 1
    if started.bundled and (started.needs_engine or args.setup_engine):
        if not run_engine_setup(started):
            return 1
    elif args.setup_engine:
        print("--setup-engine: developer mode (no $OCR_SNAP_BUNDLE), paddle comes from this environment",
              file=sys.stderr)

    # Imported only now: nothing may import paddle before the engine is active.
    from ocr_snap.config import load_app_settings
    from ocr_snap.main_window import MainWindow

    window = MainWindow(load_app_settings())
    window.show()
    if args.quit_after is not None:
        def quit_now() -> None:
            window.close()
            app.quit()

        QTimer.singleShot(max(0, int(args.quit_after * 1000)), quit_now)
    return app.exec()
