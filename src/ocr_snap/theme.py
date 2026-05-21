"""Centralized design tokens, icon factories, and reusable widget
subclasses. Ported from sub-label-pos with OCR Snap-specific
additions.
"""
from __future__ import annotations

from dataclasses import dataclass


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
