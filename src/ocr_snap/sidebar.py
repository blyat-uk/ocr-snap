from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtSignal
from PyQt6.QtGui import QContextMenuEvent, QEnterEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from PyQt6.QtGui import QColor

from ocr_snap.models import OCRResults, SelectionModel, item_color

_ENTRY_STYLE = """
SidebarEntry {{
    background-color: {bg};
    border-radius: 6px;
    border: 3px solid {border};
}}
"""
_BG_NORMAL = "rgba(255, 255, 255, 6)"
_BG_HOVER = "rgba(255, 255, 255, 14)"

_COPY_BTN_STYLE = """
QPushButton {
    background: rgba(255, 255, 255, 10);
    border: 1px solid rgba(255, 255, 255, 15);
    border-radius: 4px;
    color: #aaa;
    padding: 2px 8px;
    font-size: 11px;
}
QPushButton:hover {
    background: rgba(255, 255, 255, 20);
    color: #ddd;
}
QPushButton:pressed {
    background: rgba(255, 255, 255, 30);
}
"""

_SEPARATOR_STYLE = "background: rgba(255, 255, 255, 15); border: none; max-height: 1px;"


class _TextZone(QWidget):
    """A hover zone containing content labels and a copy button that appears on hover."""

    def __init__(
        self, copy_callback: Callable[[], None], parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setMouseTracking(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._content_layout = QVBoxLayout()
        self._content_layout.setSpacing(2)
        layout.addLayout(self._content_layout, stretch=1)

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.setFixedSize(50, 22)
        self._copy_btn.setStyleSheet(_COPY_BTN_STYLE)
        self._copy_btn.clicked.connect(copy_callback)
        self._copy_btn.hide()
        layout.addWidget(self._copy_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

    def add_widget(self, widget: QWidget) -> None:
        self._content_layout.addWidget(widget)

    def enterEvent(self, event: QEnterEvent | None) -> None:
        self._copy_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event: QEnterEvent | None) -> None:  # type: ignore[override]
        self._copy_btn.hide()
        super().leaveEvent(event)


class SidebarEntry(QFrame):
    def __init__(
        self,
        index: int,
        text: str,
        confidence: float,
        color: QColor,
        selection_model: SelectionModel,
        scroll_area: QScrollArea,
        on_merge: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._index = index
        self._text = text
        self._confidence = confidence
        self._translated_text: str | None = None
        self._color = color
        self._selection_model = selection_model
        self._scroll_area = scroll_area
        self._on_merge = on_merge

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Index badge + confidence column
        badge_layout = QVBoxLayout()
        badge_layout.setSpacing(2)

        idx_label = QLabel(f"{index + 1}")
        idx_label.setFixedSize(24, 24)
        idx_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        idx_label.setStyleSheet(
            "background: rgba(255,255,255,10); border-radius: 12px;color: #888; font-weight: bold; font-size: 10px;"
        )
        badge_layout.addWidget(idx_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        conf_label = QLabel(f"{confidence:.0%}")
        conf_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        conf_label.setStyleSheet(
            "color: #777; font-size: 9px; background: transparent; border: none;"
        )
        badge_layout.addWidget(conf_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addLayout(badge_layout)

        # Vertical stack: original zone, separator, translation zone
        zones_layout = QVBoxLayout()
        zones_layout.setSpacing(4)

        # Original text zone
        self._original_zone = _TextZone(self._copy_original)

        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setStyleSheet(
            "color: #ddd; font-size: 13px; background: transparent; border: none; min-height: 25px;"
        )
        self._original_zone.add_widget(text_label)

        zones_layout.addWidget(self._original_zone)

        # Separator (hidden until translation arrives)
        self._separator = QFrame()
        self._separator.setFrameShape(QFrame.Shape.HLine)
        self._separator.setStyleSheet(_SEPARATOR_STYLE)
        self._separator.hide()
        zones_layout.addWidget(self._separator)

        # Translation zone (hidden until translation arrives)
        self._translation_zone = _TextZone(self._copy_translation)

        self._translation_label = QLabel()
        self._translation_label.setWordWrap(True)
        self._translation_label.setStyleSheet(
            "color: #7ab8e0; font-size: 12px; background: transparent; border: none; min-height: 25px;"
        )
        self._translation_zone.add_widget(self._translation_label)
        self._translation_zone.hide()
        zones_layout.addWidget(self._translation_zone)

        layout.addLayout(zones_layout, stretch=1)

        self._apply_style()
        selection_model.hovered_changed.connect(self._on_hover_changed)
        selection_model.selection_changed.connect(self._on_selection_changed)

    def set_translation(self, text: str) -> None:
        self._translated_text = text
        self._translation_label.setText(text)
        self._separator.show()
        self._translation_zone.show()

    def _copy_original(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._text)

    def _copy_translation(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None and self._translated_text:
            clipboard.setText(self._translated_text)

    def _apply_style(self) -> None:
        hovered = self._selection_model.hovered_index == self._index
        selected = self._selection_model.is_selected(self._index)
        r, g, b, _ = self._color.getRgb()

        if selected:
            bg = _BG_HOVER
            border = f"rgb({r}, {g}, {b})"
        elif hovered:
            bg = _BG_HOVER
            border = f"rgba({r}, {g}, {b}, 0.4)"
        else:
            bg = _BG_NORMAL
            border = "transparent"
        self.setStyleSheet(_ENTRY_STYLE.format(bg=bg, border=border))

    def _on_hover_changed(self, _index: int) -> None:
        self._apply_style()

    def _on_selection_changed(self) -> None:
        self._apply_style()
        # Scroll-to-visible only when this is the sole selected item
        sel = self._selection_model.selected_indices
        if sel == frozenset({self._index}):
            self._scroll_area.ensureWidgetVisible(self)

    def enterEvent(self, event: QEnterEvent | None) -> None:
        self._selection_model.hovered_index = self._index
        super().enterEvent(event)

    def leaveEvent(self, event: QEnterEvent | None) -> None:  # type: ignore[override]
        if self._selection_model.hovered_index == self._index:
            self._selection_model.hovered_index = -1
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._selection_model.toggle(self._index)
            else:
                self._selection_model.select(self._index)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent | None) -> None:
        if event is None:
            super().contextMenuEvent(event)  # type: ignore[arg-type]
            return
        sel = self._selection_model.selected_indices
        if len(sel) < 2 or self._on_merge is None:
            super().contextMenuEvent(event)
            return
        menu = QMenu(self)
        menu.addAction(f"Merge selected ({len(sel)})", self._on_merge)
        menu.exec(event.globalPos())


class OCRSidebar(QWidget):
    merge_requested = pyqtSignal()
    confidence_filter_changed = pyqtSignal(float)
    reocr_requested = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._entries: list[SidebarEntry] = []
        self._selection_model: SelectionModel | None = None
        self._ocr_threshold: float = 0.5

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        header = QLabel("OCR Results")
        header.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #999;padding: 12px 14px 8px 14px; border: none;"
        )
        header_layout.addWidget(header)

        self._translating_label = QLabel("Translating...")
        self._translating_label.setStyleSheet(
            "font-size: 11px; font-style: italic; color: #7ab8e0;padding: 12px 14px 8px 0; border: none;"
        )
        self._translating_label.hide()
        header_layout.addWidget(self._translating_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Confidence threshold slider
        slider_layout = QHBoxLayout()
        slider_layout.setContentsMargins(14, 0, 14, 6)
        slider_layout.setSpacing(8)

        slider_label = QLabel("Min confidence")
        slider_label.setStyleSheet(
            "color: #777; font-size: 11px; background: transparent; border: none;"
        )
        slider_layout.addWidget(slider_label)

        self._confidence_slider = QSlider(Qt.Orientation.Horizontal)
        self._confidence_slider.setRange(0, 100)
        self._confidence_slider.setValue(50)
        self._confidence_slider.setStyleSheet(
            "QSlider::groove:horizontal {"
            "  background: rgba(255,255,255,10); height: 4px; border-radius: 2px;"
            "}"
            "QSlider::handle:horizontal {"
            "  background: #888; width: 12px; height: 12px; margin: -4px 0;"
            "  border-radius: 6px;"
            "}"
            "QSlider::handle:horizontal:hover {"
            "  background: #aaa;"
            "}"
        )
        slider_layout.addWidget(self._confidence_slider, stretch=1)

        self._confidence_value_label = QLabel("50%")
        self._confidence_value_label.setFixedWidth(32)
        self._confidence_value_label.setStyleSheet(
            "color: #999; font-size: 11px; background: transparent; border: none;"
        )
        slider_layout.addWidget(self._confidence_value_label)

        layout.addLayout(slider_layout)

        self._confidence_slider.valueChanged.connect(self._on_slider_value_changed)
        self._confidence_slider.sliderReleased.connect(self._on_slider_released)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll_area.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical {"
            "  background: rgba(255,255,255,5); width: 6px; border-radius: 3px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: rgba(255,255,255,20); border-radius: 3px; min-height: 30px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        layout.addWidget(self._scroll_area)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(8, 4, 8, 8)
        self._container_layout.setSpacing(4)
        self._container_layout.addStretch()
        self._scroll_area.setWidget(self._container)

    def clear(self) -> None:
        for entry in self._entries:
            self._container_layout.removeWidget(entry)
            entry.deleteLater()
        self._entries.clear()
        self._selection_model = None
        while self._container_layout.count():
            self._container_layout.takeAt(0)
        self._container_layout.addStretch()
        self._translating_label.hide()

    def set_results(
        self,
        results: OCRResults,
        selection_model: SelectionModel,
        *,
        visible: bool = False,
    ) -> None:
        # Clear old entries
        for entry in self._entries:
            self._container_layout.removeWidget(entry)
            entry.deleteLater()
        self._entries.clear()
        self._selection_model = selection_model

        # Remove the stretch
        while self._container_layout.count():
            self._container_layout.takeAt(0)

        for ocr_item in results.items:
            color = item_color(ocr_item.index)
            entry = SidebarEntry(
                ocr_item.index,
                ocr_item.text,
                ocr_item.confidence,
                color,
                selection_model,
                self._scroll_area,
                on_merge=self.merge_requested.emit,
            )
            if not visible:
                entry.hide()
            self._container_layout.addWidget(entry)
            self._entries.append(entry)

        self._container_layout.addStretch()

    def set_translating(self, active: bool) -> None:
        self._translating_label.setVisible(active)

    def update_translations(self, translations: dict[int, str]) -> None:
        for index, text in translations.items():
            if 0 <= index < len(self._entries):
                self._entries[index].set_translation(text)

    def reveal_entry(self, index: int) -> None:
        if 0 <= index < len(self._entries):
            entry = self._entries[index]
            entry.show()

            effect = QGraphicsOpacityEffect(entry)
            effect.setOpacity(0.0)
            entry.setGraphicsEffect(effect)

            anim = QPropertyAnimation(effect, b"opacity", entry)
            anim.setDuration(250)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda: entry.setGraphicsEffect(None))
            anim.start()

    def set_ocr_threshold(self, value: float) -> None:
        self._ocr_threshold = value

    def set_confidence_filter(self, value: int) -> None:
        self._confidence_slider.blockSignals(True)
        self._confidence_slider.setValue(value)
        self._confidence_value_label.setText(f"{value}%")
        self._confidence_slider.blockSignals(False)

    def filter_by_confidence(self, threshold: float) -> None:
        for entry in self._entries:
            if entry._confidence >= threshold:
                entry.show()
            else:
                entry.hide()

    def _on_slider_value_changed(self, value: int) -> None:
        self._confidence_value_label.setText(f"{value}%")
        self.confidence_filter_changed.emit(value / 100.0)

    def _on_slider_released(self) -> None:
        value = self._confidence_slider.value() / 100.0
        if value < self._ocr_threshold:
            self.reocr_requested.emit(value)
