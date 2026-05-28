from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QGraphicsView

from ocr_snap.canvas import OCRCanvas
from ocr_snap.models import OCRResultItem, OCRResults, SelectionModel


def _white_pixmap(w: int, h: int) -> QPixmap:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(Qt.GlobalColor.white)
    return QPixmap.fromImage(img)


def _canvas(qapp) -> OCRCanvas:
    canvas = OCRCanvas()
    canvas.resize(400, 300)
    canvas.show()
    qapp.processEvents()
    canvas.set_working_pixmap(_white_pixmap(800, 600))
    qapp.processEvents()
    return canvas


def test_set_working_pixmap_updates_scene_rect(qapp) -> None:
    canvas = _canvas(qapp)
    canvas.set_working_pixmap(_white_pixmap(640, 480))
    qapp.processEvents()
    assert canvas.sceneRect().width() == 640
    assert canvas.sceneRect().height() == 480
    canvas.close()


def test_set_working_pixmap_does_not_emit_image_loaded(qapp) -> None:
    canvas = _canvas(qapp)
    emitted: list[bool] = []
    canvas.image_loaded.connect(lambda _arr, _px: emitted.append(True))
    canvas.set_working_pixmap(_white_pixmap(320, 240))
    qapp.processEvents()
    assert emitted == []
    canvas.close()


def test_set_working_pixmap_preserves_user_zoom(qapp) -> None:
    canvas = _canvas(qapp)
    canvas._apply_zoom(4.0)  # zoom in -> _fit_to_view becomes False
    assert canvas._fit_to_view is False
    scaled = canvas._current_scale()
    canvas.set_working_pixmap(_white_pixmap(640, 480))
    qapp.processEvents()
    # A zoomed-in user keeps their zoom; no refit on preview swap.
    assert canvas._fit_to_view is False
    assert canvas._current_scale() == scaled
    canvas.close()


def test_clear_results_removes_items(qapp) -> None:
    canvas = _canvas(qapp)
    sel = SelectionModel()
    results = OCRResults(
        items=[
            OCRResultItem(
                index=0,
                text="hi",
                confidence=0.9,
                polygon=np.array([[0, 0], [10, 0], [10, 10], [0, 10]]),
                bbox=(0.0, 0.0, 10.0, 10.0),
            )
        ],
        image_width=800,
        image_height=600,
    )
    canvas.set_ocr_results(results, sel, visible=True)
    assert len(canvas._ocr_items) == 1
    canvas.clear_results()
    assert canvas._ocr_items == []
    assert canvas._overlay_items == []
    canvas.close()


def test_set_crop_mode_toggles_drag_mode(qapp) -> None:
    canvas = _canvas(qapp)
    canvas.set_crop_mode(True)
    assert canvas.dragMode() == QGraphicsView.DragMode.NoDrag
    canvas.set_crop_mode(False)
    assert canvas.dragMode() == QGraphicsView.DragMode.ScrollHandDrag
    canvas.close()


def test_finish_crop_emits_normalized_rect(qapp) -> None:
    canvas = _canvas(qapp)  # 800x600 working pixmap
    emitted: list[QRectF] = []
    canvas.crop_selected.connect(emitted.append)
    canvas.set_crop_mode(True)
    canvas._finish_crop(QPointF(100.0, 150.0), QPointF(500.0, 450.0))
    assert len(emitted) == 1
    rect = emitted[0]
    assert abs(rect.x() - 0.125) < 1e-6      # 100/800
    assert abs(rect.y() - 0.25) < 1e-6       # 150/600
    assert abs(rect.width() - 0.5) < 1e-6    # 400/800
    assert abs(rect.height() - 0.5) < 1e-6   # 300/600
    # crop mode auto-exits after a finished selection
    assert canvas.dragMode() == QGraphicsView.DragMode.ScrollHandDrag
    canvas.close()


def test_finish_crop_ignores_tiny_selection(qapp) -> None:
    canvas = _canvas(qapp)
    emitted: list[QRectF] = []
    canvas.crop_selected.connect(emitted.append)
    canvas.set_crop_mode(True)
    canvas._finish_crop(QPointF(100.0, 100.0), QPointF(101.0, 101.0))
    assert emitted == []
    canvas.close()


def test_set_crop_mode_emits_crop_mode_changed(qapp) -> None:
    canvas = _canvas(qapp)
    seen: list[bool] = []
    canvas.crop_mode_changed.connect(seen.append)
    canvas.set_crop_mode(True)
    canvas.set_crop_mode(False)
    assert seen == [True, False]
    canvas.close()


def test_tiny_crop_signals_crop_mode_exit(qapp) -> None:
    # A cancelled/too-small selection exits crop mode without crop_selected,
    # but must still signal crop_mode_changed(False) so the panel button syncs.
    canvas = _canvas(qapp)
    seen: list[bool] = []
    canvas.crop_mode_changed.connect(seen.append)
    canvas.set_crop_mode(True)
    canvas._finish_crop(QPointF(10.0, 10.0), QPointF(11.0, 11.0))
    assert seen[-1] is False
    canvas.close()
