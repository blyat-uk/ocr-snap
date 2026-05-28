"""Pure image-adjustment pipeline (Pillow + numpy).

No Qt-widget or app-state dependencies. Renders both the on-screen
preview (``render_display``) and the OCR-input array (``render_ocr_input``)
from a pristine original image plus an ``Adjustments`` value object.

The pixel pipeline order is: crop -> rotate -> grayscale -> brightness ->
contrast -> invert -> binarize (Otsu) -> sharpen. Crop runs before rotate
so a rotation applied after a crop expands the viewport around the cropped
piece (otherwise the cropped image would be clipped).
"""

from __future__ import annotations

import dataclasses

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from PyQt6.QtGui import QImage, QPixmap

from ocr_snap.models import Adjustments, array_from_qimage

_FILL = (255, 255, 255)


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
    # Crop FIRST, then rotate (with expand). This way rotation expands around
    # the cropped piece; the reverse order would clip a previously-cropped
    # image when the user later rotates it.
    if adj.crop is not None:
        img = _apply_crop(img, adj.crop)
    if adj.rotation != 0.0:
        # PIL rotates counter-clockwise for positive angles; negate so that
        # a positive Adjustments.rotation is clockwise.
        img = img.rotate(
            -adj.rotation, expand=True, resample=Image.BICUBIC, fillcolor=_FILL
        )
    return img


def _apply_crop(img: Image.Image, crop: tuple[float, float, float, float]) -> Image.Image:
    x, y, cw, ch = crop
    w, h = img.size

    def clamp01(v: float) -> float:
        return max(0.0, min(1.0, v))

    left = int(round(clamp01(x) * w))
    top = int(round(clamp01(y) * h))
    right = int(round(clamp01(x + cw) * w))
    bottom = int(round(clamp01(y + ch) * h))
    if right - left < 2 or bottom - top < 2:
        return img  # reject degenerate crop
    return img.crop((left, top, right, bottom))


def _apply_tone(img: Image.Image, adj: Adjustments) -> Image.Image:
    if adj.grayscale or adj.binarize:
        img = img.convert("L").convert("RGB")
    if adj.brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(adj.brightness)
    if adj.contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(adj.contrast)
    if adj.invert:
        img = ImageOps.invert(img.convert("RGB"))
    if adj.binarize:
        img = _otsu_binarize(img)
    if adj.sharpen > 0.0:
        # Map sharpen 0..2 onto UnsharpMask percent; 150% at 1.0 is Pillow's
        # recommended moderate value.
        percent = int(round(adj.sharpen * 150))
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=percent, threshold=3))
    return img


def _otsu_threshold(gray: np.ndarray) -> int:
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = int(gray.size)
    sum_total = float(np.dot(np.arange(256), hist))
    sum_b = 0.0
    w_b = 0.0
    max_var = -1.0
    threshold = 0
    for i in range(256):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * hist[i]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > max_var:
            max_var = var_between
            threshold = i
    return threshold


def _otsu_binarize(img: Image.Image) -> Image.Image:
    gray = np.asarray(img.convert("L"))
    thresh = _otsu_threshold(gray)
    binary = (gray > thresh).astype(np.uint8) * 255
    rgb = np.stack([binary, binary, binary], axis=-1)
    return Image.fromarray(rgb, mode="RGB")


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


def bake_geometry(
    source: Image.Image, adj: Adjustments
) -> tuple[Image.Image, Adjustments]:
    """Apply ``adj``'s geometry (crop, then rotation) to ``source`` and return
    ``(baked_source, geometry_stripped_adj)``. Tone and OCR fields on ``adj``
    are preserved on the returned Adjustments; only ``rotation`` and ``crop``
    are reset to identity.

    Returns ``source`` unchanged when ``adj`` has no geometry — callers can
    use ``baked is source`` to detect the no-op case.

    The caller-facing purpose is to "commit" the current geometry into the
    working source so a freshly-drawn crop rect (in working-pixmap coords) can
    be applied directly as ``Adjustments.crop`` without going through the
    inverse-rotation back-transform — which is lossy for non-90° rotations
    (it stores the axis-aligned bounding box of a rotated quad, which is
    strictly larger than what the user actually drew).
    """
    if adj.rotation == 0.0 and adj.crop is None:
        return source, adj
    geom_only = Adjustments(rotation=adj.rotation, crop=adj.crop)
    baked = _apply_geometry(source, geom_only)
    return baked, dataclasses.replace(adj, rotation=0.0, crop=None)


