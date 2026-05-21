from __future__ import annotations

import itertools
import math
import random
from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QContextMenuEvent,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontMetricsF,
    QIcon,
    QImage,
    QKeyEvent,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QResizeEvent,
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

from ocr_snap.models import OCRResults, SelectionModel, array_from_pixmap, item_color
from ocr_snap.theme import Icons, Tokens

if TYPE_CHECKING:
    from ocr_snap.models import ImageState

_FPS = 30
_SCAN_SPEED = 0.008  # fraction of image height per tick
_SPARKS_PER_TICK_FULL = 3
_SPARKS_PER_TICK_MINIMAL = 0
_SPARK_MAX_AGE = 25  # ticks
_REVEAL_FADE_FRAMES = 8  # frames for item fade-in at _FPS

_SQUARE_SIZE = 24
_SQUARE_SPACING = 6
_PLUS_WIDTH = 16


def _make_order_icon(indices: tuple[int, ...]) -> QIcon:
    """Create an icon with colored squares representing the merge order."""
    n = len(indices)
    width = n * _SQUARE_SIZE + (n - 1) * (_SQUARE_SPACING + _PLUS_WIDTH + _SQUARE_SPACING)
    height = _SQUARE_SIZE + 6  # small vertical padding
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont()
    font.setPixelSize(16)
    font.setBold(True)
    painter.setFont(font)
    y = 2
    x = 0
    for i, idx in enumerate(indices):
        color = item_color(idx)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(130), 1))
        painter.drawRoundedRect(x, y, _SQUARE_SIZE, _SQUARE_SIZE, 2, 2)
        # Draw index number centered in the square
        painter.setPen(QPen(QColor(0, 0, 0, 180)))
        painter.drawText(x, y, _SQUARE_SIZE, _SQUARE_SIZE, Qt.AlignmentFlag.AlignCenter, str(idx + 1))
        x += _SQUARE_SIZE
        if i < n - 1:
            x += _SQUARE_SPACING
            painter.setPen(QPen(QColor(180, 180, 180)))
            painter.drawText(x, y, _PLUS_WIDTH, _SQUARE_SIZE, Qt.AlignmentFlag.AlignCenter, "+")
            x += _PLUS_WIDTH + _SQUARE_SPACING
    painter.end()
    return QIcon(pixmap)


def _add_merge_permutation_actions(
    menu: QMenu,
    indices: list[int],
    callback: Callable[[list[int]], None],
) -> None:
    """Add merge actions for all permutations of the selected indices."""
    perms = list(itertools.permutations(indices))
    if len(perms) == 1:
        icon = _make_order_icon(perms[0])
        order = list(perms[0])
        menu.addAction(icon, "Merge", lambda o=order: callback(o))  # type: ignore[misc]
    else:
        merge_menu = menu.addMenu(Icons.merge(), f"Merge selected ({len(indices)})")
        for perm in perms:
            icon = _make_order_icon(perm)
            order = list(perm)
            merge_menu.addAction(icon, "", lambda o=order: callback(o))  # type: ignore[misc]


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


class TextOverlayItem(QGraphicsItem):
    """Renders OCR text inside a bounding box with translucent background."""

    def __init__(self, rect: QRectF, text: str) -> None:
        super().__init__()
        self._rect = rect
        self._text = text
        self._font = QFont()
        self._fit_font()
        self.setZValue(15)

    def set_text(self, text: str) -> None:
        self._text = text
        self._fit_font()
        self.update()

    def _fit_font(self) -> None:
        """Choose a font size that fits the text inside the bounding box."""
        w, h = self._rect.width(), self._rect.height()
        # Start at ~70% of box height, scale down to fit width
        size = max(h * 0.7, 4.0)
        self._font.setPixelSize(int(size))
        fm = QFontMetricsF(self._font)
        text_width = fm.horizontalAdvance(self._text)
        if text_width > 0 and text_width > w * 0.9:
            size = size * (w * 0.9) / text_width
        size = max(size, 4.0)
        self._font.setPixelSize(int(size))

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(
        self,
        painter: QPainter | None,
        _option: object,
        _widget: object = None,
    ) -> None:
        if painter is None:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Translucent background
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(QColor(0, 0, 0, 140)))
        painter.drawRect(self._rect)

        # Build text path for outlined text
        fm = QFontMetricsF(self._font)
        text_rect = fm.boundingRect(self._rect, Qt.AlignmentFlag.AlignCenter, self._text)
        path = QPainterPath()
        path.addText(text_rect.x(), text_rect.y() + fm.ascent(), self._font, self._text)

        # Black outline
        painter.setPen(QPen(QColor(0, 0, 0), 3.0))
        painter.setBrush(QBrush(Qt.GlobalColor.transparent))
        painter.drawPath(path)

        # White fill
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawPath(path)


