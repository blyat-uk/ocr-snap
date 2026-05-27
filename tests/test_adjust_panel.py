from __future__ import annotations

from ocr_snap.adjust_panel import AdjustPanel
from ocr_snap.models import Adjustments


def test_default_is_identity(qapp) -> None:
    panel = AdjustPanel()
    assert panel.current_adjustments().is_identity()


def test_grayscale_checkbox_emits_change(qapp) -> None:
    panel = AdjustPanel()
    seen: list[Adjustments] = []
    panel.adjustments_changed.connect(seen.append)
    panel._grayscale.setChecked(True)
    assert seen and seen[-1].grayscale is True
    assert panel.current_adjustments().grayscale is True


def test_smart_fix_checkbox_sets_flag(qapp) -> None:
    panel = AdjustPanel()
    panel._smart_fix.setChecked(True)
    assert panel.current_adjustments().smart_fix is True


def test_rotation_slider_sets_rotation(qapp) -> None:
    panel = AdjustPanel()
    seen: list[Adjustments] = []
    panel.adjustments_changed.connect(seen.append)
    panel._rotation.setValue(90)
    assert seen and abs(seen[-1].rotation - 90.0) < 1e-6


def test_brightness_slider_scales_to_factor(qapp) -> None:
    panel = AdjustPanel()
    panel._brightness.setValue(150)  # 150/100
    assert abs(panel.current_adjustments().brightness - 1.5) < 1e-6


def test_det_sensitivity_slider_scales(qapp) -> None:
    panel = AdjustPanel()
    panel._sensitivity.setValue(50)
    assert abs(panel.current_adjustments().det_sensitivity - 0.5) < 1e-6


def test_set_adjustments_loads_without_emitting(qapp) -> None:
    panel = AdjustPanel()
    seen: list[Adjustments] = []
    panel.adjustments_changed.connect(seen.append)
    panel.set_adjustments(Adjustments(grayscale=True, rotation=45.0, brightness=1.2))
    assert seen == []  # loading state must not emit
    assert panel._grayscale.isChecked() is True
    assert panel._rotation.value() == 45
    assert panel._brightness.value() == 120


def test_crop_button_emits_crop_mode_toggle(qapp) -> None:
    panel = AdjustPanel()
    toggles: list[bool] = []
    panel.crop_mode_toggled.connect(toggles.append)
    panel._crop_btn.setChecked(True)
    assert toggles == [True]


def test_set_crop_updates_adjustments_and_emits(qapp) -> None:
    panel = AdjustPanel()
    seen: list[Adjustments] = []
    panel.adjustments_changed.connect(seen.append)
    panel.set_crop((0.1, 0.1, 0.5, 0.5))
    assert panel.current_adjustments().crop == (0.1, 0.1, 0.5, 0.5)
    assert seen and seen[-1].crop == (0.1, 0.1, 0.5, 0.5)


def test_run_and_reset_buttons_emit(qapp) -> None:
    panel = AdjustPanel()
    runs: list[int] = []
    resets: list[int] = []
    panel.run_ocr_requested.connect(lambda: runs.append(1))
    panel.reset_requested.connect(lambda: resets.append(1))
    panel._run_btn.click()
    panel._reset_btn.click()
    assert runs == [1]
    assert resets == [1]


def test_set_crop_does_not_emit_crop_mode_toggle(qapp) -> None:
    panel = AdjustPanel()
    panel._crop_btn.setChecked(True)  # simulate crop mode active
    toggles: list[bool] = []
    panel.crop_mode_toggled.connect(toggles.append)
    panel.set_crop((0.1, 0.1, 0.5, 0.5))
    assert toggles == []  # unchecking the button must not re-emit the toggle
    assert panel._crop_btn.isChecked() is False


def test_set_adjustments_quantizes_to_slider_granularity(qapp) -> None:
    # Sub-integer rotation is quantized to the integer slider; internal state
    # must match the slider so a later control change does not silently shift it.
    panel = AdjustPanel()
    panel.set_adjustments(Adjustments(rotation=45.7))
    assert panel._rotation.value() == 46
    assert panel.current_adjustments().rotation == 46.0


def test_set_crop_active_syncs_button_without_emitting(qapp) -> None:
    panel = AdjustPanel()
    toggles: list[bool] = []
    panel.crop_mode_toggled.connect(toggles.append)
    panel.set_crop_active(True)
    assert panel._crop_btn.isChecked() is True
    panel.set_crop_active(False)
    assert panel._crop_btn.isChecked() is False
    assert toggles == []  # syncing must not re-emit crop_mode_toggled
