from __future__ import annotations

import numpy as np
from PyQt6.QtGui import QColor, QImage, QPixmap

from ocr_snap.models import array_from_pixmap, array_from_qimage


def _solid_qimage(w: int, h: int, color: tuple[int, int, int]) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(QColor(*color))
    return img


def test_array_from_qimage_returns_rgb_uint8(qapp) -> None:
    img = _solid_qimage(40, 30, (255, 0, 0))
    arr = array_from_qimage(img)
    assert arr.shape == (30, 40, 3)
    assert arr.dtype == np.uint8
    # The fill colour is red → first pixel R channel high
    assert arr[0, 0, 0] >= 250
    assert arr[0, 0, 1] <= 5
    assert arr[0, 0, 2] <= 5


def test_array_from_pixmap_no_max_unchanged_size(qapp) -> None:
    img = _solid_qimage(40, 30, (0, 255, 0))
    arr = array_from_pixmap(QPixmap.fromImage(img))
    assert arr.shape == (30, 40, 3)


def test_array_from_pixmap_max_long_side_downscales(qapp) -> None:
    img = _solid_qimage(800, 400, (0, 0, 255))
    arr = array_from_pixmap(QPixmap.fromImage(img), max_long_side=400)
    # 800 > 400 → scale factor 0.5 → 400×200
    assert arr.shape == (200, 400, 3)


def test_array_from_pixmap_max_long_side_skip_when_below_cap(qapp) -> None:
    img = _solid_qimage(100, 60, (0, 0, 255))
    arr = array_from_pixmap(QPixmap.fromImage(img), max_long_side=400)
    # 100 <= 400 → no resize
    assert arr.shape == (60, 100, 3)
