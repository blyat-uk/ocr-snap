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
