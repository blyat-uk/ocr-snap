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


def test_grayscale_makes_channels_equal() -> None:
    img = Image.new("RGB", (4, 4), (200, 100, 50))
    arr = array_from_pil(render_display(img, Adjustments(grayscale=True)))
    assert arr[0, 0, 0] == arr[0, 0, 1] == arr[0, 0, 2]


def test_invert_black_to_white() -> None:
    img = Image.new("RGB", (4, 4), (0, 0, 0))
    arr = array_from_pil(render_display(img, Adjustments(invert=True)))
    assert tuple(arr[0, 0]) == (255, 255, 255)


def test_binarize_outputs_only_black_and_white() -> None:
    grad = np.tile(np.arange(256, dtype=np.uint8), (4, 1))  # 4x256 ramp
    rgb = np.stack([grad, grad, grad], axis=-1)
    img = Image.fromarray(rgb, mode="RGB")
    arr = array_from_pil(render_display(img, Adjustments(binarize=True)))
    uniq = set(np.unique(arr).tolist())
    assert uniq.issubset({0, 255})
    assert arr[0, 0, 0] == arr[0, 0, 1] == arr[0, 0, 2]


def test_brightness_increases_mean() -> None:
    img = Image.new("RGB", (4, 4), (100, 100, 100))
    brighter = array_from_pil(render_display(img, Adjustments(brightness=1.5)))
    darker = array_from_pil(render_display(img, Adjustments(brightness=0.5)))
    assert brighter.mean() > 100 >= darker.mean()


def test_sharpen_preserves_size_and_runs() -> None:
    img = Image.new("RGB", (20, 16), (120, 120, 120))
    out = render_display(img, Adjustments(sharpen=1.0))
    assert out.size == (20, 16)


def test_binarize_uniform_image_does_not_crash() -> None:
    # Uniform image -> Otsu picks threshold 0; must not divide-by-zero.
    img = Image.new("RGB", (4, 4), (128, 128, 128))
    arr = array_from_pil(render_display(img, Adjustments(binarize=True)))
    assert set(np.unique(arr).tolist()).issubset({0, 255})


def test_rotate_90_swaps_dimensions() -> None:
    img = Image.new("RGB", (40, 20), (0, 0, 0))
    out = render_display(img, Adjustments(rotation=90.0))
    assert out.size == (20, 40)


def test_rotate_45_fills_corner_white() -> None:
    img = Image.new("RGB", (40, 40), (0, 0, 0))
    arr = array_from_pil(render_display(img, Adjustments(rotation=45.0)))
    assert tuple(arr[0, 0]) == (255, 255, 255)  # exposed corner is white fill


def test_crop_normalized_region() -> None:
    img = Image.new("RGB", (100, 80), (0, 0, 0))
    out = render_display(img, Adjustments(crop=(0.1, 0.25, 0.5, 0.5)))
    # left=10,right=60 -> 50 wide; top=20,bottom=60 -> 40 tall
    assert out.size == (50, 40)


def test_crop_degenerate_returns_original() -> None:
    img = Image.new("RGB", (100, 80), (0, 0, 0))
    out = render_display(img, Adjustments(crop=(0.5, 0.5, 0.0, 0.0)))
    assert out.size == (100, 80)


def test_crop_clamps_out_of_range() -> None:
    img = Image.new("RGB", (100, 80), (0, 0, 0))
    out = render_display(img, Adjustments(crop=(0.5, 0.5, 1.0, 1.0)))
    # right/bottom clamp to 100/80 -> 50 wide x 40 tall
    assert out.size == (50, 40)
