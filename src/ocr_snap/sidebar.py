from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QContextMenuEvent, QEnterEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ocr_snap.canvas import _add_merge_permutation_actions
from ocr_snap.models import OCRResults, SelectionModel, item_color
from ocr_snap.pill import Pill, TogglePill
from ocr_snap.theme import Icons, IconButton, StatusChip, Tokens

_ENTRY_STYLE = f"""
SidebarEntry {{{{
    background-color: {{bg}};
    border-radius: {Tokens.r_md}px;
    border: 3px solid {{border}};
}}}}
"""
_BG_NORMAL = Tokens.bg_surface
_BG_HOVER = Tokens.bg_raised

_SEPARATOR_STYLE = f"background: {Tokens.border}; border: none; max-height: 1px;"


class _TextZone(QWidget):
    """A hover zone containing content labels and copy/edit buttons that
    appear on hover. Edit button is created when ``edit_callback`` is given."""

    def __init__(
        self,
        copy_callback: Callable[[], None],
        edit_callback: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setMouseTracking(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._content_layout = QVBoxLayout()
        self._content_layout.setSpacing(2)
        layout.addLayout(self._content_layout, stretch=1)

        self._edit_btn: IconButton | None = None
        if edit_callback is not None:
            self._edit_btn = IconButton(Icons.pencil(), tooltip="Edit", size=14)
            self._edit_btn.clicked.connect(edit_callback)
            self._edit_btn.hide()
            layout.addWidget(self._edit_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._copy_btn = IconButton(Icons.copy(), tooltip="Copy", size=14)
        self._copy_btn.clicked.connect(copy_callback)
        self._copy_btn.hide()
        layout.addWidget(self._copy_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

    def add_widget(self, widget: QWidget) -> None:
        self._content_layout.addWidget(widget)

    def enterEvent(self, event):  # type: ignore[override, no-untyped-def]
        if self._edit_btn is not None:
            self._edit_btn.show()
        self._copy_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):  # type: ignore[override, no-untyped-def]
        if self._edit_btn is not None:
            self._edit_btn.hide()
        self._copy_btn.hide()
        super().leaveEvent(event)


class SidebarEntry(QFrame):
    text_edited = pyqtSignal(int, str)

    def __init__(
        self,
        index: int,
        text: str,
        confidence: float,
        color: QColor,
        selection_model: SelectionModel,
        scroll_area: QScrollArea,
        on_merge: Callable[[list[int]], None] | None = None,
        on_delete: Callable[[], None] | None = None,
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
        self._on_delete = on_delete

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Index badge + confidence column
        badge_layout = QVBoxLayout()
        badge_layout.setSpacing(2)

        idx_label = QLabel(f"{index + 1}")
        idx_label.setFixedSize(28, 28)
        idx_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        idx_label.setStyleSheet(
            f"background: {Tokens.bg_raised}; border-radius: 14px; "
            f"color: {Tokens.text_muted}; font-weight: bold; font-size: {Tokens.text_base}px;"
        )
        badge_layout.addWidget(idx_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        conf_label = QLabel(f"{confidence:.0%}")
        conf_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        conf_label.setStyleSheet(
            f"color: {Tokens.text_muted}; font-size: {Tokens.text_eyebrow}px; "
            f"background: transparent; border: none;"
        )
        badge_layout.addWidget(conf_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addLayout(badge_layout)

        # Vertical stack: original zone, separator, translation zone
        zones_layout = QVBoxLayout()
        zones_layout.setSpacing(4)

        # Original text zone
        self._original_zone = _TextZone(self._copy_original, self._begin_edit)

        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setStyleSheet(
            f"color: {Tokens.text_primary}; font-size: {Tokens.text_lg}px; "
            f"background: transparent; border: none; min-height: 25px;"
        )
        self._original_zone.add_widget(text_label)
        self._text_label = text_label
        self._editor: QTextEdit | None = None

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
            f"color: {Tokens.translation}; font-size: {Tokens.text_lg}px; "
            f"background: transparent; border: none; min-height: 25px;"
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

    def _begin_edit(self) -> None:
        if self._editor is not None:
            return
        editor = QTextEdit(self._text)
        editor.setStyleSheet(
            f"QTextEdit {{ color: {Tokens.text_primary}; "
            f"font-size: {Tokens.text_lg}px; "
            f"background: {Tokens.bg_deepest}; "
            f"border: 1px solid #d4a843; border-radius: 4px; "
            f"padding: 2px 6px; }}"
        )
        editor.setAcceptRichText(False)
        editor.setTabChangesFocus(True)
        editor.installEventFilter(self)
        editor.document().contentsChanged.connect(
            lambda: self._resize_editor_to_content(editor)
        )
        self._editor = editor
        self._text_label.hide()
        self._original_zone.add_widget(editor)
        editor.setFocus()
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        self._resize_editor_to_content(editor)

    def _resize_editor_to_content(self, editor: QTextEdit) -> None:
        doc_h = int(editor.document().size().height())
        editor.setFixedHeight(max(28, doc_h + 8))

    def eventFilter(self, obj, event):  # type: ignore[override, no-untyped-def]
        if obj is self._editor and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if key == Qt.Key.Key_Escape:
                self._cancel_edit()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    return False  # let the editor insert a newline
                self._commit_edit()
                return True
        if obj is self._editor and event.type() == QEvent.Type.FocusOut:
            if self._editor is not None:
                self._commit_edit()
            return False  # don't consume; allow normal focus-out processing
        return super().eventFilter(obj, event)

    def _commit_edit(self) -> None:
        if self._editor is None:
            return
        new_text = self._editor.toPlainText().strip()
        editor = self._editor
        self._editor = None
        editor.setParent(None)
        editor.deleteLater()
        self._text_label.show()
        if not new_text or new_text == self._text:
            return
        self._text = new_text
        self._text_label.setText(new_text)
        self.text_edited.emit(self._index, new_text)

    def _cancel_edit(self) -> None:
        if self._editor is None:
            return
        editor = self._editor
        self._editor = None
        editor.setParent(None)
        editor.deleteLater()
        self._text_label.show()

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
        # Auto-select this entry if it's not already selected
        if not self._selection_model.is_selected(self._index):
            self._selection_model.select(self._index)
        sel = self._selection_model.selected_indices
        if len(sel) < 1:
            super().contextMenuEvent(event)
            return
        menu = QMenu(self)
        if self._on_delete is not None:
            if len(sel) == 1:
                menu.addAction("Delete", self._on_delete)
            else:
                menu.addAction(f"Delete selected ({len(sel)})", self._on_delete)
        if len(sel) >= 2 and self._on_merge is not None:
            _add_merge_permutation_actions(menu, sorted(sel), self._on_merge)
        menu.exec(event.globalPos())


class OCRSidebar(QWidget):
    merge_requested = pyqtSignal(list)
    delete_requested = pyqtSignal()
    confidence_filter_changed = pyqtSignal(float)
    reocr_requested = pyqtSignal(float)
    overlay_toggled = pyqtSignal(bool)
    copy_image_requested = pyqtSignal()

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
            f"font-size: {Tokens.text_lg}px; font-weight: bold; "
            f"color: {Tokens.text_muted}; padding: {Tokens.sp_3}px {Tokens.sp_1}px "
            f"{Tokens.sp_2}px {Tokens.sp_4}px; border: none;"
        )
        header_layout.addWidget(header)

        self._translating_label = StatusChip("Translating…", state="translation")
        self._translating_label.hide()
        header_layout.addWidget(self._translating_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # ── Controls card ───────────────────────────────────────────────
        controls_card = QFrame()
        controls_card.setStyleSheet(
            f"QFrame {{ background: {Tokens.bg_surface}; "
            f"border: 1px solid {Tokens.border}; "
            f"border-radius: {Tokens.r_md}px; }}"
        )
        controls_card_layout = QVBoxLayout(controls_card)
        controls_card_layout.setContentsMargins(12, 10, 12, 10)
        controls_card_layout.setSpacing(8)

        slider_row = QHBoxLayout()
        slider_row.setContentsMargins(0, 0, 0, 0)
        slider_row.setSpacing(8)

        slider_label = QLabel("Min confidence")
        slider_label.setStyleSheet(
            f"color: {Tokens.text_muted}; font-size: {Tokens.text_base}px; "
            f"background: transparent; border: none;"
        )
        slider_row.addWidget(slider_label)

        self._confidence_slider = QSlider(Qt.Orientation.Horizontal)
        self._confidence_slider.setRange(0, 100)
        self._confidence_slider.setValue(50)
        self._confidence_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{"
            f"  background: {Tokens.border}; height: 4px; border-radius: 2px;"
            f"}}"
            f"QSlider::handle:horizontal {{"
            f"  background: {Tokens.text_muted}; width: 12px; height: 12px; margin: -4px 0;"
            f"  border-radius: 6px;"
            f"}}"
            f"QSlider::handle:horizontal:hover {{"
            f"  background: {Tokens.accent};"
            f"}}"
        )
        slider_row.addWidget(self._confidence_slider, stretch=1)

        self._confidence_value_label = QLabel("50%")
        self._confidence_value_label.setFixedWidth(36)
        self._confidence_value_label.setStyleSheet(
            f"color: {Tokens.text_primary}; font-size: {Tokens.text_base}px; "
            f"background: transparent; border: none;"
        )
        slider_row.addWidget(self._confidence_value_label)

        controls_card_layout.addLayout(slider_row)

        pills_row = QHBoxLayout()
        pills_row.setContentsMargins(0, 0, 0, 0)
        pills_row.setSpacing(6)

        self._overlay_pill = TogglePill(Icons.eye, "Overlay")
        self._overlay_pill.toggled.connect(self.overlay_toggled.emit)
        pills_row.addWidget(self._overlay_pill)

        self._copy_image_pill = Pill(Icons.image, "Copy image")
        self._copy_image_pill.clicked.connect(self.copy_image_requested.emit)
        pills_row.addWidget(self._copy_image_pill)

        pills_row.addStretch()
        controls_card_layout.addLayout(pills_row)

        card_wrapper_layout = QHBoxLayout()
        card_wrapper_layout.setContentsMargins(14, 0, 14, 8)
        card_wrapper_layout.addWidget(controls_card)
        layout.addLayout(card_wrapper_layout)

        self._confidence_slider.valueChanged.connect(self._on_slider_value_changed)
        self._confidence_slider.sliderReleased.connect(self._on_slider_released)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll_area.setStyleSheet(
            f"QScrollArea {{ border: none; background: transparent; }}"
            f"QScrollBar:vertical {{"
            f"  background: {Tokens.bg_surface}; width: 6px; border-radius: 3px;"
            f"}}"
            f"QScrollBar::handle:vertical {{"
            f"  background: {Tokens.border_strong}; border-radius: 3px; min-height: 30px;"
            f"}}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        layout.addWidget(self._scroll_area)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(8, 4, 8, 8)
        self._container_layout.setSpacing(4)

        self._no_results_label = QLabel("No results found")
        self._no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_results_label.setStyleSheet(
            f"color: {Tokens.text_muted}; font-size: {Tokens.text_base}px; "
            f"font-style: italic; background: transparent; border: none; "
            f"padding: {Tokens.sp_5}px 0;"
        )
        self._no_results_label.hide()
        self._container_layout.addWidget(self._no_results_label)

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
        self._container_layout.addWidget(self._no_results_label)
        self._no_results_label.show()
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

        # Remove the stretch and no-results label
        while self._container_layout.count():
            self._container_layout.takeAt(0)

        if results.items:
            self._no_results_label.hide()
        else:
            self._container_layout.addWidget(self._no_results_label)
            self._no_results_label.show()

        for ocr_item in results.items:
            color = item_color(ocr_item.index)
            entry = SidebarEntry(
                ocr_item.index,
                ocr_item.text,
                ocr_item.confidence,
                color,
                selection_model,
                self._scroll_area,
                on_merge=lambda order: self.merge_requested.emit(order),
                on_delete=self.delete_requested.emit,
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

    def set_overlay_checked(self, checked: bool) -> None:
        self._overlay_pill.blockSignals(True)
        self._overlay_pill.setChecked(checked)
        self._overlay_pill.blockSignals(False)

    def set_active_state(self, has_image: bool, has_results: bool) -> None:
        """Gate the action pills. Copy image needs an active image; Overlay
        needs OCR results to be meaningful."""
        self._copy_image_pill.setEnabled(has_image)
        self._overlay_pill.setEnabled(has_image and has_results)

    def _on_slider_released(self) -> None:
        value = self._confidence_slider.value() / 100.0
        if value < self._ocr_threshold:
            self.reocr_requested.emit(value)
