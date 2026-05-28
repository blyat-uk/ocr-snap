"""Bottom toolbar widget for image adjustments.

Visual model: every control is a pill button (icon + label). Toggle pills
flip their amber "on" state via Qt's `:checked` pseudo-class. Slider pills
open a popover on click — see ``_SliderPopover`` (Task 4) and ``_SliderPill``
(Task 5). The full ``AdjustToolbar`` widget (Tasks 6-7) wires everything
together and mirrors the previous ``AdjustPanel``'s public signal contract.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ocr_snap.theme import Tokens


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
