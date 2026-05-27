"""Pure image-adjustment pipeline (Pillow + numpy).

No Qt-widget or app-state dependencies. Renders both the on-screen
preview (``render_display``) and the OCR-input array (``render_ocr_input``)
from a pristine original image plus an ``Adjustments`` value object.

The pixel pipeline order is: rotate -> crop -> grayscale -> brightness ->
contrast -> invert -> binarize (Otsu) -> sharpen.
"""

from __future__ import annotations

import numpy as np
from PIL import Image
from PyQt6.QtGui import QImage, QPixmap

from ocr_snap.models import Adjustments, array_from_qimage


def pil_from_array(arr: np.ndarray) -> Image.Image:
    """Wrap an RGB uint8 (H, W, 3) array in a PIL image (owns a copy)."""
    return Image.fromarray(np.ascontiguousarray(arr, dtype=np.uint8), mode="RGB")


def array_from_pil(img: Image.Image) -> np.ndarray:
    """Return a contiguous RGB uint8 (H, W, 3) copy of a PIL image."""
    if img.mode != "RGB":
        img = img.convert("RGB")
    return np.ascontiguousarray(np.asarray(img, dtype=np.uint8))


def pil_from_pixmap(pixmap: QPixmap) -> Image.Image:
    """Convert a QPixmap to an RGB PIL image."""
    return pil_from_array(array_from_qimage(pixmap.toImage()))


def pixmap_from_pil(img: Image.Image) -> QPixmap:
    """Convert a PIL image to a QPixmap (detached from the source array)."""
    arr = array_from_pil(img)
    h, w, _ = arr.shape
    qimg = QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


def _apply_geometry(img: Image.Image, adj: Adjustments) -> Image.Image:
    return img  # implemented in Task 4


def _apply_tone(img: Image.Image, adj: Adjustments) -> Image.Image:
    return img  # implemented in Task 3


def _pipeline(img: Image.Image, adj: Adjustments) -> Image.Image:
    img = _apply_geometry(img, adj)
    img = _apply_tone(img, adj)
    return img


def render_display(original: Image.Image, adj: Adjustments) -> Image.Image:
    """Full pixel pipeline for the on-screen preview."""
    return _pipeline(original, adj)


def _scale_long_side(img: Image.Image, target: int, *, allow_upscale: bool) -> Image.Image:
    w, h = img.size
    long_side = max(w, h)
    if long_side == 0 or long_side == target:
        return img
    if long_side < target and not allow_upscale:
        return img
    factor = target / long_side
    new_w = max(1, round(w * factor))
    new_h = max(1, round(h * factor))
    return img.resize((new_w, new_h), Image.LANCZOS)


def render_ocr_input(
    original: Image.Image, adj: Adjustments, effective_long_side: int
) -> np.ndarray:
    """Full pixel pipeline at source resolution, then scaled to the OCR
    long-side ceiling (up if ``adj.upscale`` and currently smaller, else down).
    Returns an RGB uint8 (H, W, 3) array compatible with the OCR engine.
    """
    img = _pipeline(original, adj)
    img = _scale_long_side(img, effective_long_side, allow_upscale=adj.upscale)
    return array_from_pil(img)
