from __future__ import annotations

import collections
import concurrent.futures
import threading

import cv2
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from ocr_snap.models import OCRResultItem, OCRResults
from ocr_snap.perf_settings import OCRPerfSettings, effective_ocr_long_side

_PREDICT_TIMEOUT = 30  # seconds
_PRELOAD_TIMEOUT = 60  # seconds


class OCREngine(QObject):
    result_ready = pyqtSignal(str, OCRResults)  # (image_id, results)
    error_occurred = pyqtSignal(str)
    model_load_failed = pyqtSignal(str)

    def __init__(
        self, perf: OCRPerfSettings, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._perf = perf
        # Resolve device eagerly so the canvas can read effective_long_side
        # before the preload thread actually instantiates PaddleOCR.
        device = self._resolve_device()
        self.effective_long_side: int = effective_ocr_long_side(perf, device)
        self._resolved_device: str = device
        self._max_long_side = perf.ocr_max_long_side
        self._ocr: object | None = None
        self._queue: collections.deque[tuple[str, np.ndarray, float]] = collections.deque()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._preload_done = threading.Event()
        self._preload_error: str | None = None
        self._predict_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def preload(self) -> None:
        thread = threading.Thread(target=self._preload_worker, daemon=True)
        thread.start()

    def _preload_worker(self) -> None:
        try:
            self._init_ocr()
        except Exception as e:  # surface init failures up to the UI
            self._preload_error = str(e)
            self.model_load_failed.emit(str(e))
        finally:
            self._preload_done.set()

    def run(self, image_id: str, image: np.ndarray, *, min_confidence: float = 0.5) -> None:
        with self._lock:
            self._queue.append((image_id, image, min_confidence))
            if self._worker is not None and self._worker.is_alive():
                return
        self._start_worker()

    def _start_worker(self) -> None:
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _resolve_device(self) -> str:
        """Return 'gpu' or 'cpu' for PaddleOCR's device kwarg."""
        if self._perf.device == "cpu":
            return "cpu"
        # auto
        try:
            import paddle  # type: ignore[import-not-found]
            if paddle.is_compiled_with_cuda():
                return "gpu"
        except Exception:
            pass
        return "cpu"

    def _init_ocr(self) -> None:
        if self._ocr is not None:
            return
        from paddleocr import PaddleOCR

        if self._perf.model_variant == "server":
            det = "PP-OCRv5_server_det"
            rec = "PP-OCRv5_server_rec"
        else:
            det = "PP-OCRv5_mobile_det"
            rec = "PP-OCRv5_mobile_rec"

        device = self._resolved_device
        kwargs: dict[str, object] = dict(
            text_detection_model_name=det,
            text_recognition_model_name=rec,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device=device,
        )
        if device == "cpu" and self._perf.paddle_cpu_threads > 0:
            kwargs["cpu_threads"] = self._perf.paddle_cpu_threads
        self._ocr = PaddleOCR(**kwargs)

    def _worker_loop(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    return
                image_id, image, min_confidence = self._queue.popleft()
            self._process_one(image_id, image, min_confidence)

    def _process_one(self, image_id: str, image: np.ndarray, min_confidence: float) -> None:
        try:
            if not self._preload_done.wait(timeout=_PRELOAD_TIMEOUT):
                self.error_occurred.emit("OCR model loading timed out")
                return
            if self._preload_error is not None:
                self.error_occurred.emit(f"OCR model failed to load: {self._preload_error}")
                return
            self._init_ocr()  # fallback if preload() was never called

            h, w = image.shape[:2]
            scale = 1.0
            if max(h, w) > self._max_long_side:
                scale = self._max_long_side / max(h, w)
                new_w = int(w * scale)
                new_h = int(h * scale)
                image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

            future = self._predict_pool.submit(self._ocr.predict, image)  # type: ignore[union-attr]
            try:
                result = future.result(timeout=_PREDICT_TIMEOUT)
            except concurrent.futures.TimeoutError:
                self.error_occurred.emit("OCR timed out")
                return

            if not result or result[0] is None:
                self.result_ready.emit(image_id, OCRResults([], w, h))
                return

            page = result[0]
            texts = page["rec_texts"]
            scores = page["rec_scores"]
            polys = page["rec_polys"]
            boxes = page["rec_boxes"]

            inv_scale = 1.0 / scale

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
                        polygon=np.array(poly) * inv_scale,
                        bbox=(
                            float(box[0]) * inv_scale,
                            float(box[1]) * inv_scale,
                            float(box[2]) * inv_scale,
                            float(box[3]) * inv_scale,
                        ),
                    )
                )
                idx += 1

            self.result_ready.emit(image_id, OCRResults(items, w, h))
        except Exception as e:
            self.error_occurred.emit(str(e))

    def shutdown(self) -> None:
        with self._lock:
            self._queue.clear()
        if self._worker is not None:
            self._worker.join(timeout=5)
        self._predict_pool.shutdown(wait=False)
