from __future__ import annotations

import pytest

from PyQt6.QtGui import QIcon

from ocr_snap.theme import IconButton, Icons, PrimaryButton, StatusChip, Tokens


def test_theme_module_imports() -> None:
    """Smoke test that the module file is parseable."""
    import ocr_snap.theme  # noqa: F401


@pytest.mark.parametrize(
    "field,expected",
    [
        # Colors
        ("bg_deepest", "#0f1114"),
        ("bg_base", "#14161a"),
        ("bg_surface", "#1a1c20"),
        ("bg_raised", "#1f2226"),
        ("bg_hover", "#2a2d33"),
        ("border", "#2d3036"),
        ("border_strong", "#3a3d44"),
        ("text_muted", "#888888"),
        ("text_primary", "#d8d8d8"),
        ("text_emphasis", "#ffffff"),
        ("accent", "#4a9eff"),
        ("accent_deep", "#1f5fa6"),
        ("alert", "#ffcc55"),
        ("danger", "#ff8a8a"),
        ("success", "#8ad08a"),
        ("overlay", "rgba(0,0,0,0.85)"),
        # Spacing
        ("sp_1", 4),
        ("sp_2", 8),
        ("sp_3", 12),
        ("sp_4", 16),
        ("sp_5", 24),
        ("sp_6", 36),
        # Radii
        ("r_sm", 3),
        ("r_md", 6),
        ("r_lg", 10),
        ("r_pill", 13),
        # Type sizes
        ("text_hero", 22),
        ("text_lg", 14),
        ("text_base", 12.5),
        ("text_mono", 11),
        ("text_eyebrow", 10),
        # OCR Snap-specific
        ("translation", "#7ab8e0"),
    ],
)
def test_tokens_have_expected_values(field: str, expected) -> None:
    assert getattr(Tokens, field) == expected


def test_tokens_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        Tokens.bg_base = "#000000"  # type: ignore[misc]


def test_icons_settings_returns_valid_qicon(qapp) -> None:
    icon = Icons.settings()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_icons_close_returns_valid_qicon(qapp) -> None:
    icon = Icons.close()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_icons_copy_returns_valid_qicon(qapp) -> None:
    icon = Icons.copy()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_icons_delete_returns_valid_qicon(qapp) -> None:
    icon = Icons.delete()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_icons_merge_returns_valid_qicon(qapp) -> None:
    icon = Icons.merge()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_icons_accepts_color_override(qapp) -> None:
    """Each factory accepts a color string; both default and override produce icons."""
    default = Icons.settings()
    override = Icons.settings(color="#ff0000")
    assert not default.isNull()
    assert not override.isNull()


def test_icon_button_constructs(qapp) -> None:
    btn = IconButton(Icons.settings(), tooltip="Settings")
    assert btn.toolTip() == "Settings"
    assert not btn.icon().isNull()


def test_icon_button_default_no_tooltip(qapp) -> None:
    btn = IconButton(Icons.close())
    assert btn.toolTip() == ""


def test_primary_button_constructs(qapp) -> None:
    btn = PrimaryButton("Test key")
    assert btn.text() == "Test key"


def test_status_chip_constructs_with_default_state(qapp) -> None:
    chip = StatusChip("Translating…")
    assert chip.text() == "Translating…"


def test_status_chip_set_state_accepts_known_states(qapp) -> None:
    chip = StatusChip()
    for state in ("muted", "translation", "alert", "danger", "success"):
        chip.set_state(state)  # must not raise


def test_status_chip_set_state_unknown_raises(qapp) -> None:
    chip = StatusChip()
    with pytest.raises(KeyError):
        chip.set_state("not-a-real-state")


def test_adjust_toolbar_icon_factories_resolve(qapp) -> None:
    factories = [
        Icons.rotate,
        Icons.brightness,
        Icons.contrast,
        Icons.sharpen,
        Icons.grayscale,
        Icons.invert,
        Icons.binarize,
        Icons.upscale,
        Icons.smart_fix,
        Icons.sensitivity,
        Icons.crop,
        Icons.reset,
        Icons.run_ocr,
        Icons.auto_ocr,
    ]
    for fac in factories:
        icon = fac()
        assert isinstance(icon, QIcon), f"{fac.__name__} did not return a QIcon"
        assert not icon.isNull(), f"{fac.__name__} returned a null icon"
