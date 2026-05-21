from __future__ import annotations

import requests
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ocr_snap.config import save_app_settings
from ocr_snap.hardware_profile import detect
from ocr_snap.perf_settings import (
    AppSettings,
    TIER_LABELS,
    TIER_ORDER,
    apply_tier,
    from_profile,
)

_MODEL_OPTIONS = [
    ("Mobile (smaller, faster, less accurate)", "mobile"),
    ("Server (larger, slower, more accurate)", "server"),
]

_DEVICE_OPTIONS = [
    ("Auto (GPU if available)", "auto"),
    ("CPU only", "cpu"),
]


class SettingsDialog(QDialog):
    """Multi-group settings dialog: Translation / OCR engine / Hardware."""

    tier_overridden = pyqtSignal(str)
    perf_changed = pyqtSignal()

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self._settings = settings
        self._initial_tier = settings.hardware_tier
        self._initial_model = settings.perf.model_variant
        self._initial_device = settings.perf.device
        self._build_ui()

    # ── UI construction ────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(self._build_translation_group())
        layout.addWidget(self._build_ocr_group())
        layout.addWidget(self._build_hardware_group())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_translation_group(self) -> QGroupBox:
        box = QGroupBox("Translation (DeepL)")
        v = QVBoxLayout(box)

        hint = QLabel(
            "Used to translate OCR results. Free keys end with “:fx”. "
            "Get one at https://www.deepl.com/account/summary."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 12px;")
        v.addWidget(hint)

        row = QHBoxLayout()
        self._key_field = QLineEdit(self._settings.deepl_api_key)
        self._key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_field.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx:fx")
        row.addWidget(self._key_field, stretch=1)

        self._show_box = QCheckBox("Show")
        self._show_box.toggled.connect(self._toggle_visibility)
        row.addWidget(self._show_box)

        self._test_btn = QPushButton("Test key")
        self._test_btn.clicked.connect(self._on_test_key)
        row.addWidget(self._test_btn)
        v.addLayout(row)

        self._key_status = QLabel("")
        self._key_status.setWordWrap(True)
        self._key_status.setStyleSheet("font-size: 12px;")
        v.addWidget(self._key_status)

        return box

    def _build_ocr_group(self) -> QGroupBox:
        box = QGroupBox("OCR engine")
        form = QFormLayout(box)

        self._model_combo = QComboBox()
        for label, value in _MODEL_OPTIONS:
            self._model_combo.addItem(label, value)
        idx = self._model_combo.findData(self._settings.perf.model_variant)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        form.addRow("Model:", self._model_combo)

        self._device_combo = QComboBox()
        for label, value in _DEVICE_OPTIONS:
            self._device_combo.addItem(label, value)
        idx = self._device_combo.findData(self._settings.perf.device)
        if idx >= 0:
            self._device_combo.setCurrentIndex(idx)
        form.addRow("Device:", self._device_combo)

        note = QLabel(
            "Model or device changes take effect after restarting the app."
        )
        note.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        note.setWordWrap(True)
        form.addRow(note)

        return box

    def _build_hardware_group(self) -> QGroupBox:
        box = QGroupBox("Hardware profile")
        v = QVBoxLayout(box)

        row = QHBoxLayout()
        row.addWidget(QLabel("Profile:"))
        self._tier_combo = QComboBox()
        for tier in TIER_ORDER:
            self._tier_combo.addItem(TIER_LABELS[tier], tier)
        idx = (
            TIER_ORDER.index(self._settings.hardware_tier)
            if self._settings.hardware_tier in TIER_ORDER
            else 1
        )
        self._tier_combo.setCurrentIndex(idx)
        row.addWidget(self._tier_combo, 1)

        redetect = QPushButton("Auto-detect")
        redetect.setToolTip(
            "Re-run hardware detection and reset the profile to the recommended tier."
        )
        redetect.clicked.connect(self._on_redetect)
        row.addWidget(redetect)
        v.addLayout(row)

        self._detected_label = QLabel()
        self._detected_label.setStyleSheet("color: #888; font-size: 11px;")
        self._refresh_detected_label()
        v.addWidget(self._detected_label)

        note = QLabel(
            "Profile changes also rewrite Model and Device above. "
            "Restart the app for OCR-engine changes to take effect."
        )
        note.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        note.setWordWrap(True)
        v.addWidget(note)

        return box

    def _refresh_detected_label(self) -> None:
        tier_label = TIER_LABELS.get(
            self._settings.hardware_tier, self._settings.hardware_tier
        )
        self._detected_label.setText(
            f"Detected: <b>{self._settings.detected_ram_gb:.1f} GB</b> RAM · "
            f"<b>{self._settings.detected_cpu_cores}</b> cores · "
            f"auto-tier <b>{tier_label}</b>"
        )

    # ── Actions ────────────────────────────────────────────────────

    def _toggle_visibility(self, checked: bool) -> None:
        self._key_field.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _set_key_status(self, text: str, color: str) -> None:
        self._key_status.setText(text)
        self._key_status.setStyleSheet(f"font-size: 12px; color: {color};")

    def _on_test_key(self) -> None:
        key = self._key_field.text().strip()
        if not key:
            self._set_key_status("Key is empty.", "#e07a7a")
            return
        url = (
            "https://api-free.deepl.com/v2/usage"
            if key.endswith(":fx")
            else "https://api.deepl.com/v2/usage"
        )
        self._set_key_status("Testing…", "#888")
        self._test_btn.setEnabled(False)
        QApplication.processEvents()
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"DeepL-Auth-Key {key}"},
                timeout=10,
            )
        except requests.RequestException as e:
            self._test_btn.setEnabled(True)
            self._set_key_status(f"Network error: {e}", "#e07a7a")
            return
        self._test_btn.setEnabled(True)
        if resp.status_code == 200:
            self._set_key_status("Key OK.", "#7ad07a")
        elif resp.status_code in (401, 403):
            self._set_key_status("DeepL rejected the key (unauthorized).", "#e07a7a")
        else:
            self._set_key_status(
                f"Unexpected response from DeepL (HTTP {resp.status_code}).",
                "#e07a7a",
            )

    def _on_redetect(self) -> None:
        # Build fresh settings from detection, but preserve the DeepL key
        fresh = from_profile(detect(), deepl_key=self._key_field.text().strip())
        # Mutate the dialog's settings reference so labels/combos can refresh
        self._settings.perf = fresh.perf
        self._settings.hardware_tier = fresh.hardware_tier
        self._settings.detected_ram_gb = fresh.detected_ram_gb
        self._settings.detected_cpu_cores = fresh.detected_cpu_cores
        # Refresh UI
        idx = TIER_ORDER.index(fresh.hardware_tier)
        self._tier_combo.setCurrentIndex(idx)
        midx = self._model_combo.findData(fresh.perf.model_variant)
        if midx >= 0:
            self._model_combo.setCurrentIndex(midx)
        didx = self._device_combo.findData(fresh.perf.device)
        if didx >= 0:
            self._device_combo.setCurrentIndex(didx)
        self._refresh_detected_label()

    def _on_accept(self) -> None:
        # 1. DeepL key (always saved as entered; testing is advisory)
        self._settings.deepl_api_key = self._key_field.text().strip()

        # 2. Tier change wins over individual combos — apply_tier overwrites perf
        new_tier = self._tier_combo.currentData()
        tier_changed = new_tier != self._initial_tier
        if tier_changed:
            apply_tier(self._settings, new_tier)
        else:
            # 3. Otherwise apply individual model/device overrides
            self._settings.perf.model_variant = self._model_combo.currentData()
            self._settings.perf.device = self._device_combo.currentData()

        # Persist
        save_app_settings(self._settings)

        # Emit signals
        perf_engine_changed = (
            self._settings.perf.model_variant != self._initial_model
            or self._settings.perf.device != self._initial_device
        )
        if tier_changed:
            self.tier_overridden.emit(new_tier)
        if perf_engine_changed:
            self.perf_changed.emit()

        self.accept()
