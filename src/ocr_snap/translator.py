from __future__ import annotations

import threading

import requests
from PyQt6.QtCore import QObject, pyqtSignal

_DEEPL_URL = "https://api-free.deepl.com/v2/translate"


class TranslationEngine(QObject):
    translation_ready = pyqtSignal(str, dict)  # (image_id, {index: translated_text})
    error_occurred = pyqtSignal(str)

    def __init__(self, api_key: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._api_key = api_key
        self._thread: threading.Thread | None = None
        self._pending: tuple[str, list[tuple[int, str]]] | None = None
        self._lock = threading.Lock()

    def translate(self, image_id: str, items: list[tuple[int, str]]) -> None:
        if not self._api_key or not items:
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                self._pending = (image_id, items)
                return
        self._start(image_id, items)

    def _start(self, image_id: str, items: list[tuple[int, str]]) -> None:
        self._thread = threading.Thread(
            target=self._run_worker, args=(image_id, items), daemon=True
        )
        self._thread.start()

    def _run_worker(self, image_id: str, items: list[tuple[int, str]]) -> None:
        try:
            texts = [text for _, text in items]
            indices = [idx for idx, _ in items]

            data: list[tuple[str, str]] = [("target_lang", "EN")]
            for text in texts:
                data.append(("text", text))

            resp = requests.post(
                _DEEPL_URL,
                data=data,
                headers={"Authorization": f"DeepL-Auth-Key {self._api_key}"},
                timeout=30,
            )
            resp.raise_for_status()

            result: dict[int, str] = {}
            translations = resp.json()["translations"]
            for idx, tr in zip(indices, translations):
                if tr.get("detected_source_language", "").upper() == "EN":
                    continue
                result[idx] = tr["text"]

            if result:
                self.translation_ready.emit(image_id, result)
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            # Check for pending work
            with self._lock:
                pending = self._pending
                self._pending = None
            if pending is not None:
                self._start(pending[0], pending[1])

    def shutdown(self) -> None:
        with self._lock:
            self._pending = None
        if self._thread is not None:
            self._thread.join(timeout=5)
