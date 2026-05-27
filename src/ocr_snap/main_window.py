from __future__ import annotations

from uuid import uuid4

from PyQt6.QtCore import QSize, QTimer, Qt
from PyQt6.QtGui import (
    QCloseEvent,
    QKeyEvent,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
)

import numpy as np

from ocr_snap.canvas import OCRCanvas
from ocr_snap.gallery import GalleryPanel
from ocr_snap.models import ImageState, OCRResultItem, OCRResults, array_from_pixmap
from ocr_snap.ocr_engine import OCREngine, OCRRunOptions
from ocr_snap.perf_settings import AppSettings
from ocr_snap.settings_dialog import SettingsDialog
from ocr_snap.sidebar import OCRSidebar
from ocr_snap.theme import Icons, Tokens
from ocr_snap.translator import TranslationEngine

_APP_STYLE = f"""
QMainWindow, QWidget {{
    background-color: {Tokens.bg_base};
    color: {Tokens.text_primary};
}}
QStatusBar {{
    background: {Tokens.bg_deepest};
    color: {Tokens.text_muted};
    font-size: {Tokens.text_base}px;
    border-top: 1px solid {Tokens.border};
}}
QSplitter::handle {{
    background: {Tokens.border};
}}
QSplitter::handle:hover {{
    background: {Tokens.bg_hover};
}}
"""

