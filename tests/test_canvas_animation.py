from __future__ import annotations

from PyQt6.QtGui import QPixmap

from ocr_snap.canvas import OCRCanvas


def test_set_animation_mode_off_skips_scan_line(qapp) -> None:
    canvas = OCRCanvas()
    # Need a pixmap so _start_processing has something to dim
    pixmap = QPixmap(100, 100)
    pixmap.fill()
    canvas._pixmap_item = canvas._scene.addPixmap(pixmap)
    canvas.setSceneRect(0, 0, 100, 100)

    canvas.set_animation_mode("off")
    canvas._start_processing()
    assert canvas._overlay is not None
    assert canvas._scan_line is None
    assert not canvas._anim_timer.isActive()
    canvas._stop_processing()


def test_set_animation_mode_minimal_runs_scan_no_sparks(qapp) -> None:
    canvas = OCRCanvas()
    pixmap = QPixmap(100, 100)
    pixmap.fill()
    canvas._pixmap_item = canvas._scene.addPixmap(pixmap)
    canvas.setSceneRect(0, 0, 100, 100)

    canvas.set_animation_mode("minimal")
    canvas._start_processing()
    assert canvas._scan_line is not None
    assert canvas._sparks_per_tick == 0
    canvas._anim_tick()
    assert canvas._sparks == []
    canvas._stop_processing()


def test_set_animation_mode_full_spawns_sparks(qapp) -> None:
    canvas = OCRCanvas()
    pixmap = QPixmap(100, 100)
    pixmap.fill()
    canvas._pixmap_item = canvas._scene.addPixmap(pixmap)
    canvas.setSceneRect(0, 0, 100, 100)

    canvas.set_animation_mode("full")
    canvas._start_processing()
    assert canvas._sparks_per_tick == 3
    canvas._anim_tick()
    assert len(canvas._sparks) == 3
    canvas._stop_processing()
