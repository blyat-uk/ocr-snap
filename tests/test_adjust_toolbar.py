from __future__ import annotations

from PyQt6.QtCore import Qt

from ocr_snap.adjust_toolbar import _Pill, _SliderPopover, _TogglePill
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


def test_slider_popover_has_popup_window_flag(qapp) -> None:
    pop = _SliderPopover(
        title="Rotate", min_val=-180, max_val=180,
        default=0, current=0, value_text=lambda v: f"{v}°",
    )
    flags = pop.windowFlags()
    assert flags & Qt.WindowType.Popup


def test_slider_popover_emits_value_changed_on_drag(qapp) -> None:
    pop = _SliderPopover(
        title="Rotate", min_val=-180, max_val=180,
        default=0, current=0, value_text=lambda v: f"{v}°",
    )
    seen: list[int] = []
    pop.value_changed.connect(seen.append)
    pop._slider.setValue(45)
    pop._slider.setValue(-30)
    assert seen == [45, -30]


def test_slider_popover_reset_sets_default(qapp) -> None:
    pop = _SliderPopover(
        title="Rotate", min_val=-180, max_val=180,
        default=0, current=45, value_text=lambda v: f"{v}°",
    )
    assert pop._slider.value() == 45
    pop._reset_to_default()
    assert pop._slider.value() == 0


def test_slider_popover_value_label_updates_on_drag(qapp) -> None:
    pop = _SliderPopover(
        title="Brightness", min_val=20, max_val=200,
        default=100, current=100, value_text=lambda v: f"{v - 100:+d}%",
    )
    pop._slider.setValue(150)
    assert pop._value_label.text() == "+50%"


def test_slider_popover_reset_when_already_at_default_is_silent(qapp) -> None:
    """QSlider.setValue is a no-op when already at the target, so resetting
    from the default does not fire value_changed — document the contract."""
    pop = _SliderPopover(
        title="Rotate", min_val=-180, max_val=180,
        default=0, current=0, value_text=lambda v: f"{v}°",
    )
    seen: list[int] = []
    pop.value_changed.connect(seen.append)
    pop._reset_to_default()
    assert seen == []
    assert pop._slider.value() == 0
