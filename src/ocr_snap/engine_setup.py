"""The first-run "Set up the OCR engine" dialog (portable bundles only).

A bundle ships without paddle; this dialog installs it once, for this
computer. It shows the detected hardware and the offers `EngineSetup`
makes -- the recommended GPU build when one fits (with its download size),
and the CPU build -- then runs the install off the GUI thread and shows its
current step, the downloaded bytes and, on request, pip's full output. When
a GPU build does not work the installer falls back to the CPU build, and
the dialog says so and why.

States: choose -> installing -> done | failed | cancelled (back to choose).
Closing the dialog while it installs cancels the install first. The dialog
is accepted only after an engine installed; `exec()` returning Rejected
means the user left without one (the app then quits unless an engine is
still installed).

The dialog duck-types its service (signals step/progress/log/notice/
finished and hardware_text/offers/recommendation_reason/installed_text/
start/cancel/running): tests drive it with a fake that installs nothing.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QFontDatabase
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ocr_snap.runtime import gpu as gpu_mod
from ocr_snap.runtime.engine import installed_state
from ocr_snap.runtime.install import EngineInstaller, InstallContext, InstallEvent, InstallResult
from ocr_snap.runtime.paths import Bundle
from ocr_snap.theme import PrimaryButton, Tokens

TITLE = "Set up the OCR engine"
SUBTITLE = ("OCR Snap reads text with PaddleOCR. Its engine is downloaded once, "
            "for this computer's hardware.")
INSTALL_TEXT, RETRY_TEXT, CONTINUE_TEXT = "Install", "Try again", "Continue"
QUIT_TEXT, CANCEL_TEXT, CANCELLING_TEXT, CLOSE_TEXT = "Quit", "Cancel", "Cancelling…", "Close"
DETAILS_SHOW, DETAILS_HIDE = "▸ Details", "▾ Details"
PROGRESS_STEPS = 1000
MAX_LOG_LINES = 5000
CPU_BLURB = "works on every computer; slower"
GPU_BLURB = "fastest; uses the NVIDIA GPU"

_STYLE = f"""
QDialog {{ background: {Tokens.bg_base}; color: {Tokens.text_primary}; }}
QLabel {{ color: {Tokens.text_primary}; font-size: {Tokens.text_base}px; }}
QLabel#Title {{ color: {Tokens.text_emphasis}; font-size: {Tokens.text_hero}px; font-weight: 600; }}
QLabel#Muted {{ color: {Tokens.text_muted}; }}
QLabel#Message[tone="warn"] {{ color: {Tokens.alert}; }}
QLabel#Message[tone="bad"] {{ color: {Tokens.danger}; }}
QRadioButton {{ color: {Tokens.text_primary}; font-size: {Tokens.text_base}px; padding: {Tokens.sp_1}px 0; }}
QProgressBar {{ background: {Tokens.bg_raised}; border: none; border-radius: 3px; }}
QProgressBar::chunk {{ background: {Tokens.accent}; border-radius: 3px; }}
QPlainTextEdit {{
    background: {Tokens.bg_deepest}; color: {Tokens.text_muted};
    border: 1px solid {Tokens.border}; border-radius: {Tokens.r_md}px;
    font-size: {Tokens.text_mono}px;
}}
QPushButton#Ghost {{
    background: transparent; color: {Tokens.text_primary};
    border: 1px solid {Tokens.border_strong}; border-radius: {Tokens.r_md}px;
    padding: 6px 14px;
}}
QPushButton#Ghost:hover {{ background: {Tokens.bg_hover}; }}
QPushButton#Link {{ background: transparent; border: none; color: {Tokens.text_muted}; padding: 0; }}
QPushButton#Link:hover {{ color: {Tokens.text_emphasis}; }}
"""


# --------------------------------------------------------------------------
# The service: offers and one install at a time, events as Qt signals
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Offer:
    variant: str                   # "cpu" | "cu129" | ...
    title: str                     # "GPU build (CUDA 12.9)"
    size_text: str                 # "about 5.4 GB to download"
    recommended: bool = False


@dataclass(frozen=True)
class SetupOutcome:
    ok: bool
    cancelled: bool = False
    title: str = ""                # the installed build, "CPU build"
    fell_back: bool = False
    fallback_reason: str = ""
    error: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)


def size_text(size: int) -> str:
    """"about 5.4 GB to download", "about 210 MB to download"."""
    if size >= 1_000_000_000:
        return f"about {size / 1e9:.1f} GB to download"
    return f"about {size / 1e6:.0f} MB to download"


def format_bytes(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1e9:.2f} GB"
    return f"{value / 1e6:.0f} MB"


def installed_text(data: Path | None = None) -> str:
    """"GPU build (CUDA 12.9), installed 2026-09-23" or "" when none."""
    state = installed_state(data)
    if state is None:
        return ""
    text = f"{gpu_mod.variant_label(state.variant)}, installed {state.installed_at[:10]}"
    if state.fallback_reason:
        text += " (the GPU build did not work)"
    return text


class EngineSetup(QObject):
    # bytes as `object`: a Qt int is 32-bit and a GPU download is over 2 GB
    step = pyqtSignal(str, object, object)      # text, done bytes, total bytes
    progress = pyqtSignal(object, object)       # done bytes, total bytes
    log = pyqtSignal(str)
    notice = pyqtSignal(str)
    finished = pyqtSignal(object)               # SetupOutcome

    def __init__(self, bundle: Bundle, data: Path | None = None, probe: gpu_mod.GpuProbe | None = None,
                 installer_factory: Callable[[Callable[[InstallEvent], None]], EngineInstaller] | None = None,
                 parent: QObject | None = None):
        super().__init__(parent)
        self._bundle = bundle
        self._data = data
        self._probe = probe if probe is not None else gpu_mod.probe_gpus(bundle.os)
        self._choice = gpu_mod.select_variant(bundle.os, bundle.arch, self._probe)
        if installer_factory is None:
            def installer_factory(emit: Callable[[InstallEvent], None]) -> EngineInstaller:
                return EngineInstaller(InstallContext.for_bundle(bundle, data), emit=emit)
        self._installer = installer_factory(self._on_event)
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def hardware_text(self) -> str:
        return gpu_mod.describe(self._probe)

    def recommendation_reason(self) -> str:
        return self._choice.reason

    def offers(self) -> list[Offer]:
        offers = []
        if self._choice.is_gpu:
            offers.append(self._offer(self._choice.variant, recommended=True))
        offers.append(self._offer(gpu_mod.CPU, recommended=not self._choice.is_gpu))
        return offers

    def installed_text(self) -> str:
        return installed_text(self._data)

    def _offer(self, variant: str, recommended: bool) -> Offer:
        return Offer(variant, gpu_mod.variant_label(variant),
                     size_text(gpu_mod.download_bytes(variant, self._bundle.os)), recommended)

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, variant: str) -> None:
        if self.running():
            return
        self._cancel = threading.Event()
        gpu = self._choice.gpu if variant != gpu_mod.CPU else None
        self._thread = threading.Thread(target=self._work, args=(variant, gpu, self._cancel),
                                        name="engine-install", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _work(self, variant: str, gpu: gpu_mod.GpuInfo | None, cancel: threading.Event) -> None:
        try:
            result = self._installer.install(variant, gpu, cancel)
        except Exception as exc:                        # never leave the dialog waiting
            result = InstallResult(ok=False, error=f"{type(exc).__name__}: {exc}")
        self.finished.emit(_outcome(result))

    def _on_event(self, event: InstallEvent) -> None:
        if event.kind == "step":
            self.step.emit(event.text, event.done_bytes, event.total_bytes)
        elif event.kind == "progress":
            self.progress.emit(event.done_bytes, event.total_bytes)
        elif event.kind == "notice":
            self.notice.emit(event.text)
            self.log.emit(event.text)
        else:
            self.log.emit(event.text)


def _outcome(result: InstallResult) -> SetupOutcome:
    return SetupOutcome(ok=result.ok, cancelled=result.cancelled,
                        title=gpu_mod.variant_label(result.variant) if result.variant else "",
                        fell_back=result.fell_back, fallback_reason=result.fallback_reason or "",
                        error=result.error or "", warnings=tuple(result.warnings))


# --------------------------------------------------------------------------
# The dialog
# --------------------------------------------------------------------------

class EngineSetupDialog(QDialog):
    def __init__(self, setup, parent: QWidget | None = None, *, have_engine: bool = False) -> None:
        """`have_engine`: an engine is already installed (a reinstall), so
        leaving the dialog keeps it and the button says Close, not Quit."""
        super().__init__(parent)
        self._setup = setup
        self._have_engine = have_engine
        self._state = "choose"
        self._outcome: SetupOutcome | None = None
        self.setWindowTitle(f"OCR Snap — {TITLE}")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setStyleSheet(_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Tokens.sp_5, Tokens.sp_5, Tokens.sp_5, Tokens.sp_4)
        layout.setSpacing(Tokens.sp_2)

        title = QLabel(TITLE)
        title.setObjectName("Title")
        subtitle = QLabel(SUBTITLE)
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(Tokens.sp_2)

        self.hardware_label = QLabel(f"Hardware: {setup.hardware_text()}")
        installed = setup.installed_text()
        self.installed_label = QLabel(f"Installed: {installed or 'nothing yet'}")
        layout.addWidget(self.hardware_label)
        layout.addWidget(self.installed_label)
        layout.addSpacing(Tokens.sp_2)

        self._group = QButtonGroup(self)
        self.option_buttons: dict[str, QRadioButton] = {}
        for offer in setup.offers():
            blurb = CPU_BLURB if offer.variant == gpu_mod.CPU else GPU_BLURB
            head = offer.title + ("  ·  recommended" if offer.recommended else "")
            button = QRadioButton(f"{head}\n{offer.size_text} — {blurb}")
            self._group.addButton(button)
            self.option_buttons[offer.variant] = button
            layout.addWidget(button)
            if offer.recommended:
                button.setChecked(True)
        if self._group.checkedButton() is None and self.option_buttons:
            next(iter(self.option_buttons.values())).setChecked(True)
        self.reason_label = QLabel(setup.recommendation_reason())
        self.reason_label.setObjectName("Muted")
        self.reason_label.setWordWrap(True)
        layout.addWidget(self.reason_label)

        self.progress_area = QWidget()
        progress = QVBoxLayout(self.progress_area)
        progress.setContentsMargins(0, Tokens.sp_2, 0, 0)
        progress.setSpacing(Tokens.sp_1)
        self.step_label = QLabel()
        self.step_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, PROGRESS_STEPS)
        self.progress_bar.setFixedHeight(6)
        self.bytes_label = QLabel()
        self.bytes_label.setObjectName("Muted")
        progress.addWidget(self.step_label)
        progress.addWidget(self.progress_bar)
        progress.addWidget(self.bytes_label)
        self.progress_area.hide()
        layout.addWidget(self.progress_area)

        self.notice_label = QLabel()
        self.notice_label.setObjectName("Message")
        self.notice_label.setWordWrap(True)
        self.notice_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.notice_label.hide()
        layout.addWidget(self.notice_label)

        self.details_button = QPushButton(DETAILS_SHOW)
        self.details_button.setObjectName("Link")
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self._toggle_details)
        self.details_button.hide()                          # nothing to show before an install
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(MAX_LOG_LINES)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.log_view.setMinimumHeight(160)
        self.log_view.hide()
        layout.addWidget(self.details_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.log_view, 1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, Tokens.sp_3, 0, 0)
        buttons.addStretch(1)
        self.cancel_button = QPushButton(CLOSE_TEXT if have_engine else QUIT_TEXT)
        self.cancel_button.setObjectName("Ghost")
        self.cancel_button.clicked.connect(self._cancel_clicked)
        self.install_button = PrimaryButton(INSTALL_TEXT)
        self.install_button.clicked.connect(self._install_clicked)
        self.install_button.setDefault(True)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.install_button)
        layout.addLayout(buttons)

        setup.step.connect(self._on_step)
        setup.progress.connect(self._on_progress)
        setup.log.connect(self._on_log)
        setup.notice.connect(self._on_notice)
        setup.finished.connect(self._on_finished)

    # -- state ------------------------------------------------------------

    def state(self) -> str:
        return self._state

    def selected(self) -> str | None:
        return next((v for v, b in self.option_buttons.items() if b.isChecked()), None)

    def outcome(self) -> SetupOutcome | None:
        return self._outcome

    def select(self, variant: str) -> None:
        if self._state not in ("installing", "done") and variant in self.option_buttons:
            self.option_buttons[variant].setChecked(True)

    def _set_state(self, state: str) -> None:
        self._state = state
        installing = state == "installing"
        for button in self.option_buttons.values():
            button.setEnabled(not installing and state != "done")
        self.install_button.setEnabled(not installing)
        if state == "done":
            self.install_button.setText(CONTINUE_TEXT)
            self.cancel_button.hide()
        elif state == "failed":
            self.install_button.setText(RETRY_TEXT)
        else:
            self.install_button.setText(INSTALL_TEXT)
        if installing:
            self.cancel_button.setText(CANCEL_TEXT)
            self.cancel_button.setEnabled(True)
        elif state != "done":
            self.cancel_button.setText(CLOSE_TEXT if self._have_engine else QUIT_TEXT)
            self.cancel_button.setEnabled(True)
            self.cancel_button.show()

    def _message(self, text: str, tone: str) -> None:
        self.notice_label.setText(text)
        self.notice_label.setProperty("tone", tone)
        style = self.notice_label.style()
        if style is not None:
            style.unpolish(self.notice_label)
            style.polish(self.notice_label)
        self.notice_label.setVisible(bool(text))

    # -- buttons ----------------------------------------------------------

    def _install_clicked(self) -> None:
        if self._state == "done":
            self.accept()
            return
        variant = self.selected()
        if self._state == "installing" or variant is None:
            return
        self._message("", "warn")
        self.log_view.clear()
        self.details_button.show()
        self.progress_area.show()
        self.step_label.setText("Starting")
        self.bytes_label.setText("")
        self.progress_bar.setRange(0, 0)
        self._set_state("installing")
        self._setup.start(variant)

    def _cancel_clicked(self) -> None:
        if self._state == "installing":
            self.cancel_button.setText(CANCELLING_TEXT)
            self.cancel_button.setEnabled(False)
            self._setup.cancel()
            return
        self.reject()

    def _toggle_details(self, shown: bool) -> None:
        self.log_view.setVisible(shown)
        self.details_button.setText(DETAILS_HIDE if shown else DETAILS_SHOW)
        self.adjustSize()

    # -- installer events -------------------------------------------------

    def _on_step(self, text: str, done: int, total: int) -> None:
        self.step_label.setText(text)
        self._on_progress(done, total)

    def _on_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self.progress_bar.setRange(0, 0)                 # busy: no byte count for this step
            self.bytes_label.setText("")
            return
        self.progress_bar.setRange(0, PROGRESS_STEPS)
        self.progress_bar.setValue(min(PROGRESS_STEPS, int(PROGRESS_STEPS * done / total)))
        self.bytes_label.setText(f"{format_bytes(done)} of about {format_bytes(total)}")

    def _on_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def _on_notice(self, text: str) -> None:
        self._message(text, "warn")

    def _on_finished(self, outcome: SetupOutcome) -> None:
        self._outcome = outcome
        self.progress_bar.setRange(0, PROGRESS_STEPS)
        if outcome.ok:
            self.progress_bar.setValue(PROGRESS_STEPS)
            self.bytes_label.setText("")
            self.step_label.setText(f"Installed: {outcome.title}")
            notes = []
            if outcome.fell_back:
                notes.append(f"The GPU build did not work on this computer, so the CPU build was installed "
                             f"instead. OCR will be slower.\nReason: {outcome.fallback_reason}")
            notes.extend(outcome.warnings)
            self._message("\n\n".join(notes), "warn")
            self._set_state("done")
        elif outcome.cancelled:
            self.progress_area.hide()
            self._message("Cancelled. Nothing was changed.", "warn")
            self._set_state("cancelled")
        else:
            self.progress_bar.setValue(0)
            self.bytes_label.setText("")
            self.step_label.setText("The install failed")
            self._message(outcome.error + ("\n\nDetails has pip's full output." if outcome.error else ""), "bad")
            self._set_state("failed")

    # -- closing ----------------------------------------------------------

    def reject(self) -> None:
        """Esc / the window's close button: an install is cancelled first,
        and the dialog closes when it has stopped."""
        if self._state == "installing":
            self._cancel_clicked()
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if self._state == "installing" and event is not None:
            event.ignore()
            self._cancel_clicked()
            return
        super().closeEvent(event)
