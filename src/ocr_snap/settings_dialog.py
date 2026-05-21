from __future__ import annotations

import requests
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    def __init__(self, current_key: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(440)
        self._saved_key: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("DeepL API key")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        hint = QLabel(
            "Used to translate OCR results. Find your key at "
            "https://www.deepl.com/account/summary. Free keys end with “:fx”."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(hint)

        key_row = QHBoxLayout()
        self._key_field = QLineEdit(current_key)
        self._key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_field.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx:fx")
        key_row.addWidget(self._key_field, stretch=1)

        self._show_box = QCheckBox("Show")
        self._show_box.toggled.connect(self._toggle_visibility)
        key_row.addWidget(self._show_box)
        layout.addLayout(key_row)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._status)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Save).setText("Test & save")
        self._buttons.accepted.connect(self._on_save)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _toggle_visibility(self, checked: bool) -> None:
        self._key_field.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _set_status(self, text: str, color: str) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(f"font-size: 12px; color: {color};")

    def _on_save(self) -> None:
        key = self._key_field.text().strip()
        if not key:
            self._set_status("Key cannot be empty.", "#e07a7a")
            return

        url = (
            "https://api-free.deepl.com/v2/usage"
            if key.endswith(":fx")
            else "https://api.deepl.com/v2/usage"
        )

        self._set_status("Testing key…", "#888")
        self._buttons.setEnabled(False)
        QApplication.processEvents()

        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"DeepL-Auth-Key {key}"},
                timeout=10,
            )
        except requests.RequestException as e:
            self._buttons.setEnabled(True)
            self._set_status(f"Network error: {e}", "#e07a7a")
            return

        self._buttons.setEnabled(True)

        if resp.status_code == 200:
            self._saved_key = key
            self.accept()
        elif resp.status_code in (401, 403):
            self._set_status("DeepL rejected the key (unauthorized).", "#e07a7a")
        else:
            self._set_status(
                f"Unexpected response from DeepL (HTTP {resp.status_code}).", "#e07a7a"
            )

    def saved_key(self) -> str | None:
        return self._saved_key
