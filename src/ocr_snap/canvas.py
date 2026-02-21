from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QContextMenuEvent,
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QKeyEvent,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
    QResizeEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QGraphicsTextItem,
    QGraphicsView,
    QMenu,
)

from ocr_snap.models import OCRResults, SelectionModel, item_color

if TYPE_CHECKING:
    from ocr_snap.models import ImageState

_ZOOM_FACTOR = 1.15
_ZOOM_MIN = 0.1
_ZOOM_MAX = 10.0

_FPS = 30
_SCAN_SPEED = 0.008  # fraction of image height per tick
_SPARKS_PER_TICK = 3
_SPARK_MAX_AGE = 25  # ticks
_REVEAL_FADE_FRAMES = 8  # frames for item fade-in at _FPS


class _Spark:
    __slots__ = ("item", "vx", "vy", "age", "max_age", "base_opacity")

    def __init__(
        self, item: QGraphicsEllipseItem, vx: float, vy: float, max_age: int
    ) -> None:
        self.item = item
        self.vx = vx
        self.vy = vy
        self.age = 0
        self.max_age = max_age
        self.base_opacity = 0.6 + random.random() * 0.4


class BBoxGraphicsItem(QGraphicsRectItem):
    def __init__(
        self, rect: QRectF, index: int, color: QColor, selection_model: SelectionModel
    ):
        super().__init__(rect)
        self._base_rect = rect
        self._index = index
        self._color = color
        self._selection_model = selection_model

        self.setAcceptHoverEvents(True)
        self.setZValue(10)
        self._apply_style()

        selection_model.hovered_changed.connect(self._on_hover_changed)
        selection_model.selection_changed.connect(self._on_selection_changed)

    def _apply_style(self) -> None:
        hovered = self._selection_model.hovered_index == self._index
        selected = self._selection_model.is_selected(self._index)

        if selected:
            pen_width = 3
            fill = QColor(self._color)
            fill.setAlpha(30)
            self.setBrush(QBrush(fill))
        elif hovered:
            pen_width = 2
            self.setBrush(QBrush(Qt.GlobalColor.transparent))
        else:
            pen_width = 1
            self.setBrush(QBrush(Qt.GlobalColor.transparent))

        self.setPen(QPen(self._color, pen_width))
        # Inset rect so the outer visual edge stays fixed regardless of pen width.
        # QPen draws centered on the boundary; half the width extends outward.
        inset = (pen_width - 1) / 2.0
        self.setRect(self._base_rect.adjusted(inset, inset, -inset, -inset))

    def _on_hover_changed(self, _index: int) -> None:
        self._apply_style()

    def _on_selection_changed(self) -> None:
        self._apply_style()

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent | None) -> None:  # type: ignore[override]
        self._selection_model.hovered_index = self._index
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent | None) -> None:  # type: ignore[override]
        if self._selection_model.hovered_index == self._index:
            self._selection_model.hovered_index = -1
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:  # type: ignore[override]
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._selection_model.toggle(self._index)
            else:
                self._selection_model.select(self._index)
        super().mousePressEvent(event)