_STATUS_SETTINGS_STYLE = f"""
QPushButton {{
    background: transparent;
    border: none;
    color: {Tokens.text_muted};
    font-size: {Tokens.text_eyebrow}px;
    padding: 2px 8px;
}}
QPushButton:hover {{
    color: {Tokens.text_emphasis};
}}
"""


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.setWindowTitle("OCR Snap")
        self.resize(1200, 800)
        self.setStyleSheet(_APP_STYLE)

        self._app_settings = settings
        self._ocr_engine = OCREngine(settings.perf, self)
        self._ocr_engine.preload()
        self._translator = TranslationEngine(settings.deepl_api_key, self)

        # Multi-image state
        self._images: dict[str, ImageState] = {}
        self._image_order: list[str] = []
        self._active_id: str | None = None

        # Widgets
        self._gallery = GalleryPanel()
        self._gallery.hide()

        self._canvas = OCRCanvas()
        self._canvas.set_effective_long_side(self._ocr_engine.effective_long_side)
        self._canvas.set_animation_mode(self._app_settings.perf.processing_animation)
        self._sidebar = OCRSidebar()
        self._sidebar.setMinimumWidth(200)
        self._sidebar.hide()

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._gallery)
        self._splitter.addWidget(self._canvas)
        self._splitter.addWidget(self._sidebar)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        self._splitter.setHandleWidth(4)
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)
        self._splitter.setCollapsible(2, False)
        self._splitter.setSizes([0, 880, 320])

        self.setCentralWidget(self._splitter)

        QShortcut(
            QKeySequence(QKeySequence.StandardKey.Preferences),
            self,
            activated=self._on_settings_requested,
        )

        # Status bar + permanent Settings button on its right side.
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._status_settings_btn = QPushButton("Settings")
        self._status_settings_btn.setIcon(Icons.settings(color=Tokens.text_muted))
        self._status_settings_btn.setIconSize(QSize(12, 12))
        self._status_settings_btn.setFlat(True)
        self._status_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._status_settings_btn.setStyleSheet(_STATUS_SETTINGS_STYLE)
        self._status_settings_btn.clicked.connect(self._on_settings_requested)
        self._status_bar.addPermanentWidget(self._status_settings_btn)

        # Reveal animation state
        self._reveal_timer = QTimer(self)
        self._reveal_timer.timeout.connect(self._reveal_next)
        self._reveal_index = 0
        self._reveal_count = 0

        # Wiring
        self._canvas.image_loaded.connect(self._on_image_loaded)
        self._ocr_engine.result_ready.connect(self._on_ocr_results)
        self._ocr_engine.error_occurred.connect(self._on_ocr_error)
        self._ocr_engine.model_load_failed.connect(self._on_model_load_failed)
        self._model_load_failure_shown = False
        self._canvas.merge_requested.connect(self._on_merge)
        self._sidebar.merge_requested.connect(self._on_merge)
        self._canvas.delete_requested.connect(self._on_delete)
        self._sidebar.delete_requested.connect(self._on_delete)
        self._translator.translation_ready.connect(self._on_translation_results)
        self._translator.error_occurred.connect(self._on_translation_error)
        self._sidebar.confidence_filter_changed.connect(self._on_confidence_filter_changed)
        self._sidebar.reocr_requested.connect(self._on_reocr_requested)
        self._sidebar.overlay_toggled.connect(self._on_overlay_toggled)
        self._gallery.image_selected.connect(self._on_gallery_select)
        self._gallery.image_removed.connect(self._on_gallery_remove)

    # ── Image loaded ────────────────────────────────────────────────

    def _on_image_loaded(self, array: np.ndarray, pixmap: QPixmap) -> None:
        image_id = str(uuid4())
        state = ImageState(image_id, pixmap, array)
        state.ocr_running = True
        self._images[image_id] = state
        self._image_order.append(image_id)

        self._gallery.add_image(image_id, pixmap)
        self._gallery.set_processing(image_id, True)

        if self._gallery.count >= 2:
            self._gallery.show()

        self._switch_to(image_id)
        self._ocr_engine.run(image_id, array)
        self._status_bar.showMessage("Running OCR...")

    # ── Switching ───────────────────────────────────────────────────

    def _switch_to(self, image_id: str) -> None:
        state = self._images.get(image_id)
        if state is None:
            return

        # Stop reveal timer
        self._reveal_timer.stop()

        self._active_id = image_id

        # Load incoming image
        self._canvas.load_image_state(state)

        if state.ocr_results is not None:
            self._sidebar.set_results(
                state.ocr_results, state.selection_model, visible=True
            )
            # Re-apply translations
            translations = {
                item.index: item.translated_text
                for item in state.ocr_results.items
                if item.translated_text is not None
            }
            if translations:
                self._sidebar.update_translations(translations)
            self._sidebar.show()
            self._sidebar.set_translating(state.translation_running)
            # Restore confidence slider state
            self._sidebar.set_ocr_threshold(state.ocr_threshold)
            self._sidebar.set_confidence_filter(int(state.confidence_filter * 100))
            self._apply_confidence_filter(state)
            self._sidebar.set_overlay_checked(state.overlay_enabled)
            self._canvas.set_overlay_visible(state.overlay_enabled)
        else:
            self._sidebar.clear()
            self._sidebar.show()
            if state.ocr_running:
                self._canvas.set_processing(True)

        self._gallery.set_active(image_id)

    # ── OCR results ─────────────────────────────────────────────────

    def _on_ocr_results(self, image_id: str, results: OCRResults) -> None:
        state = self._images.get(image_id)
        if state is None:
            return

        state.ocr_results = results
        if results.items:
            state.array = None
        state.ocr_running = False
        self._gallery.set_processing(image_id, False)

        if image_id == self._active_id:
            self._canvas.set_processing(False)
            self._reveal_timer.stop()

            state.selection_model.hovered_index = -1
            state.selection_model.clear()
            self._canvas.set_ocr_results(results, state.selection_model)
            self._sidebar.set_results(results, state.selection_model)

            # Update sidebar's OCR threshold
            self._sidebar.set_ocr_threshold(state.ocr_threshold)

            self._canvas.set_overlay_visible(state.overlay_enabled)

            if results.items:
                self._sidebar.show()
                self._reveal_index = 0
                self._reveal_count = len(results.items)
                interval = min(80, max(30, 2000 // self._reveal_count))
                self._reveal_timer.setInterval(interval)
                self._reveal_next()
                self._reveal_timer.start()
                # Apply current confidence filter after reveal
                self._apply_confidence_filter(state)
            else:
                self._sidebar.show()

            count = len(results.items)
            self._status_bar.showMessage(
                f"Found {count} text region{'s' if count != 1 else ''}",
                5000,
            )
        # Start translation for this image regardless of whether it's active
        self._start_translation(image_id)

    def _reveal_next(self) -> None:
        if self._reveal_index >= self._reveal_count:
            self._reveal_timer.stop()
            return
        self._canvas.reveal_item(self._reveal_index)
        self._sidebar.reveal_entry(self._reveal_index)
        self._reveal_index += 1

    # ── Confidence filter ───────────────────────────────────────────

    def _on_confidence_filter_changed(self, threshold: float) -> None:
        if self._active_id is None:
            return
        state = self._images.get(self._active_id)
        if state is None:
            return
        state.confidence_filter = threshold
        self._apply_confidence_filter(state)

    def _apply_confidence_filter(self, state: ImageState) -> None:
        if state.ocr_results is None:
            return
        threshold = state.confidence_filter
        self._sidebar.filter_by_confidence(threshold)
        for i, item in enumerate(state.ocr_results.items):
            self._canvas.set_item_visible(i, item.confidence >= threshold)

    def _on_reocr_requested(self, threshold: float) -> None:
        if self._active_id is None:
            return
        state = self._images.get(self._active_id)
        if state is None:
            return
        if state.array is None:
            state.array = array_from_pixmap(
                state.pixmap,
                max_long_side=self._ocr_engine.effective_long_side,
            )
        state.ocr_threshold = threshold
        state.ocr_running = True
        self._canvas.set_processing(True)
        self._gallery.set_processing(self._active_id, True)
        self._ocr_engine.run(
            self._active_id, state.array, OCRRunOptions(min_confidence=threshold)
        )
        self._status_bar.showMessage("Re-running OCR with lower threshold...")

    # ── Merge ───────────────────────────────────────────────────────

    def _on_merge(self, ordered_indices: list[int]) -> None:
        if self._active_id is None:
            return
        state = self._images.get(self._active_id)
        if state is None or state.ocr_results is None:
            return

        if len(ordered_indices) < 2:
            return

        items = state.ocr_results.items
        items_by_index = {item.index: item for item in items}
        sel_items = [items_by_index[idx] for idx in ordered_indices if idx in items_by_index]

        merged_text = " ".join(it.text for it in sel_items)
        merged_confidence = float(np.mean([it.confidence for it in sel_items]))
        x1 = min(it.bbox[0] for it in sel_items)
        y1 = min(it.bbox[1] for it in sel_items)
        x2 = max(it.bbox[2] for it in sel_items)
        y2 = max(it.bbox[3] for it in sel_items)
        merged_bbox = (x1, y1, x2, y2)
        merged_polygon = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])

        merged_item = OCRResultItem(
            index=0,
            text=merged_text,
            confidence=merged_confidence,
            polygon=merged_polygon,
            bbox=merged_bbox,
        )

        selected = set(ordered_indices)
        first_selected = True
        new_items: list[OCRResultItem] = []
        for item in items:
            if item.index in selected:
                if first_selected:
                    new_items.append(merged_item)
                    first_selected = False
            else:
                new_items.append(item)

        for i, item in enumerate(new_items):
            item.index = i

        new_results = OCRResults(
            items=new_items,
            image_width=state.ocr_results.image_width,
            image_height=state.ocr_results.image_height,
        )

        self._reveal_timer.stop()
        state.selection_model.clear()
        state.ocr_results = new_results
        self._canvas.set_ocr_results(new_results, state.selection_model, visible=True)
        self._sidebar.set_results(new_results, state.selection_model, visible=True)

        self._canvas.set_overlay_visible(state.overlay_enabled)

        count = len(new_results.items)
        self._status_bar.showMessage(
            f"Merged {len(sel_items)} items — {count} region{'s' if count != 1 else ''} remaining",
            5000,
        )

        self._start_translation(self._active_id)

    # ── Delete ─────────────────────────────────────────────────────

    def _on_delete(self) -> None:
        if self._active_id is None:
            return
        state = self._images.get(self._active_id)
        if state is None or state.ocr_results is None:
            return

        selected = state.selection_model.selected_indices
        if len(selected) < 1:
            return

        items = state.ocr_results.items
        new_items = [item for item in items if item.index not in selected]

        for i, item in enumerate(new_items):
            item.index = i

        new_results = OCRResults(
            items=new_items,
            image_width=state.ocr_results.image_width,
            image_height=state.ocr_results.image_height,
        )

        self._reveal_timer.stop()
        state.selection_model.clear()
        state.ocr_results = new_results
        self._canvas.set_ocr_results(new_results, state.selection_model, visible=True)
        self._sidebar.set_results(new_results, state.selection_model, visible=True)

        self._canvas.set_overlay_visible(state.overlay_enabled)

        deleted_count = len(selected)
        self._status_bar.showMessage(
            f"Deleted {deleted_count} item{'s' if deleted_count != 1 else ''}",
            5000,
        )

        if new_results.items:
            self._start_translation(self._active_id)

    # ── Overlay ─────────────────────────────────────────────────────

    def _on_overlay_toggled(self, checked: bool) -> None:
        if self._active_id is None:
            return
        state = self._images.get(self._active_id)
        if state is not None:
            state.overlay_enabled = checked
        self._canvas.set_overlay_visible(checked)

    # ── Settings ────────────────────────────────────────────────────

    def _on_settings_requested(self) -> None:
        dialog = SettingsDialog(self._app_settings, self)
        needs_restart = {"flag": False}

        def on_tier(_tier: str) -> None:
            needs_restart["flag"] = True

        def on_perf_changed() -> None:
            needs_restart["flag"] = True

        dialog.tier_overridden.connect(on_tier)
        dialog.perf_changed.connect(on_perf_changed)

        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return

        # Always apply the live changes
        self._translator.set_api_key(self._app_settings.deepl_api_key)
        self._canvas.set_animation_mode(self._app_settings.perf.processing_animation)
        self._status_bar.showMessage("Settings saved.", 5000)

        if needs_restart["flag"]:
            QMessageBox.information(
                self,
                "Restart required",
                "Model or device changes will take effect after you restart OCR Snap.",
            )

    # ── Translation ─────────────────────────────────────────────────

    def _start_translation(self, image_id: str) -> None:
        state = self._images.get(image_id)
        if state is None or state.ocr_results is None:
            return
        items = [(it.index, it.text) for it in state.ocr_results.items]
        if not self._translator.translate(image_id, items):
            return
        state.translation_running = True
        if image_id == self._active_id:
            self._sidebar.set_translating(True)

    def _on_translation_results(
        self, image_id: str, translations: dict[int, str]
    ) -> None:
        state = self._images.get(image_id)
        if state is None or state.ocr_results is None:
            return

        state.translation_running = False
        for item in state.ocr_results.items:
            if item.index in translations:
                item.translated_text = translations[item.index]

        if image_id == self._active_id:
            self._sidebar.update_translations(translations)
            self._sidebar.set_translating(False)
            self._canvas.set_overlay_texts(state.ocr_results.items)

    def _on_translation_error(self, message: str) -> None:
        # Mark active image as not translating
        if self._active_id is not None:
            state = self._images.get(self._active_id)
            if state is not None:
                state.translation_running = False
        self._sidebar.set_translating(False)
        self._status_bar.showMessage(f"Translation error: {message}", 10000)

    # ── Gallery events ──────────────────────────────────────────────

    def _on_gallery_select(self, image_id: str) -> None:
        if image_id != self._active_id:
            self._switch_to(image_id)

    def _on_gallery_remove(self, image_id: str) -> None:
        state = self._images.pop(image_id, None)
        if state is None:
            return

        idx = self._image_order.index(image_id)
        self._image_order.remove(image_id)
        self._gallery.remove_image(image_id)

        if not self._image_order:
            # No images left
            self._active_id = None
            self._reveal_timer.stop()
            self._canvas.show_placeholder()
            self._sidebar.clear()
            self._sidebar.hide()
            self._gallery.hide()
            return

        if self._gallery.count < 2:
            self._gallery.hide()

        if image_id == self._active_id:
            # Switch to adjacent image
            new_idx = min(idx, len(self._image_order) - 1)
            self._active_id = None  # prevent saving view state for removed image
            self._switch_to(self._image_order[new_idx])

    # ── Errors ──────────────────────────────────────────────────────

    def _on_ocr_error(self, message: str) -> None:
        self._status_bar.showMessage(f"OCR Error: {message}", 10000)

    def _on_model_load_failed(self, message: str) -> None:
        self._status_bar.showMessage(
            f"OCR model failed to load: {message}", 0  # persistent
        )
        if not self._model_load_failure_shown:
            self._model_load_failure_shown = True
            QMessageBox.critical(
                self,
                "OCR engine could not load",
                (
                    "The OCR model failed to load:\n\n"
                    f"{message}\n\n"
                    "Open Settings to try a smaller model (Mobile) or switch the "
                    "Device to CPU only, then restart OCR Snap."
                ),
            )

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is not None and event.matches(QKeySequence.StandardKey.Paste):
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                qimg = clipboard.image()
                if not qimg.isNull():
                    self._canvas._load_qimage(qimg)
                    return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self._ocr_engine.shutdown()
        self._translator.shutdown()
        super().closeEvent(event)
