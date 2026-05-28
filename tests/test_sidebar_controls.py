from __future__ import annotations

import pytest

from ocr_snap.sidebar import OCRSidebar
from ocr_snap.pill import TogglePill, Pill


def test_sidebar_has_overlay_toggle_pill(qapp) -> None:
    sb = OCRSidebar()
    assert isinstance(sb._overlay_pill, TogglePill)
    assert sb._overlay_pill.text() == "Overlay"


def test_sidebar_has_copy_image_pill(qapp) -> None:
    sb = OCRSidebar()
    assert isinstance(sb._copy_image_pill, Pill)
    assert sb._copy_image_pill.text() == "Copy image"
    # Copy image is an action, not a toggle.
    assert sb._copy_image_pill.isCheckable() is False


def test_overlay_pill_emits_overlay_toggled(qapp) -> None:
    sb = OCRSidebar()
    received: list[bool] = []
    sb.overlay_toggled.connect(received.append)
    sb._overlay_pill.setChecked(True)
    assert received == [True]
    sb._overlay_pill.setChecked(False)
    assert received == [True, False]


def test_copy_image_pill_emits_copy_image_requested(qapp) -> None:
    sb = OCRSidebar()
    received: list[bool] = []
    sb.copy_image_requested.connect(lambda: received.append(True))
    sb._copy_image_pill.click()
    assert received == [True]


def test_set_overlay_checked_does_not_re_emit(qapp) -> None:
    sb = OCRSidebar()
    received: list[bool] = []
    sb.overlay_toggled.connect(received.append)
    sb.set_overlay_checked(True)
    assert received == []
    assert sb._overlay_pill.isChecked() is True


def test_set_active_state_disables_both_pills_when_no_image(qapp) -> None:
    sb = OCRSidebar()
    sb.set_active_state(has_image=False, has_results=False)
    assert sb._overlay_pill.isEnabled() is False
    assert sb._copy_image_pill.isEnabled() is False


def test_set_active_state_image_without_results_enables_only_copy(qapp) -> None:
    sb = OCRSidebar()
    sb.set_active_state(has_image=True, has_results=False)
    assert sb._copy_image_pill.isEnabled() is True
    assert sb._overlay_pill.isEnabled() is False


def test_set_active_state_image_and_results_enables_both(qapp) -> None:
    sb = OCRSidebar()
    sb.set_active_state(has_image=True, has_results=True)
    assert sb._copy_image_pill.isEnabled() is True
    assert sb._overlay_pill.isEnabled() is True
