from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from ocr_snap.models import ImageState, OCRResultItem, OCRResults


def _make_state(items: list[OCRResultItem]) -> ImageState:
    from PyQt6.QtGui import QPixmap
    pm = QPixmap(10, 10)
    pm.fill()
    state = ImageState("img", pm, None)
    state.ocr_results = OCRResults(items=items, image_width=10, image_height=10)
    return state


def test_start_translation_only_missing_filters_translated_items(qapp) -> None:
    from ocr_snap.main_window import MainWindow

    items = [
        OCRResultItem(
            index=0, text="a", confidence=0.9,
            polygon=np.zeros((4, 2)), bbox=(0, 0, 1, 1),
            translated_text="A",  # already translated
        ),
        OCRResultItem(
            index=1, text="b", confidence=0.9,
            polygon=np.zeros((4, 2)), bbox=(0, 0, 1, 1),
            translated_text=None,  # missing
        ),
    ]
    state = _make_state(items)
    mw = MainWindow.__new__(MainWindow)
    mw._images = {"img": state}
    mw._active_id = "img"
    mw._translator = MagicMock()
    mw._translator.translate.return_value = True
    mw._sidebar = MagicMock()

    mw._start_translation("img", only_missing=True)

    mw._translator.translate.assert_called_once()
    submitted = mw._translator.translate.call_args.args[1]
    assert submitted == [(1, "b")]  # only the missing one


def test_start_translation_default_submits_all(qapp) -> None:
    from ocr_snap.main_window import MainWindow

    items = [
        OCRResultItem(
            index=0, text="a", confidence=0.9,
            polygon=np.zeros((4, 2)), bbox=(0, 0, 1, 1),
            translated_text="A",
        ),
        OCRResultItem(
            index=1, text="b", confidence=0.9,
            polygon=np.zeros((4, 2)), bbox=(0, 0, 1, 1),
            translated_text=None,
        ),
    ]
    state = _make_state(items)
    mw = MainWindow.__new__(MainWindow)
    mw._images = {"img": state}
    mw._active_id = "img"
    mw._translator = MagicMock()
    mw._translator.translate.return_value = True
    mw._sidebar = MagicMock()

    mw._start_translation("img")  # default only_missing=False

    submitted = mw._translator.translate.call_args.args[1]
    assert submitted == [(0, "a"), (1, "b")]
