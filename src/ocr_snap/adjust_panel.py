"""The 'Adjust image' panel: controls that mutate an Adjustments object
and emit signals for the coordinator to apply preview / OCR / reset.

The panel owns the editable Adjustments for the active image. The
coordinator calls ``set_adjustments`` on image switch and ``set_crop``
when the canvas reports a crop selection. Every control change emits
``adjustments_changed`` with the current Adjustments.
"""

from __future__ import annotations

import dataclasses

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ocr_snap.models import Adjustments
from ocr_snap.theme import Tokens

_LABEL_STYLE = (
    f"color: {Tokens.text_muted}; font-size: {Tokens.text_base}px; "
    f"background: transparent; border: none;"
)
_CHECK_STYLE = (
    f"QCheckBox {{ color: {Tokens.text_primary}; font-size: {Tokens.text_base}px; "
    f"background: transparent; border: none; }}"
    f"QCheckBox::indicator {{ width: 14px; height: 14px; }}"
    f"QCheckBox::indicator:unchecked {{ border: 1px solid {Tokens.border_strong}; "
    f"border-radius: 2px; background: transparent; }}"
    f"QCheckBox::indicator:checked {{ border: 1px solid {Tokens.accent}; "
    f"border-radius: 2px; background: {Tokens.accent}; }}"
)
_SLIDER_STYLE = (
    f"QSlider::groove:horizontal {{ background: {Tokens.border}; height: 4px; border-radius: 2px; }}"
    f"QSlider::handle:horizontal {{ background: {Tokens.text_muted}; width: 12px; height: 12px; "
    f"margin: -4px 0; border-radius: 6px; }}"
    f"QSlider::handle:horizontal:hover {{ background: {Tokens.accent}; }}"
)


class AdjustPanel(QWidget):
    adjustments_changed = pyqtSignal(Adjustments)
    run_ocr_requested = pyqtSignal()
    reset_requested = pyqtSignal()
    crop_mode_toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._adj = Adjustments()
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 6, 14, 6)
        root.setSpacing(6)

        header = QLabel("Adjust image")
        header.setStyleSheet(
            f"font-size: {Tokens.text_base}px; font-weight: bold; "
            f"color: {Tokens.text_muted}; background: transparent; border: none;"
        )
        root.addWidget(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        row = 0

        self._rotation = self._add_slider(grid, row, "Rotate", -180, 180, 0)
        row += 1
        self._brightness = self._add_slider(grid, row, "Brightness", 20, 200, 100)
        row += 1
        self._contrast = self._add_slider(grid, row, "Contrast", 20, 200, 100)
        row += 1
        self._sharpen = self._add_slider(grid, row, "Sharpen", 0, 200, 0)
        row += 1
        self._sensitivity = self._add_slider(grid, row, "Det. sensitivity", 0, 100, 0)
        row += 1
        root.addLayout(grid)

        checks = QHBoxLayout()
        self._grayscale = self._add_check(checks, "Grayscale")
        self._invert = self._add_check(checks, "Invert")
        self._binarize = self._add_check(checks, "Binarize")
        checks.addStretch()
        root.addLayout(checks)

        checks2 = QHBoxLayout()
        self._upscale = self._add_check(checks2, "Upscale")
        self._smart_fix = self._add_check(checks2, "Smart fix")
        checks2.addStretch()
        root.addLayout(checks2)

        crop_row = QHBoxLayout()
        self._crop_btn = QPushButton("Crop")
        self._crop_btn.setCheckable(True)
        self._crop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._crop_btn.toggled.connect(self.crop_mode_toggled.emit)
        crop_row.addWidget(self._crop_btn)
        self._clear_crop_btn = QPushButton("Clear crop")
        self._clear_crop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_crop_btn.clicked.connect(lambda: self.set_crop(None))
        crop_row.addWidget(self._clear_crop_btn)
        crop_row.addStretch()
        root.addLayout(crop_row)

        actions = QHBoxLayout()
        self._run_btn = QPushButton("Run OCR")
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.clicked.connect(self.run_ocr_requested.emit)
        actions.addWidget(self._run_btn)
        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.clicked.connect(self.reset_requested.emit)
        actions.addWidget(self._reset_btn)
        actions.addStretch()
        root.addLayout(actions)

    # ── construction helpers ─────────────────────────────────────────

    def _add_slider(
        self, grid: QGridLayout, row: int, label: str, lo: int, hi: int, value: int
    ) -> QSlider:
        text = QLabel(label)
        text.setStyleSheet(_LABEL_STYLE)
        grid.addWidget(text, row, 0)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(value)
        slider.setStyleSheet(_SLIDER_STYLE)
        slider.valueChanged.connect(self._on_control_changed)
        grid.addWidget(slider, row, 1)
        return slider

    def _add_check(self, layout: QHBoxLayout, label: str) -> QCheckBox:
        box = QCheckBox(label)
        box.setStyleSheet(_CHECK_STYLE)
        box.toggled.connect(self._on_control_changed)
        layout.addWidget(box)
        return box

    # ── state ────────────────────────────────────────────────────────

    def _adjustments_from_widgets(
        self, crop: tuple[float, float, float, float] | None
    ) -> Adjustments:
        """Build Adjustments from the current widget values. The widgets are
        the source of truth for the editable fields; ``crop`` is managed
        separately (via ``set_crop``) and passed through."""
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

    def set_crop_active(self, active: bool) -> None:
        """Sync the crop button to the canvas's actual crop-mode state (e.g.
        the canvas auto-exits crop mode after a selection). Does not re-emit
        ``crop_mode_toggled``."""
        if self._crop_btn.isChecked() != active:
            self._crop_btn.blockSignals(True)
            self._crop_btn.setChecked(active)
            self._crop_btn.blockSignals(False)

    def set_crop(self, crop: tuple[float, float, float, float] | None) -> None:
        self._adj = dataclasses.replace(self._adj, crop=crop)
        if self._crop_btn.isChecked():
            self._crop_btn.blockSignals(True)
            self._crop_btn.setChecked(False)
            self._crop_btn.blockSignals(False)
        self.adjustments_changed.emit(self._adj)

    def set_adjustments(self, adj: Adjustments) -> None:
        """Load state into the controls without emitting adjustments_changed."""
        self._loading = True
        try:
            for widget, value in (
                (self._rotation, int(round(adj.rotation))),
                (self._brightness, int(round(adj.brightness * 100))),
                (self._contrast, int(round(adj.contrast * 100))),
                (self._sharpen, int(round(adj.sharpen * 100))),
                (self._sensitivity, int(round(adj.det_sensitivity * 100))),
            ):
                widget.blockSignals(True)
                widget.setValue(value)
                widget.blockSignals(False)
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
            # The crop button reflects "rubber-band mode active", not whether a
            # crop exists, so it always resets on load.
            self._crop_btn.blockSignals(True)
            self._crop_btn.setChecked(False)
            self._crop_btn.blockSignals(False)
            # Rebuild _adj from the (integer-quantized) widget values so the
            # internal state never diverges from what the widgets hold.
            self._adj = self._adjustments_from_widgets(adj.crop)
        finally:
            self._loading = False
