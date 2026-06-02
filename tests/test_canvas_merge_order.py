from __future__ import annotations

from PyQt6.QtWidgets import QMenu

from ocr_snap.canvas import _MergeOrderAction, _MergeOrderWidget, _SQUARE_SIZE


def test_merge_order_squares_keep_fixed_size_regardless_of_count(qapp):
    """Regression: squares must not shrink as more labels are merged.

    Previously the order preview was a QPixmap shoved into QMenu's 16px icon
    slot, so a wider pixmap (more labels) got scaled down and the squares
    collapsed to a few px tall. The widget now paints squares at a fixed size,
    so the row height is constant and only the width grows with label count.
    """
    w2 = _MergeOrderWidget((0, 1))
    w3 = _MergeOrderWidget((0, 1, 2))
    w4 = _MergeOrderWidget((0, 1, 2, 3))

    # Square-row height is identical no matter how many labels.
    assert w2.height() == w3.height() == w4.height()
    # Each square keeps at least its full design size (no shrink).
    assert w2.height() >= _SQUARE_SIZE
    # Width grows with count instead of squeezing the squares smaller.
    assert w2.width() < w3.width() < w4.width()
    # Each added label widens the row by exactly one square + separators.
    step = w4.width() - w3.width()
    assert step == w3.width() - w2.width()
    assert step >= _SQUARE_SIZE


def test_merge_order_action_invokes_callback_with_order(qapp):
    captured: list[list[int]] = []
    action = _MergeOrderAction((2, 0, 1), captured.append)
    action.defaultWidget().clicked.emit()
    assert captured == [[2, 0, 1]]


def test_ordinal_words(qapp):
    from ocr_snap.canvas import _ordinal

    assert _ordinal(1) == "first"
    assert _ordinal(3) == "third"
    assert _ordinal(10) == "tenth"
    assert _ordinal(11) == "11th"  # fallback beyond the word list


def test_make_swatch_icon_is_square_and_nonnull(qapp):
    from ocr_snap.canvas import _SQUARE_SIZE, _make_swatch_icon

    icon = _make_swatch_icon(0)
    assert not icon.isNull()
    sizes = icon.availableSizes()
    assert sizes
    assert sizes[0].width() == sizes[0].height() == _SQUARE_SIZE


def test_merge_order_action_display_differs_from_emitted_order(qapp):
    from ocr_snap.canvas import _MergeOrderAction

    captured: list[list[int]] = []
    action = _MergeOrderAction((0, 1, 2, 3), captured.append, display=(2, 3))
    # Widget shows only the two display swatches...
    assert action.defaultWidget()._indices == (2, 3)
    # ...but clicking emits the full order.
    action.defaultWidget().clicked.emit()
    assert captured == [[0, 1, 2, 3]]


def _root_submenu(menu):
    """Return (submenu-action, submenu) for the single 'Merge selected' submenu."""
    action = next(a for a in menu.actions() if a.menu() is not None)
    return action, action.menu()


def _child_submenus(menu):
    return [a.menu() for a in menu.actions() if a.menu() is not None]


def _leaf_actions(menu):
    from ocr_snap.canvas import _MergeOrderAction

    return [a for a in menu.actions() if isinstance(a, _MergeOrderAction)]


def _section_titles(menu):
    return [a.text() for a in menu.actions() if a.isSeparator() and a.text()]


def test_small_selection_uses_flat_permutation_menu(qapp):
    from ocr_snap.canvas import _add_merge_permutation_actions

    menu = QMenu()
    _add_merge_permutation_actions(menu, [0, 1, 2], lambda o: None)
    action, root = _root_submenu(menu)
    assert action.text() == "Merge selected (3)"
    assert len(_leaf_actions(root)) == 6  # 3! permutations, shown flat
    assert _child_submenus(root) == []


def test_two_label_selection_uses_flat_permutation_menu(qapp):
    from ocr_snap.canvas import _add_merge_permutation_actions

    menu = QMenu()
    _add_merge_permutation_actions(menu, [0, 1], lambda o: None)
    action, root = _root_submenu(menu)
    assert action.text() == "Merge selected (2)"
    assert len(_leaf_actions(root)) == 2  # 2! permutations, shown flat
    assert _child_submenus(root) == []


def test_large_selection_builds_lazy_cascade_top_level(qapp):
    from ocr_snap.canvas import _add_merge_permutation_actions

    menu = QMenu()
    _add_merge_permutation_actions(menu, [0, 1, 2, 3], lambda o: None)
    action, root = _root_submenu(menu)
    assert action.text() == "Merge selected (4)"
    # One swatch submenu per label, no leaf rows yet (lazy).
    assert len(_child_submenus(root)) == 4
    assert _leaf_actions(root) == []
    assert _section_titles(root) == ["Select the first item"]


def test_cascade_second_level_populates_on_about_to_show(qapp):
    from ocr_snap.canvas import _add_merge_permutation_actions

    menu = QMenu()
    _add_merge_permutation_actions(menu, [0, 1, 2, 3], lambda o: None)
    _, root = _root_submenu(menu)
    first_sub = _child_submenus(root)[0]
    assert first_sub.actions() == []  # not built until shown
    first_sub.aboutToShow.emit()
    # remaining == 3 -> three deeper swatch submenus, no leaves yet.
    assert len(_child_submenus(first_sub)) == 3
    assert _leaf_actions(first_sub) == []
    assert _section_titles(first_sub) == ["Select the second item"]


def test_cascade_leaf_shows_last_two_and_emits_full_order(qapp):
    from ocr_snap.canvas import _add_merge_permutation_actions

    captured: list[list[int]] = []
    menu = QMenu()
    _add_merge_permutation_actions(menu, [0, 1, 2, 3], captured.append)
    _, root = _root_submenu(menu)

    sub0 = _child_submenus(root)[0]      # picked first label = 0
    sub0.aboutToShow.emit()
    sub01 = _child_submenus(sub0)[0]     # picked second label = 1 (remaining [1,2,3] -> first is 1)
    sub01.aboutToShow.emit()

    assert _section_titles(sub01) == ["Select the rest"]
    leaves = _leaf_actions(sub01)
    assert len(leaves) == 2
    # Full emitted orders = prefix [0, 1] + each permutation of the last two.
    assert sorted(tuple(a._order) for a in leaves) == [(0, 1, 2, 3), (0, 1, 3, 2)]
    # Display shows only the final two swatches.
    assert sorted(tuple(a.defaultWidget()._indices) for a in leaves) == [(2, 3), (3, 2)]
    # Clicking emits the full order.
    leaf = next(a for a in leaves if tuple(a._order) == (0, 1, 2, 3))
    leaf.defaultWidget().clicked.emit()
    assert captured == [[0, 1, 2, 3]]


def test_large_selection_does_not_enumerate_all_permutations(qapp):
    from ocr_snap.canvas import _add_merge_permutation_actions

    # N=8 -> 40320 permutations if enumerated. The cascade only builds the top
    # level (8 submenu shells), so this returns immediately.
    menu = QMenu()
    _add_merge_permutation_actions(menu, list(range(8)), lambda o: None)
    _, root = _root_submenu(menu)
    assert len(_child_submenus(root)) == 8
    assert _leaf_actions(root) == []
