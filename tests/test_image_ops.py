from __future__ import annotations

import numpy as np
from PIL import Image
from PyQt6.QtGui import QColor, QImage, QPixmap

from ocr_snap.image_ops import (
    array_from_pil,
    pil_from_array,
    pil_from_pixmap,
    pixmap_from_pil,
    render_display,
    render_ocr_input,
)
from ocr_snap.models import Adjustments


def _solid_pil(w: int, h: int, color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (w, h), color)


def test_pil_array_roundtrip() -> None:
    img = _solid_pil(8, 6, (10, 20, 30))
    arr = array_from_pil(img)
    assert arr.shape == (6, 8, 3)
    assert arr.dtype == np.uint8
    assert tuple(arr[0, 0]) == (10, 20, 30)
    back = pil_from_array(arr)
    assert back.size == (8, 6)


def test_pixmap_roundtrip(qapp) -> None:
    src = QImage(8, 6, QImage.Format.Format_RGB888)
    src.fill(QColor(200, 100, 50))
    pixmap = QPixmap.fromImage(src)
    img = pil_from_pixmap(pixmap)
    assert img.size == (8, 6)
    assert tuple(array_from_pil(img)[0, 0]) == (200, 100, 50)
    out = pixmap_from_pil(img)
    assert out.width() == 8 and out.height() == 6


def test_render_display_identity_keeps_size() -> None:
    img = _solid_pil(40, 30, (120, 120, 120))
    out = render_display(img, Adjustments())
    assert out.size == (40, 30)


def test_render_ocr_input_downscales_large() -> None:
    img = _solid_pil(800, 400, (0, 0, 255))
    arr = render_ocr_input(img, Adjustments(), effective_long_side=400)
    assert arr.shape == (200, 400, 3)
    assert arr.dtype == np.uint8


def test_render_ocr_input_no_upscale_when_small() -> None:
    img = _solid_pil(100, 60, (0, 0, 0))
    arr = render_ocr_input(img, Adjustments(upscale=False), effective_long_side=400)
    assert arr.shape == (60, 100, 3)


def test_render_ocr_input_upscales_when_flagged() -> None:
    img = _solid_pil(100, 60, (0, 0, 0))
    arr = render_ocr_input(img, Adjustments(upscale=True), effective_long_side=400)
    # long side 100 -> 400, factor 4 -> 240 tall
    assert arr.shape == (240, 400, 3)
