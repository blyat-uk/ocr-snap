from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QEnterEvent, QMouseEvent, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_THUMB_WIDTH = 74
_PANEL_WIDTH = 90
_THUMB_MAX_HEIGHT = 100

_THUMB_STYLE = """
GalleryThumbnail {{
    background: #252525;
    border: 2px solid {border};
    border-radius: 4px;
}}
"""

_CLOSE_BTN_STYLE = """
QPushButton {
    background: rgba(0, 0, 0, 160);
    color: #ccc;
    border: none;
    border-radius: 8px;
    font-size: 11px;
    font-weight: bold;
    padding: 0;
}
QPushButton:hover {
    background: rgba(200, 50, 50, 200);
    color: #fff;
}
"""

_PANEL_STYLE = """
GalleryPanel {
    background: #1a1a1a;
    border-right: 1px solid #2a2a2a;
}
"""

_PROCESSING_STYLE = """
GalleryThumbnail {{
    background: #252525;
    border: 2px solid rgba(255, 190, 50, 0.6);
    border-radius: 4px;
}}
"""


class GalleryThumbnail(QFrame):
    clicked = pyqtSignal(str)
    close_clicked = pyqtSignal(str)

    def __init__(
        self, image_id: str, pixmap: QPixmap, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._image_id = image_id
        self._active = False
        self._processing = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(_THUMB_WIDTH)

        # Scale pixmap to thumbnail size
        scaled = pixmap.scaledToWidth(
            _THUMB_WIDTH - 4, Qt.TransformationMode.SmoothTransformation
        )
        if scaled.height() > _THUMB_MAX_HEIGHT:
            scaled = scaled.scaledToHeight(
                _THUMB_MAX_HEIGHT, Qt.TransformationMode.SmoothTransformation
            )
        self.setFixedHeight(scaled.height() + 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self._label = QLabel()
        self._label.setPixmap(scaled)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self._label)

        # Close button (top-right, hidden by default)
        self._close_btn = QPushButton("\u00d7")
        self._close_btn.setFixedSize(16, 16)
        self._close_btn.setStyleSheet(_CLOSE_BTN_STYLE)
        self._close_btn.setParent(self)
        self._close_btn.move(self.width() - 18, 2)
        self._close_btn.hide()
        self._close_btn.clicked.connect(lambda: self.close_clicked.emit(self._image_id))

        self._apply_style()

    @property
    def image_id(self) -> str:
        return self._image_id

    def set_active(self, active: bool) -> None:
        self._active = active
        self._apply_style()

    def set_processing(self, processing: bool) -> None:
        self._processing = processing
        self._apply_style()

    def _apply_style(self) -> None:
        if self._processing and not self._active:
            self.setStyleSheet(_PROCESSING_STYLE.format())
        elif self._active:
            self.setStyleSheet(_THUMB_STYLE.format(border="rgba(255, 190, 50, 0.8)"))
        else:
            self.setStyleSheet(_THUMB_STYLE.format(border="transparent"))

    def enterEvent(self, event: QEnterEvent | None) -> None:
        self._close_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event: QEnterEvent | None) -> None:  # type: ignore[override]
        self._close_btn.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._image_id)
        super().mousePressEvent(event)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._close_btn.move(self.width() - 18, 2)


class GalleryPanel(QWidget):
    image_selected = pyqtSignal(str)
    image_removed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(_PANEL_WIDTH)
        self.setStyleSheet(_PANEL_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll_area.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical {"
            "  background: rgba(255,255,255,5); width: 5px; border-radius: 2px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: rgba(255,255,255,20); border-radius: 2px; min-height: 20px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        layout.addWidget(self._scroll_area)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(8, 8, 8, 8)
        self._container_layout.setSpacing(6)
        self._container_layout.addStretch()
        self._scroll_area.setWidget(self._container)

        self._thumbnails: dict[str, GalleryThumbnail] = {}

    def add_image(self, image_id: str, pixmap: QPixmap) -> None:
        thumb = GalleryThumbnail(image_id, pixmap)
        thumb.clicked.connect(self.image_selected.emit)
        thumb.close_clicked.connect(self.image_removed.emit)

        # Insert before the stretch
        count = self._container_layout.count()
        self._container_layout.insertWidget(count - 1, thumb)
        self._thumbnails[image_id] = thumb

    def remove_image(self, image_id: str) -> None:
        thumb = self._thumbnails.pop(image_id, None)
        if thumb is not None:
            self._container_layout.removeWidget(thumb)
            thumb.deleteLater()

    def set_active(self, image_id: str) -> None:
        for tid, thumb in self._thumbnails.items():
            thumb.set_active(tid == image_id)

    def set_processing(self, image_id: str, active: bool) -> None:
        thumb = self._thumbnails.get(image_id)
        if thumb is not None:
            thumb.set_processing(active)

    @property
    def count(self) -> int:
        return len(self._thumbnails)
