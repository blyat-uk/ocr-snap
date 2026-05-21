from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import QObject, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPixmap


def item_color(index: int) -> QColor:
    """Return a distinct color for the given item index."""
    hue = (index * 137.5) % 360  # golden-angle spacing
    return QColor.fromHslF(hue / 360.0, 0.7, 0.6)


def array_from_qimage(qimg: QImage) -> np.ndarray:
    """Convert a QImage to an RGB uint8 numpy array (H, W, 3).

    Workhorse used by ``array_from_pixmap`` and by the canvas's
    direct-from-QImage paste path.
    """
    rgb = qimg.convertToFormat(QImage.Format.Format_RGB888)
    ptr = rgb.bits()
    if ptr is None:
        raise RuntimeError("QImage.bits() returned None")
    h, w = rgb.height(), rgb.width()
    bpl = rgb.bytesPerLine()
    ptr.setsize(bpl * h)
    buf = np.frombuffer(ptr, dtype=np.uint8).reshape(h, bpl)  # type: ignore[call-overload]
    return buf[:, : w * 3].reshape(h, w, 3).copy()


def array_from_pixmap(
    pixmap: QPixmap, *, max_long_side: int | None = None
) -> np.ndarray:
    """Convert a QPixmap to an RGB uint8 numpy array (H, W, 3).

    If ``max_long_side`` is given and the pixmap's longer side
    exceeds it, the pixmap's QImage is scaled down (smooth
    transformation, aspect ratio preserved) before conversion.
    """
    qimg = pixmap.toImage()
    if max_long_side is not None and max(qimg.width(), qimg.height()) > max_long_side:
        qimg = qimg.scaled(
            max_long_side,
            max_long_side,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return array_from_qimage(qimg)


@dataclass
class OCRResultItem:
    index: int
    text: str
    confidence: float
    polygon: np.ndarray  # shape (4, 2)
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    translated_text: str | None = None


@dataclass
class OCRResults:
    items: list[OCRResultItem]
    image_width: int
    image_height: int


class ImageState:
    def __init__(self, image_id: str, pixmap: QPixmap, array: np.ndarray | None) -> None:
        self.image_id = image_id
        self.pixmap = pixmap
        self.array: np.ndarray | None = array
        self.selection_model = SelectionModel()
        self.ocr_results: OCRResults | None = None
        self.ocr_running: bool = False
        self.translation_running: bool = False
        self.view_zoom: float | None = None
        self.view_center: QPointF | None = None
        self.confidence_filter: float = 0.5
        self.ocr_threshold: float = 0.5
        self.overlay_enabled: bool = False


class SelectionModel(QObject):
    hovered_changed = pyqtSignal(int)
    selection_changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._hovered_index: int = -1
        self._selected_indices: set[int] = set()

    @property
    def hovered_index(self) -> int:
        return self._hovered_index

    @hovered_index.setter
    def hovered_index(self, value: int) -> None:
        if self._hovered_index != value:
            self._hovered_index = value
            self.hovered_changed.emit(value)

    @property
    def selected_indices(self) -> frozenset[int]:
        return frozenset(self._selected_indices)

    def is_selected(self, index: int) -> bool:
        return index in self._selected_indices

    def select(self, index: int) -> None:
        """Clear others and select a single index (regular click)."""
        if self._selected_indices != {index}:
            self._selected_indices = {index}
            self.selection_changed.emit()

    def toggle(self, index: int) -> None:
        """Add or remove index from the set (Ctrl+click)."""
        if index in self._selected_indices:
            self._selected_indices.discard(index)
        else:
            self._selected_indices.add(index)
        self.selection_changed.emit()

    def clear(self) -> None:
        if self._selected_indices:
            self._selected_indices.clear()
            self.selection_changed.emit()
