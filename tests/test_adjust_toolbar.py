from __future__ import annotations

from PyQt6.QtCore import Qt

from ocr_snap.adjust_toolbar import AdjustToolbar, _Pill, _SliderPill, _SliderPopover, _TogglePill
from ocr_snap.models import Adjustments
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


def test_slider_pill_idle_label_is_base(qapp) -> None:
    pill = _SliderPill(
        Icons.rotate, "Rotate",
        min_val=-180, max_val=180, default=0,
        value_text=lambda v: f"{v}°",
    )
    assert pill.text() == "Rotate"
    assert pill.is_active() is False
    assert pill.value() == 0


def test_slider_pill_active_label_appends_value(qapp) -> None:
    pill = _SliderPill(
        Icons.rotate, "Rotate",
        min_val=-180, max_val=180, default=0,
        value_text=lambda v: f"{v}°",
    )
    pill.set_value(45)
    assert pill.text() == "Rotate 45°"
    assert pill.is_active() is True
    assert pill.value() == 45
    pill.set_value(0)  # back to default
    assert pill.text() == "Rotate"
    assert pill.is_active() is False


def test_slider_pill_emits_value_changed(qapp) -> None:
    pill = _SliderPill(
        Icons.rotate, "Rotate",
        min_val=-180, max_val=180, default=0,
        value_text=lambda v: f"{v}°",
    )
    seen: list[int] = []
    pill.value_changed.connect(seen.append)
    pill.set_value(45)
    pill.set_value(-30)
    assert seen == [45, -30]


def test_slider_pill_click_opens_popover(qapp) -> None:
    pill = _SliderPill(
        Icons.rotate, "Rotate",
        min_val=-180, max_val=180, default=0,
        value_text=lambda v: f"{v}°",
    )
    assert pill._popover is None
    pill.click()
    assert pill._popover is not None
    assert pill._popover.isVisible()


def test_slider_pill_popover_drag_updates_pill_value(qapp) -> None:
    pill = _SliderPill(
        Icons.rotate, "Rotate",
        min_val=-180, max_val=180, default=0,
        value_text=lambda v: f"{v}°",
    )
    pill.click()
    pop = pill._popover
    assert pop is not None
    pop._slider.setValue(75)
    assert pill.value() == 75
    assert pill.text() == "Rotate 75°"
    assert pill.is_active() is True


def test_slider_pill_reuses_popover_across_open_close_cycles(qapp) -> None:
    """A second click closes the popover; a third click re-shows the SAME
    popover instance (no leak)."""
    pill = _SliderPill(
        Icons.rotate, "Rotate",
        min_val=-180, max_val=180, default=0,
        value_text=lambda v: f"{v}°",
    )
    pill.click()
    first = pill._popover
    assert first is not None and first.isVisible()
    pill.click()  # toggle close
    assert not first.isVisible()
    pill.click()  # reopen
    assert pill._popover is first  # same instance, not a fresh one
    assert first.isVisible()


def test_toolbar_default_is_identity(qapp) -> None:
    tb = AdjustToolbar()
    assert tb.current_adjustments().is_identity()


def test_toolbar_grayscale_toggle_emits_change(qapp) -> None:
    tb = AdjustToolbar()
    seen: list[Adjustments] = []
    tb.adjustments_changed.connect(seen.append)
    tb._grayscale.setChecked(True)
    assert seen and seen[-1].grayscale is True
    assert tb.current_adjustments().grayscale is True


def test_toolbar_rotate_slider_pill_emits_change(qapp) -> None:
    tb = AdjustToolbar()
    seen: list[Adjustments] = []
    tb.adjustments_changed.connect(seen.append)
    tb._rotation.set_value(90)
    assert seen and abs(seen[-1].rotation - 90.0) < 1e-6


def test_toolbar_brightness_scales_to_factor(qapp) -> None:
    tb = AdjustToolbar()
    tb._brightness.set_value(150)
    assert abs(tb.current_adjustments().brightness - 1.5) < 1e-6


def test_toolbar_sensitivity_scales_to_unit(qapp) -> None:
    tb = AdjustToolbar()
    tb._sensitivity.set_value(50)
    assert abs(tb.current_adjustments().det_sensitivity - 0.5) < 1e-6


def test_toolbar_crop_button_emits_crop_mode_toggle(qapp) -> None:
    tb = AdjustToolbar()
    seen: list[bool] = []
    tb.crop_mode_toggled.connect(seen.append)
    tb._crop_btn.setChecked(True)
    assert seen == [True]


def test_toolbar_run_and_reset_emit(qapp) -> None:
    tb = AdjustToolbar()
    runs: list[int] = []
    resets: list[int] = []
    tb.run_ocr_requested.connect(lambda: runs.append(1))
    tb.reset_requested.connect(lambda: resets.append(1))
    tb._run_btn.click()
    tb._reset_btn.click()
    assert runs == [1]
    assert resets == [1]


def test_toolbar_auto_pill_emits_auto_ocr_toggled(qapp) -> None:
    tb = AdjustToolbar()
    toggles: list[bool] = []
    tb.auto_ocr_toggled.connect(toggles.append)
    tb._auto_btn.setChecked(True)
    tb._auto_btn.setChecked(False)
    assert toggles == [True, False]


def test_toolbar_auto_does_not_affect_adjustments(qapp) -> None:
    """Auto is a UI mode, not a field on Adjustments — toggling it must
    not flip is_identity()."""
    tb = AdjustToolbar()
    tb._auto_btn.setChecked(True)
    assert tb.current_adjustments().is_identity()


def test_toolbar_contrast_and_sharpen_scale_to_factor(qapp) -> None:
    tb = AdjustToolbar()
    tb._contrast.set_value(60)
    tb._sharpen.set_value(120)
    adj = tb.current_adjustments()
    assert abs(adj.contrast - 0.6) < 1e-6
    assert abs(adj.sharpen - 1.2) < 1e-6


def test_toolbar_upscale_and_smart_fix_pills_emit(qapp) -> None:
    tb = AdjustToolbar()
    seen: list[Adjustments] = []
    tb.adjustments_changed.connect(seen.append)
    tb._upscale.setChecked(True)
    tb._smart_fix.setChecked(True)
    assert seen[-1].upscale is True
    assert seen[-1].smart_fix is True
