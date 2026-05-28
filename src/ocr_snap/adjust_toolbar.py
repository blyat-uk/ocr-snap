"""Bottom toolbar widget for image adjustments.

Visual model: every control is a pill button (icon + label). Toggle pills
flip their amber "on" state via Qt's `:checked` pseudo-class. Slider pills
open a popover on click — see ``_SliderPopover`` (Task 4) and ``_SliderPill``
(Task 5). The full ``AdjustToolbar`` widget (Tasks 6-7) wires everything
together and mirrors the previous ``AdjustPanel``'s public signal contract.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QPushButton, QWidget

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
