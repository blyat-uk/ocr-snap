from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QScrollArea, QTextEdit

from ocr_snap.models import SelectionModel
from ocr_snap.sidebar import SidebarEntry


def _make_entry(qapp, text: str = "hello world", confidence: float = 0.99) -> SidebarEntry:
    sel = SelectionModel()
    scroll = QScrollArea()
    return SidebarEntry(
        index=0,
        text=text,
        confidence=confidence,
        color=QColor(255, 0, 0),
        selection_model=sel,
        scroll_area=scroll,
    )


def test_pencil_button_exists_and_starts_hidden(qapp) -> None:
    entry = _make_entry(qapp)
    edit_btn = entry._original_zone._edit_btn
    assert edit_btn is not None
    # ``hide()`` was called in _TextZone.__init__; isHidden() returns True
    # regardless of whether the parent entry is shown.
    assert edit_btn.isHidden() is True


def test_clicking_pencil_swaps_label_for_editor(qapp) -> None:
    entry = _make_entry(qapp, "hello")
    entry._begin_edit()
    assert isinstance(entry._editor, QTextEdit)
    assert entry._editor.toPlainText() == "hello"
    assert entry._text_label.isHidden() is True


def test_commit_emits_text_edited_when_changed(qapp) -> None:
    entry = _make_entry(qapp, "hello")
    fired: list[tuple[int, str]] = []
    entry.text_edited.connect(lambda i, t: fired.append((i, t)))
    entry._begin_edit()
    entry._editor.setPlainText("hello there")
    entry._commit_edit()
    assert fired == [(0, "hello there")]
    assert entry._text == "hello there"
    assert entry._text_label.text() == "hello there"
    assert entry._editor is None


def test_commit_does_not_emit_when_unchanged(qapp) -> None:
    entry = _make_entry(qapp, "hello")
    fired: list[tuple[int, str]] = []
    entry.text_edited.connect(lambda i, t: fired.append((i, t)))
    entry._begin_edit()
    entry._commit_edit()
    assert fired == []


def test_cancel_restores_original_text(qapp) -> None:
    entry = _make_entry(qapp, "hello")
    fired: list[tuple[int, str]] = []
    entry.text_edited.connect(lambda i, t: fired.append((i, t)))
    entry._begin_edit()
    entry._editor.setPlainText("changed")
    entry._cancel_edit()
    assert fired == []
    assert entry._text_label.text() == "hello"
    assert entry._editor is None


def test_commit_empty_string_is_a_no_op(qapp) -> None:
    entry = _make_entry(qapp, "hello")
    fired: list[tuple[int, str]] = []
    entry.text_edited.connect(lambda i, t: fired.append((i, t)))
    entry._begin_edit()
    entry._editor.setPlainText("")
    entry._commit_edit()
    assert fired == []
    assert entry._text_label.text() == "hello"
