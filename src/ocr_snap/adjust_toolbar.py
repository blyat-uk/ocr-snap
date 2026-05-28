"""Bottom toolbar widget for image adjustments.

Visual model: every control is a pill button (icon + label). Toggle pills
flip their amber "on" state via Qt's `:checked` pseudo-class. Slider pills
open a popover on click — see ``_SliderPopover`` (Task 4) and ``_SliderPill``
(Task 5). The full ``AdjustToolbar`` widget (Tasks 6-7) wires everything
together and mirrors the previous ``AdjustPanel``'s public signal contract.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Literal

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ocr_snap.models import Adjustments
from ocr_snap.theme import Icons, Tokens


# Local "active" palette — evokes the canvas scan-line / OCR-processing
# amber so an "on" pill reads as "this affects the OCR run". Kept local
# to the toolbar so theme.Tokens (blue accent for general UI) is untouched.
_ON_BG = "rgba(212, 168, 67, 0.18)"
_ON_BORDER = "#d4a843"
_ON_TEXT = "#f0d28a"

_PILL_STYLE = f"""
QPushButton {{
    background: {Tokens.bg_raised};
    border: 1px solid {Tokens.border};
    border-radius: {Tokens.r_pill}px;
    color: {Tokens.text_muted};
    padding: 4px 10px;
    font-size: {Tokens.text_base}px;
    text-align: left;
}}
QPushButton:hover {{
    border-color: {Tokens.border_strong};
}}
QPushButton:checked,
QPushButton[on="true"] {{
    background: {_ON_BG};
    border-color: {_ON_BORDER};
    color: {_ON_TEXT};
}}
QPushButton:disabled {{
    color: {Tokens.text_muted};
}}
"""


IconFactory = Callable[..., QIcon]


class _Pill(QPushButton):
    """Base pill button: icon + label, with an amber 'on' state.

    The icon swaps between an idle (muted) and active (amber) variant when
    ``set_active`` is called. Stylesheet handles the background/border/text
    changes via the ``on`` dynamic property and the ``:checked`` pseudo-class.
    """

    def __init__(
        self,
        icon_factory: IconFactory,
        label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(label, parent)
        self._idle_icon = icon_factory(color=Tokens.text_muted)
        self._active_icon = icon_factory(color=_ON_BORDER)
        self.setIcon(self._idle_icon)
        self.setIconSize(QSize(14, 14))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(_PILL_STYLE)
        self.setProperty("on", False)
        self._active = False

    def icon(self) -> QIcon:  # type: ignore[override]
        """Return the cached QIcon instance so callers can use ``is`` identity."""
        return self._active_icon if self._active else self._idle_icon

    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        if active == self._active:
            return
        self._active = active
        self.setProperty("on", active)
        self.setIcon(self._active_icon if active else self._idle_icon)
        # Re-evaluate the stylesheet after a property change.
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)


class _TogglePill(_Pill):
    """Checkable pill — used for boolean Adjustments fields and the Auto
    toggle. The amber 'on' state is driven by the ``:checked`` selector in
    the stylesheet AND mirrored on the ``on`` dynamic property so it composes
    with ``_SliderPill``'s value-driven active state.
    """

    def __init__(
        self,
        icon_factory: IconFactory,
        label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(icon_factory, label, parent)
        self.setCheckable(True)
        self.toggled.connect(self.set_active)


_POPOVER_STYLE = f"""
QWidget#SliderPopover {{
    background: {Tokens.bg_raised};
    border: 1px solid {Tokens.border_strong};
    border-radius: {Tokens.r_md}px;
}}
QLabel {{ background: transparent; border: none; }}
QLabel#PopTitle {{ color: {Tokens.text_muted}; font-size: {Tokens.text_base}px; }}
QLabel#PopReset {{ color: {Tokens.text_muted}; font-size: {Tokens.text_eyebrow}px; text-decoration: underline; }}
QLabel#PopReset:hover {{ color: {_ON_TEXT}; }}
QLabel#PopValue {{ color: {_ON_TEXT}; font-size: {Tokens.text_lg}px; font-weight: 700; }}
QLabel#PopEndpoint {{ color: {Tokens.text_muted}; font-size: {Tokens.text_eyebrow}px; }}
QSlider::groove:horizontal {{
    background: {Tokens.border}; height: 4px; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {_ON_BORDER}; width: 12px; height: 12px;
    margin: -4px 0; border-radius: 6px;
}}
"""


class _ResetLabel(QLabel):
    """A QLabel that emits ``clicked`` on left-mouse release. Cheaper than a
    QPushButton for an inline link and styles cleanly via the popover sheet."""

    clicked = pyqtSignal()

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class _SliderPopover(QWidget):
    """Floating popup containing a slider for a single adjustment value.

    Constructed with the value's range, default, current value, and a
    formatter that turns an int slider value into a display string. Emits
    ``value_changed(int)`` on every slider tick. ``_reset_to_default``
    snaps the slider back via ``QSlider.setValue``, which fires
    ``value_changed`` only when the current value differs from the default
    (Qt's setter is a no-op when the value is already correct).
    """

    value_changed = pyqtSignal(int)

    def __init__(
        self,
        *,
        title: str,
        min_val: int,
        max_val: int,
        default: int,
        current: int,
        value_text: Callable[[int], str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("SliderPopover")
        self._default = default
        self._value_text = value_text
        self.setStyleSheet(_POPOVER_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("PopTitle")
        header.addWidget(title_lbl)
        header.addStretch()
        self._reset_lbl = _ResetLabel(f"Reset to {value_text(default)}")
        self._reset_lbl.setObjectName("PopReset")
        self._reset_lbl.clicked.connect(self._reset_to_default)
        header.addWidget(self._reset_lbl)
        root.addLayout(header)

        self._value_label = QLabel(value_text(current))
        self._value_label.setObjectName("PopValue")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._value_label)

        track_row = QHBoxLayout()
        track_row.setSpacing(8)
        lo_lbl = QLabel(value_text(min_val))
        lo_lbl.setObjectName("PopEndpoint")
        track_row.addWidget(lo_lbl)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(min_val, max_val)
        self._slider.setValue(current)
        self._slider.valueChanged.connect(self._on_slider_changed)
        track_row.addWidget(self._slider, stretch=1)
        hi_lbl = QLabel(value_text(max_val))
        hi_lbl.setObjectName("PopEndpoint")
        track_row.addWidget(hi_lbl)
        root.addLayout(track_row)

        self.setFixedWidth(240)

    def _on_slider_changed(self, value: int) -> None:
        self._value_label.setText(self._value_text(value))
        self.value_changed.emit(value)

    def _reset_to_default(self) -> None:
        self._slider.setValue(self._default)

    def value(self) -> int:
        return self._slider.value()


class _SliderPill(_Pill):
    """A pill that opens a slider popover on click. The pill's inline
    label shows the base name when at default, or "name value" otherwise.
    """

    value_changed = pyqtSignal(int)

    def __init__(
        self,
        icon_factory: IconFactory,
        label: str,
        *,
        min_val: int,
        max_val: int,
        default: int,
        value_text: Callable[[int], str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(icon_factory, label, parent)
        self._base_label = label
        self._min = min_val
        self._max = max_val
        self._default = default
        self._value_text = value_text
        self._value = default
        self._popover: _SliderPopover | None = None
        self.clicked.connect(self._open_popover)
        self._refresh()

    def value(self) -> int:
        return self._value

    def set_value(self, value: int) -> None:
        value = max(self._min, min(self._max, int(value)))
        if value == self._value:
            return
        self._value = value
        self._refresh()
        self.value_changed.emit(value)
        if self._popover is not None:
            # Keep the popover's slider in sync if it's open while an
            # external update arrives (e.g. set_adjustments).
            self._popover._slider.blockSignals(True)
            self._popover._slider.setValue(value)
            self._popover._slider.blockSignals(False)
            self._popover._value_label.setText(self._value_text(value))

    def _refresh(self) -> None:
        active = self._value != self._default
        self.set_active(active)
        if active:
            self.setText(f"{self._base_label} {self._value_text(self._value)}")
        else:
            self.setText(self._base_label)

    def _open_popover(self) -> None:
        if self._popover is not None and self._popover.isVisible():
            self._popover.close()
            return
        # Reuse the popover across open/close cycles — Qt parents it to the
        # pill and keeps it alive, so allocating a fresh one each time would
        # accumulate orphaned children.
        if self._popover is None:
            self._popover = _SliderPopover(
                title=self._base_label,
                min_val=self._min,
                max_val=self._max,
                default=self._default,
                current=self._value,
                value_text=self._value_text,
                parent=self,
            )
            self._popover.value_changed.connect(self._on_popover_value)
        else:
            # Sync the cached popover to the current value before re-showing.
            self._popover._slider.blockSignals(True)
            self._popover._slider.setValue(self._value)
            self._popover._slider.blockSignals(False)
            self._popover._value_label.setText(self._value_text(self._value))
        pop = self._popover
        # Position above the pill, horizontally centered. Clamp y so the
        # popover stays visible if the pill is near the top of the screen.
        pop.adjustSize()
        pill_top_left = self.mapToGlobal(self.rect().topLeft())
        x = pill_top_left.x() + (self.width() - pop.width()) // 2
        y = max(0, pill_top_left.y() - pop.height() - 6)
        pop.move(x, y)
        pop.show()

    def _on_popover_value(self, value: int) -> None:
        # Pop-driven update — drive the pill (which emits value_changed).
        if value == self._value:
            return
        self._value = value
        self._refresh()
        self.value_changed.emit(value)


_INDICATOR_STYLE = f"""
QLabel#AdjIndicator {{
    color: {_ON_TEXT};
    font-size: {Tokens.text_eyebrow}px;
    background: transparent;
    border: none;
    padding: 0 4px;
}}
"""


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setStyleSheet(f"color: {Tokens.border};")
    return line


# Slider value formatters — int → str. Kept as module-level functions so
# tests / debugging can refer to them by name if needed.
def _fmt_degrees(v: int) -> str:
    return f"{v}°"


def _fmt_percent_delta(v: int) -> str:
    # Brightness / Contrast: 100 = identity (1.0 factor), shown as +/- delta.
    return f"{v - 100:+d}%"


def _fmt_percent(v: int) -> str:
    return f"{v}%"


class AdjustToolbar(QWidget):
    """Bottom toolbar containing every image-adjustment control as a pill.

    Three logical groups: Image and OCR are separated by a vertical
    divider; Actions are pinned right by an addStretch() gap.
      Image (live-preview):  Rotate · Brightness · Contrast · Sharpen ·
                              Grayscale · Invert · Binarize
      OCR (next-run):        Upscale · Smart fix · Sensitivity
      Actions:               Crop · Reset · Auto · Run OCR

    Mirrors AdjustPanel's signal contract; adds ``auto_ocr_toggled(bool)``
    for the new Auto pill. The Adjustments value object is built from the
    live pill values — Auto is intentionally NOT part of Adjustments (it's
    a UI mode).
    """

    adjustments_changed = pyqtSignal(Adjustments)
    run_ocr_requested = pyqtSignal()
    reset_requested = pyqtSignal()
    crop_mode_toggled = pyqtSignal(bool)
    auto_ocr_toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._adj = Adjustments()
        self._loading = False

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 6)
        root.setSpacing(6)

        # ── Image group ──
        self._rotation = _SliderPill(
            Icons.rotate, "Rotate",
            min_val=-180, max_val=180, default=0, value_text=_fmt_degrees,
        )
        self._brightness = _SliderPill(
            Icons.brightness, "Brightness",
            min_val=20, max_val=200, default=100, value_text=_fmt_percent_delta,
        )
        self._contrast = _SliderPill(
            Icons.contrast, "Contrast",
            min_val=20, max_val=200, default=100, value_text=_fmt_percent_delta,
        )
        self._sharpen = _SliderPill(
            Icons.sharpen, "Sharpen",
            min_val=0, max_val=200, default=0, value_text=_fmt_percent,
        )
        self._grayscale = _TogglePill(Icons.grayscale, "Grayscale")
        self._invert = _TogglePill(Icons.invert, "Invert")
        self._binarize = _TogglePill(Icons.binarize, "Binarize")
        for pill in (
            self._rotation, self._brightness, self._contrast, self._sharpen,
            self._grayscale, self._invert, self._binarize,
        ):
            root.addWidget(pill)

        root.addWidget(_divider())

        # ── OCR group ──
        self._upscale = _TogglePill(Icons.upscale, "Upscale")
        self._smart_fix = _TogglePill(Icons.smart_fix, "Smart fix")
        self._sensitivity = _SliderPill(
            Icons.sensitivity, "Sensitivity",
            min_val=0, max_val=100, default=0, value_text=_fmt_percent,
        )
        for pill in (self._upscale, self._smart_fix, self._sensitivity):
            root.addWidget(pill)

        root.addStretch()

        # ── Actions group ──
        self._indicator = QLabel("")
        self._indicator.setObjectName("AdjIndicator")
        self._indicator.setStyleSheet(_INDICATOR_STYLE)
        self._indicator.hide()
        root.addWidget(self._indicator)

        self._crop_btn = _TogglePill(Icons.crop, "Crop")
        self._reset_btn = _Pill(Icons.reset, "Reset")
        self._auto_btn = _TogglePill(Icons.auto_ocr, "Auto")
        self._run_btn = _Pill(Icons.run_ocr, "Run OCR")
        # Run OCR is the primary CTA — always-amber.
        self._run_btn.set_active(True)
        for btn in (self._crop_btn, self._reset_btn, self._auto_btn, self._run_btn):
            root.addWidget(btn)

        # Wiring — every parameter pill rebuilds Adjustments on change.
        for pill in (
            self._rotation, self._brightness, self._contrast, self._sharpen,
            self._sensitivity,
        ):
            pill.value_changed.connect(self._on_control_changed)
        for pill in (
            self._grayscale, self._invert, self._binarize,
            self._upscale, self._smart_fix,
        ):
            pill.toggled.connect(self._on_control_changed)

        self._crop_btn.toggled.connect(self.crop_mode_toggled.emit)
        self._reset_btn.clicked.connect(self.reset_requested.emit)
        self._auto_btn.toggled.connect(self.auto_ocr_toggled.emit)
        self._run_btn.clicked.connect(self.run_ocr_requested.emit)

    # ── State ────────────────────────────────────────────────────────

    def _adjustments_from_widgets(
        self, crop: tuple[float, float, float, float] | None
    ) -> Adjustments:
        """Build Adjustments from the current pill values. Crop is passed
        through (managed separately via ``set_crop`` in Task 7)."""
        return Adjustments(
            rotation=float(self._rotation.value()),
            crop=crop,
            brightness=self._brightness.value() / 100.0,
            contrast=self._contrast.value() / 100.0,
            grayscale=self._grayscale.isChecked(),
            invert=self._invert.isChecked(),
            binarize=self._binarize.isChecked(),
            sharpen=self._sharpen.value() / 100.0,
            upscale=self._upscale.isChecked(),
            det_sensitivity=self._sensitivity.value() / 100.0,
            smart_fix=self._smart_fix.isChecked(),
        )

    def _on_control_changed(self, *_args: object) -> None:
        if self._loading:
            return
        self._adj = self._adjustments_from_widgets(self._adj.crop)
        self.adjustments_changed.emit(self._adj)

    def current_adjustments(self) -> Adjustments:
        return dataclasses.replace(self._adj)

    def set_crop(self, crop: tuple[float, float, float, float] | None) -> None:
        if self._adj.crop == crop:
            # No-op: same crop already set. Skip the emission so the
            # coordinator doesn't re-render the preview for nothing.
            return
        self._adj = dataclasses.replace(self._adj, crop=crop)
        if self._crop_btn.isChecked():
            self._crop_btn.blockSignals(True)
            self._crop_btn.setChecked(False)
            self._crop_btn.blockSignals(False)
        self.adjustments_changed.emit(self._adj)

    def set_crop_active(self, active: bool) -> None:
        """Sync the Crop pill to the canvas's actual crop-mode state without
        re-emitting ``crop_mode_toggled``."""
        if self._crop_btn.isChecked() != active:
            self._crop_btn.blockSignals(True)
            self._crop_btn.setChecked(active)
            self._crop_btn.blockSignals(False)

    def set_adjustments(self, adj: Adjustments) -> None:
        """Load state into the controls without emitting ``adjustments_changed``.
        The internal Adjustments is then rebuilt from the (integer-quantized)
        widget values so it never diverges from what the widgets hold."""
        self._loading = True
        try:
            for pill, value in (
                (self._rotation, int(round(adj.rotation))),
                (self._brightness, int(round(adj.brightness * 100))),
                (self._contrast, int(round(adj.contrast * 100))),
                (self._sharpen, int(round(adj.sharpen * 100))),
                (self._sensitivity, int(round(adj.det_sensitivity * 100))),
            ):
                pill.set_value(value)
            for box, checked in (
                (self._grayscale, adj.grayscale),
                (self._invert, adj.invert),
                (self._binarize, adj.binarize),
                (self._upscale, adj.upscale),
                (self._smart_fix, adj.smart_fix),
            ):
                box.blockSignals(True)
                box.setChecked(checked)
                box.blockSignals(False)
            self._crop_btn.blockSignals(True)
            self._crop_btn.setChecked(False)
            self._crop_btn.blockSignals(False)
            self._adj = self._adjustments_from_widgets(adj.crop)
        finally:
            self._loading = False

    def set_indicator(self, state: Literal["none", "adjusted", "running"]) -> None:
        """Set the right-side indicator chip: hidden, "● Adjusted", or "● Running…"."""
        if state == "none":
            self._indicator.hide()
            self._indicator.setText("")
        elif state == "adjusted":
            self._indicator.setText("● Adjusted")
            self._indicator.show()
        elif state == "running":
            self._indicator.setText("● Running…")
            self._indicator.show()
        else:
            raise ValueError(f"invalid indicator state: {state!r}")