class OCRCanvas(QGraphicsView):
    image_loaded = pyqtSignal(np.ndarray, QPixmap)
    merge_requested = pyqtSignal(list)
    delete_requested = pyqtSignal()

    def __init__(self, parent: QGraphicsView | None = None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.setBackgroundBrush(QBrush(QColor(Tokens.bg_base)))

        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setAcceptDrops(True)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

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

        # Text overlay state
        self._overlay_items: list[TextOverlayItem] = []
        self._overlay_visible = False

        # Processing overlay state
        self._processing = False
        self._overlay: QGraphicsRectItem | None = None
        self._scan_line: QGraphicsRectItem | None = None
        self._sparks: list[_Spark] = []
        self._scan_pos = 0.0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(1000 // _FPS)
        self._anim_timer.timeout.connect(self._anim_tick)

        self._animation_mode: str = "full"  # overridden by set_animation_mode
        self._sparks_per_tick = _SPARKS_PER_TICK_FULL

        self.show_placeholder()

    # ── Processing overlay ──────────────────────────────────────────

    def set_animation_mode(self, mode: str) -> None:
        """mode is one of 'off', 'minimal', 'full'."""
        self._animation_mode = mode
        if mode == "full":
            self._sparks_per_tick = _SPARKS_PER_TICK_FULL
        else:  # "minimal" or "off"
            self._sparks_per_tick = _SPARKS_PER_TICK_MINIMAL

    def set_processing(self, active: bool) -> None:
        if active and not self._processing and self._pixmap_item is not None:
            self._start_processing()
        elif not active and self._processing:
            self._stop_processing()

    def _start_processing(self) -> None:
        self._processing = True
        rect = self.sceneRect()

        # Dim overlay (always shown so the user knows something's happening)
        self._overlay = QGraphicsRectItem(rect)
        self._overlay.setBrush(QBrush(QColor(0, 0, 0, 120)))
        self._overlay.setPen(QPen(Qt.PenStyle.NoPen))
        self._overlay.setZValue(50)
        self._scene.addItem(self._overlay)

        if self._animation_mode == "off":
            return  # no scan line, no sparks, no timer

        # Scan line — kept for both minimal and full
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
        for _ in range(self._sparks_per_tick):
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
            f'<div style="text-align:center;">'
            f'<p style="font-size:{Tokens.text_hero + 6}px; color:{Tokens.text_muted}; font-weight:600;">'
            f'Paste or drop an image</p>'
            f'<p style="font-size:{Tokens.text_lg}px; color:{Tokens.text_muted}; margin-top:8px; opacity:0.7;">'
            f'Ctrl+V from clipboard &nbsp;&middot;&nbsp; drag &amp; drop a file</p>'
            f'</div>'
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

    # ── Load image state (switch without emitting image_loaded) ──────

    def load_image_state(self, state: ImageState) -> None:
        self._remove_placeholder()
        self._stop_processing()

        # Clear existing scene items
        for gfx_item in self._ocr_items:
            self._scene.removeItem(gfx_item)
        self._ocr_items.clear()
        self._clear_overlay_items()
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

        self.fitInView(pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

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
        self._clear_overlay_items()
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

        self.set_overlay_texts(results.items)

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

    # ── Text overlay ─────────────────────────────────────────────

    def _clear_overlay_items(self) -> None:
        for item in self._overlay_items:
            self._scene.removeItem(item)
        self._overlay_items.clear()

    def set_overlay_texts(self, items: list[object]) -> None:
        """Create text overlay items from OCRResultItem list."""
        from ocr_snap.models import OCRResultItem

        self._clear_overlay_items()
        for ocr_item in items:  # type: ignore[union-attr]
            assert isinstance(ocr_item, OCRResultItem)
            text = ocr_item.translated_text or ocr_item.text
            bbox_rect = QRectF(
                ocr_item.bbox[0],
                ocr_item.bbox[1],
                ocr_item.bbox[2] - ocr_item.bbox[0],
                ocr_item.bbox[3] - ocr_item.bbox[1],
            )
            overlay = TextOverlayItem(bbox_rect, text)
            overlay.setVisible(self._overlay_visible)
            self._scene.addItem(overlay)
            self._overlay_items.append(overlay)

    def set_overlay_visible(self, visible: bool) -> None:
        self._overlay_visible = visible
        for item in self._overlay_items:
            item.setVisible(visible)

    # ── Context menu ──────────────────────────────────────────────

    def contextMenuEvent(self, event: QContextMenuEvent | None) -> None:
        if event is None or self._selection_model is None:
            super().contextMenuEvent(event)
            return
        sel = self._selection_model.selected_indices
        if len(sel) < 1:
            super().contextMenuEvent(event)
            return
        menu = QMenu(self)
        if len(sel) == 1:
            menu.addAction(Icons.delete(), "Delete", self.delete_requested.emit)
        else:
            menu.addAction(
                Icons.delete(), f"Delete selected ({len(sel)})", self.delete_requested.emit
            )
            _add_merge_permutation_actions(
                menu, sorted(sel), lambda order: self.merge_requested.emit(order)
            )
        menu.exec(event.globalPos())

    # ── Image loading ───────────────────────────────────────────────

    def _load_qimage(self, qimg: QImage) -> None:
        if qimg.isNull():
            return

        self._remove_placeholder()

        pixmap = QPixmap.fromImage(qimg)
        arr = array_from_pixmap(pixmap)
        if self._pixmap_item:
            self._scene.removeItem(self._pixmap_item)
        for gfx_item in self._ocr_items:
            self._scene.removeItem(gfx_item)
        self._ocr_items.clear()
        self._clear_overlay_items()

        pixmap_item = self._scene.addPixmap(pixmap)
        assert pixmap_item is not None
        pixmap_item.setZValue(0)
        self._pixmap_item = pixmap_item
        self.setSceneRect(QRectF(pixmap.rect().toRectF()))
        self.fitInView(pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

        self.image_loaded.emit(arr, pixmap)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        if self._pixmap_item is not None:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

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
