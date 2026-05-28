from __future__ import annotations

from PyQt6.QtCore import Qt

from ocr_snap.pill import Pill, TogglePill
from ocr_snap.theme import Icons


def test_pill_starts_inactive(qapp) -> None:
    p = Pill(Icons.eye, "Overlay")
    assert p.is_active() is False
    assert p.property("on") is False


def test_pill_set_active_toggles_property_and_icon(qapp) -> None:
    p = Pill(Icons.eye, "Overlay")
    idle = p.icon()
    p.set_active(True)
    assert p.is_active() is True
    assert p.property("on") is True
    assert p.icon() is not idle


def test_toggle_pill_is_checkable_and_emits_toggled(qapp) -> None:
    p = TogglePill(Icons.eye, "Overlay")
    assert p.isCheckable()
    received: list[bool] = []
    p.toggled.connect(received.append)
    p.setChecked(True)
    assert received == [True]


def test_toggle_pill_checked_drives_active_state(qapp) -> None:
    p = TogglePill(Icons.eye, "Overlay")
    p.setChecked(True)
    assert p.is_active() is True
    p.setChecked(False)
    assert p.is_active() is False


def test_pill_cursor_is_pointing_hand(qapp) -> None:
    p = Pill(Icons.eye, "Overlay")
    assert p.cursor().shape() == Qt.CursorShape.PointingHandCursor
