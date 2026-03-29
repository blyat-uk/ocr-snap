from __future__ import annotations

import collections
import threading

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from ocr_snap.models import OCRResultItem, OCRResults


class OCREngine(QObject):
    result_ready = pyqtSignal(str, OCRResults)  # (image_id, results)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ocr: object | None = None
        self._queue: collections.deque[tuple[str, np.ndarray, float]] = collections.deque()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._preload_done = threading.Event()

    def preload(self) -> None:
        """Start loading the OCR model in a background thread."""
        thread = threading.Thread(target=self._preload_worker, daemon=True)
        thread.start()

    def _preload_worker(self) -> None:
        try:
            self._init_ocr()
        finally:
            self._preload_done.set()

    def run(self, image_id: str, image: np.ndarray, *, min_confidence: float = 0.5) -> None:
        with self._lock:
            self._queue.append((image_id, image, min_confidence))
            if self._worker is not None and self._worker.is_alive():
                return  # worker will pick it up
        self._start_worker()

    def _start_worker(self) -> None:
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _init_ocr(self) -> None:
        if self._ocr is None:
            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(
                text_detection_model_name="PP-OCRv5_server_det",
                text_recognition_model_name="PP-OCRv5_server_rec",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )

    def _worker_loop(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    return
                image_id, image, min_confidence = self._queue.popleft()
            self._process_one(image_id, image, min_confidence)

    def _process_one(self, image_id: str, image: np.ndarray, min_confidence: float) -> None:
        try:
            self._preload_done.wait()
            self._init_ocr()  # fallback if preload() was never called
            result = self._ocr.predict(image)  # type: ignore[union-attr]
            if not result or result[0] is None:
                self.result_ready.emit(
                    image_id, OCRResults([], image.shape[1], image.shape[0])
                )
                return

            page = result[0]
            texts = page["rec_texts"]
            scores = page["rec_scores"]
            polys = page["rec_polys"]
            boxes = page["rec_boxes"]

            items = []
            idx = 0
            for text, score, poly, box in zip(texts, scores, polys, boxes):
                if float(score) < min_confidence:
                    continue
                items.append(
                    OCRResultItem(
                        index=idx,
                        text=text,
                        confidence=float(score),
                        polygon=np.array(poly),
                        bbox=(
                            float(box[0]),
                            float(box[1]),
                            float(box[2]),
                            float(box[3]),
                        ),
                    )
                )
                idx += 1

            self.result_ready.emit(
                image_id, OCRResults(items, image.shape[1], image.shape[0])
            )
        except Exception as e:
            self.error_occurred.emit(str(e))

    def shutdown(self) -> None:
        with self._lock:
            self._queue.clear()
        if self._worker is not None:
            self._worker.join(timeout=5)
