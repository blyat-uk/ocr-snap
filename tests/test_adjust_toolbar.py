from __future__ import annotations

from ocr_snap.adjust_toolbar import _Pill, _TogglePill
from ocr_snap.theme import Icons


def test_pill_has_icon_and_label(qapp) -> None:
    p = _Pill(Icons.grayscale, "Grayscale")
    assert p.text() == "Grayscale"
    assert not p.icon().isNull()


def test_pill_starts_inactive(qapp) -> None:
    p = _Pill(Icons.grayscale, "Grayscale")
    assert p.is_active() is False
    assert p.property("on") is False


def test_pill_set_active_toggles_property_and_swaps_icon(qapp) -> None:
    p = _Pill(Icons.grayscale, "Grayscale")
    idle = p.icon()
    p.set_active(True)
    assert p.is_active() is True
    assert p.property("on") in (True, "true")
    # The icon object should be the cached active variant (different
    # QIcon instance from the idle one).
    assert p.icon() is not idle
    p.set_active(False)
    assert p.is_active() is False
    assert p.icon() is idle  # back to the cached idle icon


def test_toggle_pill_is_checkable(qapp) -> None:
    p = _TogglePill(Icons.grayscale, "Grayscale")
    assert p.isCheckable()
    assert p.is_active() is False


def test_toggle_pill_checked_drives_active_state(qapp) -> None:
    p = _TogglePill(Icons.grayscale, "Grayscale")
    p.setChecked(True)
    assert p.is_active() is True
    p.setChecked(False)
    assert p.is_active() is False


def test_toggle_pill_emits_toggled_signal(qapp) -> None:
    p = _TogglePill(Icons.grayscale, "Grayscale")
    seen: list[bool] = []
    p.toggled.connect(seen.append)
    p.setChecked(True)
    p.setChecked(False)
    assert seen == [True, False]
