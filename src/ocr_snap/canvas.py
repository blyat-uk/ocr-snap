from __future__ import annotations

import itertools
import math
import random
from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np
from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QContextMenuEvent,
    QDragEnterEvent,
    QDropEvent,
    QEnterEvent,
    QFont,
    QFontMetricsF,
    QIcon,
    QImage,
    QKeyEvent,
    QKeySequence,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QRadialGradient,
    QResizeEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGestureEvent,
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
    QPinchGesture,
    QWidget,
    QWidgetAction,
)

from ocr_snap.models import OCRResults, SelectionModel, array_from_qimage, item_color
from ocr_snap.perf_settings import DISPLAY_LONG_SIDE
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

_MAX_SCALE = 8.0


def _order_row_width(n: int) -> int:
    """Pixel width of a row of ``n`` colored squares with ``+`` separators."""
    return n * _SQUARE_SIZE + (n - 1) * (_SQUARE_SPACING + _PLUS_WIDTH + _SQUARE_SPACING)


def _draw_square(painter: QPainter, idx: int, x: int, y: int) -> None:
    """Draw one rounded color square with its 1-based index centered, at (x, y)."""
    font = QFont()
    font.setPixelSize(16)
    font.setBold(True)
    painter.setFont(font)
    color = item_color(idx)
    painter.setBrush(QBrush(color))
    painter.setPen(QPen(color.darker(130), 1))
    painter.drawRoundedRect(x, y, _SQUARE_SIZE, _SQUARE_SIZE, 2, 2)
    painter.setPen(QPen(QColor(0, 0, 0, 180)))
    painter.drawText(x, y, _SQUARE_SIZE, _SQUARE_SIZE, Qt.AlignmentFlag.AlignCenter, str(idx + 1))


def _paint_order_squares(
    painter: QPainter, indices: tuple[int, ...], origin_x: int, origin_y: int
) -> None:
    """Paint the merge-order squares (numbered, '+'-separated) at a fixed size.

    Squares are always ``_SQUARE_SIZE`` px; the row simply grows wider with more
    labels. The caller owns ``painter`` and is responsible for ending it.
    """
    n = len(indices)
    x = origin_x
    y = origin_y
    for i, idx in enumerate(indices):
        _draw_square(painter, idx, x, y)
        x += _SQUARE_SIZE
        if i < n - 1:
            x += _SQUARE_SPACING
            painter.setPen(QPen(QColor(180, 180, 180)))
            painter.drawText(x, y, _PLUS_WIDTH, _SQUARE_SIZE, Qt.AlignmentFlag.AlignCenter, "+")
            x += _PLUS_WIDTH + _SQUARE_SPACING


def _make_order_icon(indices: tuple[int, ...]) -> QIcon:
    """Create an icon with colored squares representing the merge order."""
    width = _order_row_width(len(indices))
    height = _SQUARE_SIZE + 6  # small vertical padding
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _paint_order_squares(painter, indices, 0, 2)
    painter.end()
    return QIcon(pixmap)


def _make_swatch_icon(idx: int) -> QIcon:
    """A single square color swatch icon, used as the icon for pick-level
    cascade submenu rows. Square so it scales cleanly in QMenu's icon slot."""
    pixmap = QPixmap(_SQUARE_SIZE, _SQUARE_SIZE)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _draw_square(painter, idx, 0, 0)
    painter.end()
    return QIcon(pixmap)


_ORDINAL_WORDS = (
    "first", "second", "third", "fourth", "fifth",
    "sixth", "seventh", "eighth", "ninth", "tenth",
)


def _ordinal(n: int) -> str:
    """1-based ordinal word ('first'..'tenth'); falls back to '{n}th'."""
    return _ORDINAL_WORDS[n - 1] if 1 <= n <= len(_ORDINAL_WORDS) else f"{n}th"


