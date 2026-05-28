from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from ocr_snap.sidebar import OCRSidebar


def test_insert_adjust_panel_adds_widget(qapp) -> None:
    sidebar = OCRSidebar()
    panel = QWidget()
    sidebar.insert_adjust_panel(panel)
    assert panel.parent() is not None
    layout = sidebar.layout()
    assert layout is not None
    assert layout.indexOf(panel) != -1


def test_set_adjusted_hint_toggles_visibility(qapp) -> None:
    sidebar = OCRSidebar()
    # Use isHidden() (explicit hidden flag) rather than isVisible(), which is
    # False whenever an ancestor is hidden — the sidebar is never shown here.
    sidebar.set_adjusted_hint(True)
    assert sidebar._adjusted_hint.isHidden() is False
    sidebar.set_adjusted_hint(False)
    assert sidebar._adjusted_hint.isHidden() is True