class OCRCanvas(QGraphicsView):
    image_loaded = pyqtSignal(np.ndarray, QPixmap)
    merge_requested = pyqtSignal()

    def __init__(self, parent: QGraphicsView | None = None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.setBackgroundBrush(QBrush(QColor(30, 30, 30)))

        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setAcceptDrops(True)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

        self._zoom = 1.0
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._ocr_items: list[QGraphicsItem] = []
        self._placeholder: QGraphicsTextItem | None = None
        self._selection_model: SelectionModel | None = None

        # Reveal animation state
        self._item_groups: list[list[QGraphicsItem]] = []
        self._fading_groups: list[tuple[list[QGraphicsItem], float]] = []
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(1000 // _FPS)
        self._fade_timer.timeout.connect(self._fade_tick)

        # Processing overlay state
        self._processing = False
        self._overlay: QGraphicsRectItem | None = None
        self._scan_line: QGraphicsRectItem | None = None
        self._sparks: list[_Spark] = []
        self._scan_pos = 0.0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(1000 // _FPS)
        self._anim_timer.timeout.connect(self._anim_tick)

        self.show_placeholder()

    # ── Processing overlay ──────────────────────────────────────────

    def set_processing(self, active: bool) -> None:
        if active and not self._processing and self._pixmap_item is not None:
            self._start_processing()
        elif not active and self._processing:
            self._stop_processing()

    def _start_processing(self) -> None:
        self._processing = True
        rect = self.sceneRect()

        # Dim overlay
        self._overlay = QGraphicsRectItem(rect)
        self._overlay.setBrush(QBrush(QColor(0, 0, 0, 120)))
        self._overlay.setPen(QPen(Qt.PenStyle.NoPen))
        self._overlay.setZValue(50)
        self._scene.addItem(self._overlay)

        # Scan line — a thin horizontal band with a glow gradient
        scan_h = rect.height() * 0.012
        self._scan_line = QGraphicsRectItem(rect.x(), rect.y(), rect.width(), scan_h)
        grad = QLinearGradient(0, 0, 0, scan_h)
        grad.setColorAt(0.0, QColor(255, 190, 50, 0))
        grad.setColorAt(0.4, QColor(255, 190, 50, 100))
        grad.setColorAt(0.5, QColor(255, 225, 100, 200))
        grad.setColorAt(0.6, QColor(255, 190, 50, 100))
        grad.setColorAt(1.0, QColor(255, 190, 50, 0))
        self._scan_line.setBrush(QBrush(grad))
        self._scan_line.setPen(QPen(Qt.PenStyle.NoPen))
        self._scan_line.setZValue(51)
        self._scene.addItem(self._scan_line)

        self._scan_pos = 0.0
        self._sparks.clear()
        self._anim_timer.start()

    def _stop_processing(self) -> None:
        self._processing = False
        self._anim_timer.stop()

        if self._overlay is not None:
            self._scene.removeItem(self._overlay)
            self._overlay = None
        if self._scan_line is not None:
            self._scene.removeItem(self._scan_line)
            self._scan_line = None
        for spark in self._sparks:
            self._scene.removeItem(spark.item)
        self._sparks.clear()

    def _anim_tick(self) -> None:
        rect = self.sceneRect()
        h = rect.height()
        w = rect.width()

        # Advance scan line
        self._scan_pos += _SCAN_SPEED
        if self._scan_pos > 1.0:
            self._scan_pos -= 1.0
        scan_y = rect.y() + h * self._scan_pos

        if self._scan_line is not None:
            self._scan_line.setPos(0, scan_y - self._scan_line.rect().y())

        # Spawn sparks along the scan line
        for _ in range(_SPARKS_PER_TICK):
            x = rect.x() + random.random() * w
            y = scan_y + random.gauss(0, h * 0.006)
            size = random.uniform(1.0, 6.0)

            grad = QRadialGradient(size / 2, size / 2, size / 2)
            grad.setColorAt(0.0, QColor(255, 240, 150, 220))
            grad.setColorAt(0.5, QColor(255, 190, 50, 120))
            grad.setColorAt(1.0, QColor(200, 150, 20, 0))

            dot = QGraphicsEllipseItem(0, 0, size, size)
            dot.setBrush(QBrush(grad))
            dot.setPen(QPen(Qt.PenStyle.NoPen))
            dot.setPos(x, y)
            dot.setZValue(52)
            self._scene.addItem(dot)

            angle = random.uniform(0, 2 * math.pi)
            speed = 0.3 + random.random() * 0.8
            self._sparks.append(
                _Spark(
                    dot,
                    math.cos(angle) * speed,
                    -abs(math.sin(angle)) * speed * 0.6,
                    _SPARK_MAX_AGE,
                )
            )

        # Update & cull sparks
        alive: list[_Spark] = []
        for s in self._sparks:
            s.age += 1
            if s.age >= s.max_age:
                self._scene.removeItem(s.item)
                continue
            s.item.moveBy(s.vx, s.vy)
            s.vy += 0.02  # slight gravity
            t = s.age / s.max_age
            s.item.setOpacity(s.base_opacity * (1.0 - t * t))
            alive.append(s)
        self._sparks = alive

    # ── Placeholder ─────────────────────────────────────────────────

    def show_placeholder(self) -> None:
        self._remove_placeholder()
        html = (
            '<div style="text-align:center;">'
            '<p style="font-size:28px; color:#666; font-weight:600;">'
            "Paste or drop an image</p>"
            '<p style="font-size:14px; color:#555; margin-top:8px;">'
            "Ctrl+V from clipboard &nbsp;&middot;&nbsp; drag &amp; drop a file</p>"
            "</div>"
        )
        self._placeholder = QGraphicsTextItem()
        self._placeholder.setHtml(html)
        self._placeholder.setTextWidth(400)
        br = self._placeholder.boundingRect()
        self._placeholder.setPos(-br.width() / 2, -br.height() / 2)
        self._scene.addItem(self._placeholder)
        self.setSceneRect(-250, -150, 500, 300)

    def _remove_placeholder(self) -> None:
        if self._placeholder is not None:
            self._scene.removeItem(self._placeholder)
            self._placeholder = None

    # ── View state save/restore ──────────────────────────────────────

    def save_view_state(self) -> tuple[float, QPointF]:
        vp = self.viewport()
        assert vp is not None
        center = self.mapToScene(vp.rect().center())
        return (self._zoom, center)

    def restore_view_state(self, zoom: float, center: QPointF) -> None:
        self.resetTransform()
        self._zoom = zoom
        self.scale(zoom, zoom)
        self.centerOn(center)

    # ── Load image state (switch without emitting image_loaded) ──────

    def load_image_state(self, state: ImageState) -> None:
        self._remove_placeholder()
        self._stop_processing()

        # Clear existing scene items
        for gfx_item in self._ocr_items:
            self._scene.removeItem(gfx_item)
        self._ocr_items.clear()
        self._item_groups.clear()
        self._fading_groups.clear()
        self._fade_timer.stop()

        if self._pixmap_item is not None:
            self._scene.removeItem(self._pixmap_item)

        # Display the image
        pixmap_item = self._scene.addPixmap(state.pixmap)
        assert pixmap_item is not None
        pixmap_item.setZValue(0)
        self._pixmap_item = pixmap_item
        self.setSceneRect(QRectF(state.pixmap.rect().toRectF()))

        # Restore view transform or fit
        if state.view_zoom is not None and state.view_center is not None:
            self.restore_view_state(state.view_zoom, state.view_center)
        else:
            self.fitInView(pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = self.transform().m11()

        # Restore OCR overlays if results exist
        if state.ocr_results is not None:
            self.set_ocr_results(state.ocr_results, state.selection_model, visible=True)

    # ── OCR results ─────────────────────────────────────────────────

    def set_ocr_results(
        self,
        results: OCRResults,
        selection_model: SelectionModel,
        *,
        visible: bool = False,
    ) -> None:
        for gfx_item in self._ocr_items:
            self._scene.removeItem(gfx_item)
        self._ocr_items.clear()
        self._item_groups.clear()
        self._fading_groups.clear()
        self._fade_timer.stop()
        self._selection_model = selection_model

        if not results.items:
            return

        for ocr_item in results.items:
            bbox_rect = QRectF(
                ocr_item.bbox[0],
                ocr_item.bbox[1],
                ocr_item.bbox[2] - ocr_item.bbox[0],
                ocr_item.bbox[3] - ocr_item.bbox[1],
            )

            color = item_color(ocr_item.index)
            bbox_gfx = BBoxGraphicsItem(
                bbox_rect, ocr_item.index, color, selection_model
            )
            bbox_gfx.setOpacity(0.0 if not visible else 1.0)
            self._scene.addItem(bbox_gfx)
            self._ocr_items.append(bbox_gfx)
            self._item_groups.append([bbox_gfx])

    def set_item_visible(self, index: int, visible: bool) -> None:
        if 0 <= index < len(self._ocr_items):
            self._ocr_items[index].setOpacity(1.0 if visible else 0.0)

    def reveal_item(self, index: int) -> None:
        if 0 <= index < len(self._item_groups):
            self._fading_groups.append((self._item_groups[index], 0.0))
            if not self._fade_timer.isActive():
                self._fade_timer.start()

    def _fade_tick(self) -> None:
        step = 1.0 / _REVEAL_FADE_FRAMES
        still_fading: list[tuple[list[QGraphicsItem], float]] = []
        for items, progress in self._fading_groups:
            progress = min(progress + step, 1.0)
            eased = 1.0 - (1.0 - progress) ** 2  # ease-out quadratic
            for item in items:
                item.setOpacity(eased)
            if progress < 1.0:
                still_fading.append((items, progress))
        self._fading_groups = still_fading
        if not self._fading_groups:
            self._fade_timer.stop()

    # ── Context menu ──────────────────────────────────────────────

    def contextMenuEvent(self, event: QContextMenuEvent | None) -> None:
        if event is None or self._selection_model is None:
            super().contextMenuEvent(event)
            return
        sel = self._selection_model.selected_indices
        if len(sel) < 2:
            super().contextMenuEvent(event)
            return
        menu = QMenu(self)
        menu.addAction(f"Merge selected ({len(sel)})", self.merge_requested.emit)
        menu.exec(event.globalPos())

    # ── Image loading ───────────────────────────────────────────────

    def _load_qimage(self, qimg: QImage) -> None:
        if qimg.isNull():
            return

        self._remove_placeholder()

        qimg_rgb = qimg.convertToFormat(QImage.Format.Format_RGB888)
        ptr = qimg_rgb.bits()
        if ptr is None:
            return
        h, w = qimg_rgb.height(), qimg_rgb.width()
        bpl = qimg_rgb.bytesPerLine()
        ptr.setsize(bpl * h)
        buf = np.frombuffer(ptr, dtype=np.uint8).reshape(h, bpl)  # type: ignore[call-overload]
        arr = buf[:, : w * 3].reshape(h, w, 3).copy()

        pixmap = QPixmap.fromImage(qimg)
        if self._pixmap_item:
            self._scene.removeItem(self._pixmap_item)
        for gfx_item in self._ocr_items:
            self._scene.removeItem(gfx_item)
        self._ocr_items.clear()

        pixmap_item = self._scene.addPixmap(pixmap)
        assert pixmap_item is not None
        pixmap_item.setZValue(0)
        self._pixmap_item = pixmap_item
        self.setSceneRect(QRectF(pixmap.rect().toRectF()))
        self.fitInView(pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()

        self.image_loaded.emit(arr, pixmap)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        if self._pixmap_item is not None:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = self.transform().m11()

    # ── Input events ────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is not None and event.matches(QKeySequence.StandardKey.Paste):
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                qimg = clipboard.image()
                if not qimg.isNull():
                    self._load_qimage(qimg)
                    return
        super().keyPressEvent(event)

    def open_file(self, path: str) -> None:
        qimg = QImage(path)
        if not qimg.isNull():
            self._load_qimage(qimg)

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if (
            event is not None
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            if event.angleDelta().y() > 0:
                factor = _ZOOM_FACTOR
            else:
                factor = 1 / _ZOOM_FACTOR

            new_zoom = self._zoom * factor
            if _ZOOM_MIN <= new_zoom <= _ZOOM_MAX:
                self._zoom = new_zoom
                self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        mime = event.mimeData() if event is not None else None
        if mime is not None and mime.hasUrls():
            event.acceptProposedAction()  # type: ignore[union-attr]
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragEnterEvent | None) -> None:  # type: ignore[override]
        mime = event.mimeData() if event is not None else None
        if mime is not None and mime.hasUrls():
            event.acceptProposedAction()  # type: ignore[union-attr]
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent | None) -> None:
        mime = event.mimeData() if event is not None else None
        if mime is not None and mime.hasUrls():
            for url in mime.urls():
                path = url.toLocalFile()
                if path:
                    self.open_file(path)
                    break
            event.acceptProposedAction()  # type: ignore[union-attr]
        else:
            super().dropEvent(event)
