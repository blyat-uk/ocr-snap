from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap

from ocr_snap.canvas import OCRCanvas, _MAX_SCALE
from ocr_snap.models import ImageState


def _make_canvas_with_image(qapp, w: int = 800, h: int = 600) -> OCRCanvas:
    canvas = OCRCanvas()
    canvas.resize(400, 300)
    canvas.show()
    qapp.processEvents()
    qimg = QImage(w, h, QImage.Format.Format_RGB32)
    qimg.fill(Qt.GlobalColor.white)
    canvas._load_qimage(qimg)
    qapp.processEvents()
    return canvas


def test_fit_scale_matches_viewport(qapp):
    canvas = _make_canvas_with_image(qapp, w=1000, h=500)
    fit = canvas._fit_scale()
    vp = canvas.viewport().size()
    expected = min(vp.width() / 1000, vp.height() / 500)
    assert fit == expected
    canvas.close()


def test_apply_zoom_clamps_at_max(qapp):
    canvas = _make_canvas_with_image(qapp)
    canvas._apply_zoom(1000.0)
    assert canvas._current_scale() == _MAX_SCALE
    assert canvas._fit_to_view is False
    canvas.close()


def test_apply_zoom_snaps_to_fit(qapp):
    canvas = _make_canvas_with_image(qapp)
    canvas._apply_zoom(4.0)
    assert canvas._fit_to_view is False
    canvas._apply_zoom(0.0001)
    assert canvas._fit_to_view is True
    # fitInView's actual transform sits a hair under _fit_scale's pure ratio
    # due to Qt's internal viewport margin handling; allow ~2% slack.
    assert math.isclose(canvas._current_scale(), canvas._fit_scale(), rel_tol=0.02)
    canvas.close()


def test_load_image_resets_fit_flag(qapp):
    canvas = _make_canvas_with_image(qapp)
    canvas._apply_zoom(4.0)
    assert canvas._fit_to_view is False
    qimg = QImage(640, 480, QImage.Format.Format_RGB32)
    qimg.fill(Qt.GlobalColor.white)
    canvas._load_qimage(qimg)
    qapp.processEvents()
    assert canvas._fit_to_view is True
    canvas.close()


def test_load_image_state_resets_fit_flag(qapp):
    canvas = _make_canvas_with_image(qapp)
    canvas._apply_zoom(4.0)
    assert canvas._fit_to_view is False

    qimg = QImage(640, 480, QImage.Format.Format_RGB32)
    qimg.fill(Qt.GlobalColor.white)
    pixmap = QPixmap.fromImage(qimg)
    state = ImageState("x", pixmap, np.zeros((480, 640, 3), dtype=np.uint8))
    canvas.load_image_state(state)
    qapp.processEvents()
    assert canvas._fit_to_view is True
    canvas.close()


# ── Wheel + resize ───────────────────────────────────────────────────


def _send_wheel(canvas: OCRCanvas, delta_y: int) -> None:
    from PyQt6.QtCore import QPoint, QPointF
    from PyQt6.QtGui import QWheelEvent

    pos = QPointF(canvas.viewport().rect().center())
    global_pos = QPointF(canvas.viewport().mapToGlobal(pos.toPoint()))
    event = QWheelEvent(
        pos,
        global_pos,
        QPoint(0, 0),
        QPoint(0, delta_y),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    canvas.wheelEvent(event)


def test_wheel_in_zooms_in(qapp):
    canvas = _make_canvas_with_image(qapp)
    before = canvas._current_scale()
    _send_wheel(canvas, 480)
    assert canvas._current_scale() > before
    assert canvas._fit_to_view is False
    canvas.close()


def test_wheel_out_snaps_back_to_fit(qapp):
    canvas = _make_canvas_with_image(qapp)
    _send_wheel(canvas, 1200)
    assert canvas._fit_to_view is False
    _send_wheel(canvas, -10000)
    assert canvas._fit_to_view is True
    canvas.close()


def test_resize_preserves_zoom_when_user_zoomed(qapp):
    canvas = _make_canvas_with_image(qapp)
    _send_wheel(canvas, 1200)
    scaled = canvas._current_scale()
    canvas.resize(500, 400)
    qapp.processEvents()
    assert canvas._fit_to_view is False
    assert canvas._current_scale() == scaled
    canvas.close()


def test_resize_refits_when_at_fit(qapp):
    canvas = _make_canvas_with_image(qapp)
    assert canvas._fit_to_view is True
    canvas.resize(500, 400)
    qapp.processEvents()
    # After resize, scale should be at the new fit (within fitInView's ~2% slack).
    assert math.isclose(canvas._current_scale(), canvas._fit_scale(), rel_tol=0.02)
    canvas.close()