class _MergeOrderWidget(QWidget):
    """Menu-row widget that paints the merge-order squares at full, fixed size.

    Using a widget instead of a QAction icon avoids QMenu's 16px icon slot,
    which scaled the wide swatch row down (the more labels, the tinier the
    squares). Here squares stay ``_SQUARE_SIZE`` px and the row grows wider.
    """

    clicked = pyqtSignal()

    _PAD_X = 10
    _PAD_Y = 4

    def __init__(self, indices: tuple[int, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._indices = indices
        self._hover = False
        self.setMouseTracking(True)
        self.setFixedSize(
            _order_row_width(len(indices)) + 2 * self._PAD_X,
            _SQUARE_SIZE + 2 * self._PAD_Y,
        )

    def enterEvent(self, event: QEnterEvent | None) -> None:  # type: ignore[override]
        self._hover = True
        self.update()

    def leaveEvent(self, event: QEvent | None) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:  # type: ignore[override]
        if (
            event is not None
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover:
            painter.fillRect(self.rect(), self.palette().highlight())
        _paint_order_squares(painter, self._indices, self._PAD_X, self._PAD_Y)
        painter.end()


class _MergeOrderAction(QWidgetAction):
    """A menu action whose row is a fixed-size merge-order swatch preview.

    ``order`` is the full label order emitted on click; ``display`` (defaults to
    ``order``) is what the swatch row renders — the cascade leaf shows only the
    final two labels while still emitting the full navigated order.
    """

    def __init__(
        self,
        order: tuple[int, ...] | list[int],
        callback: Callable[[list[int]], None],
        parent: QObject | None = None,
        *,
        display: tuple[int, ...] | None = None,
    ) -> None:
        super().__init__(parent)
        self._order = list(order)
        self._callback = callback
        shown = tuple(order) if display is None else display
        widget = _MergeOrderWidget(shown)
        widget.clicked.connect(self._activate)
        self.setDefaultWidget(widget)

    def _activate(self) -> None:
        self._callback(self._order)
        # Mirror a normal action click: tear down the whole open menu chain
        # (this submenu plus its parent context menu).
        w: QWidget | None = self.defaultWidget()
        while w is not None:
            if isinstance(w, QMenu):
                w.close()
            w = w.parentWidget()


_FLAT_MENU_MAX = 3  # selections up to this many use the flat permutation menu


def _populate_cascade_level(
    menu: QMenu,
    prefix: list[int],
    remaining: list[int],
    callback: Callable[[list[int]], None],
) -> None:
    """Fill one cascade level.

    With more than two labels left, offer one swatch submenu per remaining label
    (pick the next item); each child is populated lazily. With exactly two left,
    offer the two final orders as leaf rows that display only those two swatches
    but emit the full ``prefix + permutation`` order.
    """
    if len(remaining) == 2:
        menu.addSection("Select the rest")
        for perm in itertools.permutations(remaining):
            order = prefix + list(perm)
            menu.addAction(_MergeOrderAction(order, callback, menu, display=perm))
        return
    menu.addSection(f"Select the {_ordinal(len(prefix) + 1)} item")
    for label in remaining:
        sub = menu.addMenu(_make_swatch_icon(label), "")
        rest = [x for x in remaining if x != label]
        _connect_lazy_cascade(sub, prefix + [label], rest, callback)


def _connect_lazy_cascade(
    submenu: QMenu,
    prefix: list[int],
    remaining: list[int],
    callback: Callable[[list[int]], None],
) -> None:
    """Populate ``submenu`` the first time it is about to be shown."""
    built = {"done": False}

    def build() -> None:
        if built["done"]:
            return
        built["done"] = True
        _populate_cascade_level(submenu, prefix, remaining, callback)

    submenu.aboutToShow.connect(build)


def _add_merge_permutation_actions(
    menu: QMenu,
    indices: list[int],
    callback: Callable[[list[int]], None],
) -> None:
    """Add merge actions for the selected indices.

    Up to ``_FLAT_MENU_MAX`` labels: a flat submenu listing every permutation.
    Beyond that: a lazily-built cascade that picks one label per level (depth
    N-1, last level = the final two), so no single menu ever holds the full N!
    set of orders.
    """
    n = len(indices)
    if n <= 1:
        if n == 1:
            order = list(indices)
            menu.addAction(  # type: ignore[misc]
                _make_order_icon(tuple(indices)), "Merge", lambda o=order: callback(o)
            )
        return
    if n <= _FLAT_MENU_MAX:
        merge_menu = menu.addMenu(Icons.merge(), f"Merge selected ({n})")
        for perm in itertools.permutations(indices):
            merge_menu.addAction(_MergeOrderAction(perm, callback, merge_menu))
        return
    root = menu.addMenu(Icons.merge(), f"Merge selected ({n})")
    _populate_cascade_level(root, [], list(indices), callback)


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
    crop_selected = pyqtSignal(QRectF)  # normalized (x, y, w, h) of the working pixmap
    crop_mode_changed = pyqtSignal(bool)  # crop mode entered/exited (incl. auto-exit)

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
        self.grabGesture(Qt.GestureType.PinchGesture)

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._effective_long_side: int = DISPLAY_LONG_SIDE
        self._bbox_scale: float = 1.0
        self._fit_to_view: bool = True
        self._ocr_items: list[QGraphicsItem] = []
        self._placeholder: QGraphicsTextItem | None = None
        self._selection_model: SelectionModel | None = None

        # Crop mode state
        self._crop_mode = False
        self._crop_origin: QPointF | None = None
        self._crop_rect_item: QGraphicsRectItem | None = None

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

    def set_effective_long_side(self, value: int) -> None:
        """The OCR-input long-side ceiling. Used by ``_load_qimage`` to
        produce the OCR-size array. The display pixmap remains at
        ``DISPLAY_LONG_SIDE``.
        """
        self._effective_long_side = value

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

    # ── Zoom ────────────────────────────────────────────────────────

    def _current_scale(self) -> float:
        return self.transform().m11()

    def _fit_scale(self) -> float:
        if self._pixmap_item is None:
            return 1.0
        br = self._pixmap_item.boundingRect()
        if br.width() <= 0 or br.height() <= 0:
            return 1.0
        vp = self.viewport().size()
        return min(vp.width() / br.width(), vp.height() / br.height())

    def _apply_zoom(self, factor: float) -> None:
        if self._pixmap_item is None:
            return
        current = self._current_scale()
        target = current * factor
        fit = self._fit_scale()
        target = max(fit, min(_MAX_SCALE, target))
        if target <= fit * 1.001:
            self._fit_to_view = True
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            return
        actual = target / current
        if actual == 1.0:
            return
        self.scale(actual, actual)
        self._fit_to_view = False

    def wheelEvent(self, event: QWheelEvent | None) -> None:  # type: ignore[override]
        if event is None or self._pixmap_item is None:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        factor = 1.0015 ** delta
        self._apply_zoom(factor)
        event.accept()

    def event(self, event: QEvent | None) -> bool:  # type: ignore[override]
        if event is not None and event.type() == QEvent.Type.Gesture:
            assert isinstance(event, QGestureEvent)
            pinch = event.gesture(Qt.GestureType.PinchGesture)
            if isinstance(pinch, QPinchGesture):
                if pinch.changeFlags() & QPinchGesture.ChangeFlag.ScaleFactorChanged:
                    self._apply_zoom(pinch.scaleFactor())
                event.accept(pinch)
                return True
        return super().event(event)

    # ── Placeholder ─────────────────────────────────────────────────

    def show_placeholder(self) -> None:
        self._remove_placeholder()
        # "⌘V" on macOS, "Ctrl+V" elsewhere.
        paste_keys = QKeySequence(QKeySequence.StandardKey.Paste).toString(
            QKeySequence.SequenceFormat.NativeText
        )
        html = (
            f'<div style="text-align:center;">'
            f'<p style="font-size:{Tokens.text_hero + 6}px; color:{Tokens.text_muted}; font-weight:600;">'
            f'Paste or drop an image</p>'
            f'<p style="font-size:{Tokens.text_lg}px; color:{Tokens.text_muted}; margin-top:8px; opacity:0.7;">'
            f'{paste_keys} from clipboard &nbsp;&middot;&nbsp; drag &amp; drop a file</p>'
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

        self.clear_results()

        if self._pixmap_item is not None:
            self._scene.removeItem(self._pixmap_item)

        # Display the image
        pixmap_item = self._scene.addPixmap(state.pixmap)
        assert pixmap_item is not None
        pixmap_item.setZValue(0)
        self._pixmap_item = pixmap_item
        self.setSceneRect(QRectF(state.pixmap.rect().toRectF()))

        self._fit_to_view = True
        self.fitInView(pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

        # Restore OCR overlays if results exist
        if state.ocr_results is not None:
            self.set_ocr_results(state.ocr_results, state.selection_model, visible=True)

    def set_working_pixmap(self, pixmap: QPixmap) -> None:
        """Swap the displayed image (live preview) without emitting
        ``image_loaded``. Preserves the current fit/zoom flag (fits if no
        image has been loaded yet).
        """
        self._remove_placeholder()
        if self._pixmap_item is not None:
            self._scene.removeItem(self._pixmap_item)
        item = self._scene.addPixmap(pixmap)
        assert item is not None
        item.setZValue(0)
        self._pixmap_item = item
        self.setSceneRect(QRectF(pixmap.rect().toRectF()))
        if self._fit_to_view:
            self.fitInView(item, Qt.AspectRatioMode.KeepAspectRatio)

    def clear_results(self) -> None:
        """Remove all OCR bbox + overlay items (e.g. when results go stale)."""
        for gfx_item in self._ocr_items:
            self._scene.removeItem(gfx_item)
        self._ocr_items.clear()
        self._clear_overlay_items()
        self._item_groups.clear()
        self._fading_groups.clear()
        self._fade_timer.stop()

    # ── Crop mode ────────────────────────────────────────────────────

    def set_crop_mode(self, enabled: bool) -> None:
        self._crop_mode = enabled
        if enabled:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            viewport = self.viewport()
            if viewport is not None:
                viewport.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            viewport = self.viewport()
            if viewport is not None:
                viewport.unsetCursor()
            self._remove_crop_rect()
            self._crop_origin = None
        self.crop_mode_changed.emit(enabled)

    def _remove_crop_rect(self) -> None:
        if self._crop_rect_item is not None:
            self._scene.removeItem(self._crop_rect_item)
            self._crop_rect_item = None

    def _update_crop_rect(self, origin: QPointF, current: QPointF) -> None:
        rect = QRectF(origin, current).normalized()
        if self._crop_rect_item is None:
            item = QGraphicsRectItem(rect)
            item.setPen(QPen(QColor(Tokens.accent), 0, Qt.PenStyle.DashLine))
            fill = QColor(Tokens.accent)
            fill.setAlpha(40)
            item.setBrush(QBrush(fill))
            item.setZValue(60)
            self._scene.addItem(item)
            self._crop_rect_item = item
        else:
            self._crop_rect_item.setRect(rect)

    def _finish_crop(self, origin: QPointF, end: QPointF) -> None:
        self._remove_crop_rect()
        if self._pixmap_item is None:
            self.set_crop_mode(False)
            return
        br = self._pixmap_item.boundingRect()
        w = br.width()
        h = br.height()
        if w <= 0 or h <= 0:
            self.set_crop_mode(False)
            return
        x1 = max(0.0, min(w, min(origin.x(), end.x())))
        x2 = max(0.0, min(w, max(origin.x(), end.x())))
        y1 = max(0.0, min(h, min(origin.y(), end.y())))
        y2 = max(0.0, min(h, max(origin.y(), end.y())))
        nx, ny = x1 / w, y1 / h
        nw, nh = (x2 - x1) / w, (y2 - y1) / h
        if nw < 0.01 or nh < 0.01:
            self.set_crop_mode(False)
            return
        self.crop_selected.emit(QRectF(nx, ny, nw, nh))
        self.set_crop_mode(False)

    # ── OCR results ─────────────────────────────────────────────────

    def set_ocr_results(
        self,
        results: OCRResults,
        selection_model: SelectionModel,
        *,
        visible: bool = False,
    ) -> None:
        self.clear_results()
        self._selection_model = selection_model

        if not results.items:
            return

        ocr_w = results.image_width
        display_w = self._pixmap_item.boundingRect().width() if self._pixmap_item else ocr_w
        self._bbox_scale = display_w / ocr_w if ocr_w else 1.0

        for ocr_item in results.items:
            x1 = ocr_item.bbox[0] * self._bbox_scale
            y1 = ocr_item.bbox[1] * self._bbox_scale
            x2 = ocr_item.bbox[2] * self._bbox_scale
            y2 = ocr_item.bbox[3] * self._bbox_scale
            bbox_rect = QRectF(x1, y1, x2 - x1, y2 - y1)

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
            x1 = ocr_item.bbox[0] * self._bbox_scale
            y1 = ocr_item.bbox[1] * self._bbox_scale
            x2 = ocr_item.bbox[2] * self._bbox_scale
            y2 = ocr_item.bbox[3] * self._bbox_scale
            bbox_rect = QRectF(x1, y1, x2 - x1, y2 - y1)
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

        # Stage 1: scale to display size (so we can free the full-res original ASAP).
        if max(qimg.width(), qimg.height()) > DISPLAY_LONG_SIDE:
            display_qimg = qimg.scaled(
                DISPLAY_LONG_SIDE,
                DISPLAY_LONG_SIDE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            display_qimg = qimg
        # Drop the reference to the (potentially full-res) original.
        del qimg

        # Stage 2: scale down further for OCR, if needed.
        if max(display_qimg.width(), display_qimg.height()) > self._effective_long_side:
            ocr_qimg = display_qimg.scaled(
                self._effective_long_side,
                self._effective_long_side,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            ocr_qimg = display_qimg

        arr = array_from_qimage(ocr_qimg)
        # ocr_qimg goes out of scope after the array copy.

        pixmap = QPixmap.fromImage(display_qimg)

        if self._pixmap_item:
            self._scene.removeItem(self._pixmap_item)
        self.clear_results()

        pixmap_item = self._scene.addPixmap(pixmap)
        assert pixmap_item is not None
        pixmap_item.setZValue(0)
        self._pixmap_item = pixmap_item
        self.setSceneRect(QRectF(pixmap.rect().toRectF()))
        self._fit_to_view = True
        self.fitInView(pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

        self.image_loaded.emit(arr, pixmap)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        if self._pixmap_item is not None and self._fit_to_view:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    # ── Input events ────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent | None) -> None:  # type: ignore[override]
        if (
            self._crop_mode
            and event is not None
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._crop_origin = self.mapToScene(event.pos())
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:  # type: ignore[override]
        if self._crop_mode and self._crop_origin is not None and event is not None:
            self._update_crop_rect(self._crop_origin, self.mapToScene(event.pos()))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:  # type: ignore[override]
        if self._crop_mode and self._crop_origin is not None and event is not None:
            origin = self._crop_origin
            self._crop_origin = None
            self._finish_crop(origin, self.mapToScene(event.pos()))
            return
        super().mouseReleaseEvent(event)

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
