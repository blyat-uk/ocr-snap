from __future__ import annotations

import sys
import traceback

from dotenv import load_dotenv
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from ocr_snap import _build_info
from ocr_snap.runtime_bootstrap import (
    default_runtime_dir,
    ensure_paddle_installed,
    is_paddle_installed,
)


class _InstallWorker(QThread):
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal()
    finished_err = pyqtSignal(str)

    def __init__(self, target_dir, package):
        super().__init__()
        self._target_dir = target_dir
        self._package = package

    def run(self):
        try:
            ensure_paddle_installed(
                self._target_dir,
                self._package,
                on_progress=self.progress.emit,
            )
            self.finished_ok.emit()
        except Exception:
            self.finished_err.emit(traceback.format_exc())


def _run_first_run_install() -> bool:
    target_dir = default_runtime_dir()
    # Fast path: already installed. Still call ensure_paddle_installed so
    # sys.path gets the prepend.
    if is_paddle_installed(target_dir):
        ensure_paddle_installed(target_dir, _build_info.PADDLE_PACKAGE)
        return True

    dialog = QProgressDialog(
        "Preparing OCR engine (first run only)...", "", 0, 0
    )
    dialog.setWindowTitle("OCR Snap — First-run setup")
    dialog.setMinimumDuration(0)
    # Pip can't be safely interrupted mid-install. Remove the Cancel button
    # rather than leaving a button that does nothing useful.
    dialog.setCancelButton(None)

    worker = _InstallWorker(target_dir, _build_info.PADDLE_PACKAGE)
    result = {"ok": False, "err": ""}

    def on_progress(msg: str) -> None:
        dialog.setLabelText(msg)

    def on_ok() -> None:
        result["ok"] = True
        dialog.close()

    def on_err(msg: str) -> None:
        result["err"] = msg
        dialog.close()

    worker.progress.connect(on_progress)
    worker.finished_ok.connect(on_ok)
    worker.finished_err.connect(on_err)
    worker.start()
    dialog.exec()
    worker.wait()

    if not result["ok"]:
        msg = QMessageBox(
            QMessageBox.Icon.Critical,
            "OCR Snap — setup failed",
            "Failed to install OCR engine.",
        )
        msg.setDetailedText(result["err"])
        msg.exec()
        return False
    return True


def main() -> None:
    load_dotenv()
    app = QApplication(sys.argv)
    app.setApplicationName("OCR Snap")

    if not _run_first_run_install():
        sys.exit(1)

    # Lazy import: MUST happen after runtime_bootstrap so numpy and other
    # transitive deps resolve against the runtime install (sys.path[0]) rather
    # than the bundled PyInstaller copy.
    from ocr_snap.config import load_app_settings
    from ocr_snap.main_window import MainWindow

    settings = load_app_settings()
    window = MainWindow(settings)
    window.show()
    sys.exit(app.exec())
