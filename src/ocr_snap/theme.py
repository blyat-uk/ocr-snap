"""Centralized design tokens, icon factories, and reusable widget
subclasses. Ported from sub-label-pos with OCR Snap-specific
additions.
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget

import qtawesome as qta


@dataclass(frozen=True)
class _Tokens:
    # --- Color (ported verbatim from sub-label-pos) ---
    bg_deepest: str = "#0f1114"
    bg_base: str = "#14161a"
    bg_surface: str = "#1a1c20"
    bg_raised: str = "#1f2226"
    bg_hover: str = "#2a2d33"
    border: str = "#2d3036"
    border_strong: str = "#3a3d44"
    text_muted: str = "#888888"
    text_primary: str = "#d8d8d8"
    text_emphasis: str = "#ffffff"
    accent: str = "#4a9eff"
    accent_deep: str = "#1f5fa6"
    alert: str = "#ffcc55"
    danger: str = "#ff8a8a"
    success: str = "#8ad08a"
    overlay: str = "rgba(0,0,0,0.85)"

    # --- Spacing (px) ---
    sp_1: int = 4
    sp_2: int = 8
    sp_3: int = 12
    sp_4: int = 16
    sp_5: int = 24
    sp_6: int = 36

    # --- Radii (px) ---
    r_sm: int = 3
    r_md: int = 6
    r_lg: int = 10
    r_pill: int = 13

    # --- Type sizes (px) ---
    text_hero: int = 22
    text_lg: int = 14
    text_base: float = 12.5
    text_mono: int = 11
    text_eyebrow: int = 10

    # --- OCR Snap-specific additions ---
    translation: str = "#7ab8e0"  # translated text + "Translating…" indicator


Tokens = _Tokens()


class Icons:
    """Phosphor icon factories via qtawesome. Default color is text-primary."""

    _DEFAULT_COLOR = Tokens.text_primary

    @classmethod
    def _i(cls, name: str, color: str | None = None) -> QIcon:
        return qta.icon(name, color=color or cls._DEFAULT_COLOR)

    @classmethod
    def settings(cls, color: str | None = None) -> QIcon:
        return cls._i("ph.gear", color)

    @classmethod
    def close(cls, color: str | None = None) -> QIcon:
        return cls._i("ph.x", color)

    @classmethod
    def copy(cls, color: str | None = None) -> QIcon:
        return cls._i("ph.copy", color)

    @classmethod
    def delete(cls, color: str | None = None) -> QIcon:
        return cls._i("ph.trash", color)

    @classmethod
    def merge(cls, color: str | None = None) -> QIcon:
        return cls._i("ph.git-merge", color)


# --- IconButton ---

_ICON_BUTTON_QSS = f"""
QPushButton {{
    background: transparent;
    border: none;
    border-radius: {Tokens.r_sm}px;
    padding: {Tokens.sp_1}px;
}}
QPushButton:hover {{
    background: {Tokens.bg_hover};
}}
QPushButton:pressed {{
    background: {Tokens.bg_raised};
}}
QPushButton:checked {{
    background: {Tokens.accent_deep};
}}
"""


class IconButton(QPushButton):
    """Square, transparent-by-default icon button. Hover → bg_hover."""

    def __init__(
        self,
        icon: QIcon,
        tooltip: str = "",
        *,
        size: int = 24,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setIcon(icon)
        self.setIconSize(QSize(size, size))
        self.setFixedSize(size + 8, size + 8)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet(_ICON_BUTTON_QSS)
        if tooltip:
            self.setToolTip(tooltip)


# --- PrimaryButton ---

_PRIMARY_BUTTON_QSS = f"""
QPushButton {{
    background: {Tokens.accent_deep};
    color: {Tokens.text_emphasis};
    border: 1px solid {Tokens.accent};
    border-radius: {Tokens.r_md}px;
    padding: {Tokens.sp_1}px {Tokens.sp_3}px;
    font-size: {Tokens.text_base}px;
}}
QPushButton:hover {{
    background: #2a6fb8;
}}
QPushButton:pressed {{
    background: {Tokens.accent};
}}
QPushButton:disabled {{
    background: {Tokens.bg_raised};
    color: {Tokens.text_muted};
    border-color: {Tokens.border};
}}
"""


class PrimaryButton(QPushButton):
    """Accent-filled call-to-action button."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(_PRIMARY_BUTTON_QSS)


# --- StatusChip ---

_STATUS_CHIP_QSS = """
QLabel {{
    background: {bg};
    color: {fg};
    border: 1px solid {border};
    border-radius: {r}px;
    padding: 2px 8px;
    font-size: {fs}px;
}}
"""


class StatusChip(QLabel):
    """Pill-shaped label for transient state ('Translating…', etc.)."""

    _STATES = {
        "muted": (Tokens.bg_deepest, Tokens.text_muted, Tokens.border),
        "translation": (Tokens.bg_deepest, Tokens.translation, Tokens.translation),
        "alert": (Tokens.bg_deepest, Tokens.alert, Tokens.alert),
        "danger": (Tokens.bg_deepest, Tokens.danger, Tokens.danger),
        "success": (Tokens.bg_deepest, Tokens.success, Tokens.success),
    }

    def __init__(
        self,
        text: str = "",
        *,
        state: str = "muted",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.set_state(state)

    def set_state(self, state: str) -> None:
        bg, fg, border = self._STATES[state]
        self.setStyleSheet(
            _STATUS_CHIP_QSS.format(
                bg=bg, fg=fg, border=border, r=Tokens.r_pill, fs=Tokens.text_eyebrow
            )
        )
