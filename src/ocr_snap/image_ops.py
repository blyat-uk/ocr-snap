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

import math

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


def crop_to_original_normalized(
    rect_in_working_normalized: tuple[float, float, float, float],
    working_size: tuple[int, int],
    adj: Adjustments,
    original_size: tuple[int, int],
) -> tuple[float, float, float, float]:
    """Map a crop rect drawn on the WORKING (displayed) pixmap to normalized
    coordinates on the ORIGINAL pixmap.

    The working pixmap is produced by the pixel pipeline (``crop`` then
    ``rotate``). To recover original-space coords from a working-space point
    we invert the rotation first (working → cropped-original) and then the
    prior crop (cropped-original → original). The result is the axis-aligned
    bounding box of the user's drawn rect in original space, clamped to the
    image bounds. Identity when ``adj`` has no rotation and no prior crop.
    """
    W_orig, H_orig = original_size
    if W_orig <= 0 or H_orig <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    W_work, H_work = working_size

    nx, ny, nw, nh = rect_in_working_normalized
    x1, y1 = nx * W_work, ny * H_work
    x2, y2 = x1 + nw * W_work, y1 + nh * H_work
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

    # Cropped-original dims and offset (or full original when no prior crop).
    if adj.crop is not None:
        cx, cy, cw, ch = adj.crop
        W_crop = cw * W_orig
        H_crop = ch * H_orig
        crop_offset_x = cx * W_orig
        crop_offset_y = cy * H_orig
    else:
        W_crop = float(W_orig)
        H_crop = float(H_orig)
        crop_offset_x = 0.0
        crop_offset_y = 0.0

    # 1. Inverse-rotate (working → cropped-original space). The forward
    #    rotation is visual CW by ``adj.rotation``; the inverse rotates each
    #    working-space corner around the working center, then re-centers on
    #    the cropped-original center.
    if adj.rotation != 0.0:
        theta = math.radians(adj.rotation)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        ow_x, ow_y = W_work / 2.0, H_work / 2.0
        oc_x, oc_y = W_crop / 2.0, H_crop / 2.0
        corners = [
            (
                (px - ow_x) * cos_t + (py - ow_y) * sin_t + oc_x,
                -(px - ow_x) * sin_t + (py - ow_y) * cos_t + oc_y,
            )
            for px, py in corners
        ]

    # 2. Undo any prior crop offset (cropped-original → original).
    corners = [(px + crop_offset_x, py + crop_offset_y) for px, py in corners]

    # 3. Axis-aligned bounding box in original space, clamped to bounds.
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    x_min = max(0.0, min(float(W_orig), min(xs)))
    x_max = max(0.0, min(float(W_orig), max(xs)))
    y_min = max(0.0, min(float(H_orig), min(ys)))
    y_max = max(0.0, min(float(H_orig), max(ys)))
    return (
        x_min / W_orig,
        y_min / H_orig,
        (x_max - x_min) / W_orig,
        (y_max - y_min) / H_orig,
    )
