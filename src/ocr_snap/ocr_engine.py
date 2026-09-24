from __future__ import annotations

import collections
import concurrent.futures
import threading
from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from ocr_snap.languages import DEFAULT_LANGUAGE
from ocr_snap.models import Adjustments, OCRResultItem, OCRResults
from ocr_snap.perf_settings import OCRPerfSettings, effective_ocr_long_side

_PREDICT_TIMEOUT = 30  # seconds
_PRELOAD_TIMEOUT = 60  # seconds


@dataclass
class OCRRunOptions:
    """Per-prediction OCR options carried through the engine work queue."""

    min_confidence: float = 0.5
    use_doc_orientation_classify: bool = False
    use_doc_unwarping: bool = False
    use_textline_orientation: bool = False
    text_det_thresh: float | None = None
    text_det_box_thresh: float | None = None
    text_det_unclip_ratio: float | None = None

    def uses_correction(self) -> bool:
        return (
            self.use_doc_orientation_classify
            or self.use_doc_unwarping
            or self.use_textline_orientation
        )

    def predict_kwargs(self) -> dict[str, object]:
        kw: dict[str, object] = {
            "use_doc_orientation_classify": self.use_doc_orientation_classify,
            "use_doc_unwarping": self.use_doc_unwarping,
            "use_textline_orientation": self.use_textline_orientation,
        }
        if self.text_det_thresh is not None:
            kw["text_det_thresh"] = self.text_det_thresh
        if self.text_det_box_thresh is not None:
            kw["text_det_box_thresh"] = self.text_det_box_thresh
        if self.text_det_unclip_ratio is not None:
            kw["text_det_unclip_ratio"] = self.text_det_unclip_ratio
        return kw

    @classmethod
    def from_adjustments(cls, adj: Adjustments, min_confidence: float) -> OCRRunOptions:
        """Map Adjustments + min_confidence to engine options. Detection
        thresholds stay None (Paddle defaults) when sensitivity is 0."""
        thresh: float | None = None
        box: float | None = None
        unclip: float | None = None
        s = adj.det_sensitivity
        if s > 0.0:
            thresh = 0.3 - 0.2 * s
            box = 0.6 - 0.3 * s
            unclip = 1.5 + 0.5 * s
        return cls(
            min_confidence=min_confidence,
            use_doc_orientation_classify=adj.smart_fix,
            use_doc_unwarping=adj.smart_fix,
            use_textline_orientation=adj.smart_fix,
            text_det_thresh=thresh,
            text_det_box_thresh=box,
            text_det_unclip_ratio=unclip,
        )


class OCREngine(QObject):
    result_ready = pyqtSignal(str, OCRResults)  # (image_id, results)
    error_occurred = pyqtSignal(str)
    model_load_failed = pyqtSignal(str)

    def __init__(
        self,
        perf: OCRPerfSettings,
        language: str = DEFAULT_LANGUAGE,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._perf = perf
        self._language = language
        # The language the cached models were built with (worker-confined).
        self._built_language = language
        # Resolve device eagerly so the canvas can read effective_long_side
        # before the preload thread actually instantiates PaddleOCR.
        device = self._resolve_device()
        self.effective_long_side: int = effective_ocr_long_side(perf, device)
        self._resolved_device: str = device
        self._ocr: object | None = None
        self._correction_ocr: object | None = None
        self._queue: collections.deque[tuple[str, np.ndarray, OCRRunOptions]] = collections.deque()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._preload_done = threading.Event()
        self._preload_error: str | None = None
        self._predict_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    @property
    def device(self) -> str:
        """The device OCR runs on: "gpu" or "cpu"."""
        return self._resolved_device

    def model_names(self) -> tuple[str, str]:
        """(detection, recognition) model names for the current language."""
        return self._resolve_models(self._language)

    def load_models(self) -> object:
        """Build the plain (no-correction) PaddleOCR engine now, on the
        calling thread, and return it. For the headless checks; the window
        uses preload()."""
        self._init_ocr()
        assert self._ocr is not None
        return self._ocr

    def set_language(self, language: str) -> None:
        """Switch the OCR language live. The worker rebuilds its models lazily
        on the next job (it compares ``_built_language`` to ``_language``).
        Assignment is atomic, so no lock is needed here."""
        self._language = language

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

    def run(
        self, image_id: str, image: np.ndarray, options: OCRRunOptions | None = None
    ) -> None:
        if options is None:
            options = OCRRunOptions()
        with self._lock:
            # Supersede any pending entry for the same image_id. The
            # currently-running predict cannot be cancelled, but its pending
            # successor is replaced by the latest request.
            self._queue = collections.deque(
                entry for entry in self._queue if entry[0] != image_id
            )
            self._queue.append((image_id, image, options))
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

    # PaddleOCR 3.4.1 per-language recognition models (mirrors its own
    # _get_ocr_model_names). ch/chinese_cht/japan share the unified CJK+En
    # rec model, which has a mobile and a server variant; the rest are
    # mobile-only language/script models.
    _CJK_LANGS = ("ch", "chinese_cht", "japan")
    _REC_BY_LANG = {
        "en": "en_PP-OCRv5_mobile_rec",
        "korean": "korean_PP-OCRv5_mobile_rec",
        "fr": "latin_PP-OCRv5_mobile_rec",
        "de": "latin_PP-OCRv5_mobile_rec",
        "es": "latin_PP-OCRv5_mobile_rec",
        "ru": "eslav_PP-OCRv5_mobile_rec",
        "ar": "arabic_PP-OCRv5_mobile_rec",
    }

    def _resolve_models(self, language: str) -> tuple[str, str]:
        """Return (detection_model_name, recognition_model_name) for a language."""
        server = self._perf.model_variant == "server"
        det = "PP-OCRv5_server_det" if server else "PP-OCRv5_mobile_det"
        if language in self._CJK_LANGS:
            rec = "PP-OCRv5_server_rec" if server else "PP-OCRv5_mobile_rec"
        else:
            rec = self._REC_BY_LANG.get(language, "PP-OCRv5_mobile_rec")
        return det, rec

    def _build_kwargs(self, *, corrections: bool) -> dict[str, object]:
        det, rec = self._resolve_models(self._language)
        kwargs: dict[str, object] = dict(
            text_detection_model_name=det,
            text_recognition_model_name=rec,
            use_doc_orientation_classify=corrections,
            use_doc_unwarping=corrections,
            use_textline_orientation=corrections,
            device=self._resolved_device,
        )
        if self._resolved_device == "cpu":
            # paddlepaddle 3.3.x cannot lower the PP-OCRv5 detection models
            # through its PIR oneDNN executor — the first predict() raises
            # NotImplementedError on a pir::ArrayAttribute<pir::DoubleAttribute>
            # op attribute. oneDNN is on by default for CPU inference, so opt
            # out until upstream fixes it (PaddlePaddle/Paddle#77340).
            kwargs["enable_mkldnn"] = False
            if self._perf.paddle_cpu_threads > 0:
                kwargs["cpu_threads"] = self._perf.paddle_cpu_threads
        return kwargs

    def _build_ocr(self, *, corrections: bool) -> object:
        from paddleocr import PaddleOCR

        return PaddleOCR(**self._build_kwargs(corrections=corrections))

    def _init_ocr(self) -> None:
        if self._ocr is None:
            self._ocr = self._build_ocr(corrections=False)

    def _get_correction_ocr(self) -> object:
        if self._correction_ocr is None:
            self._correction_ocr = self._build_ocr(corrections=True)
        return self._correction_ocr

    def _select_ocr(self, options: OCRRunOptions) -> object:
        if self._built_language != self._language:
            # Language switched since the cached models were built — drop them
            # so the next build below uses the new language.
            self._ocr = None
            self._correction_ocr = None
            self._built_language = self._language
        if options.uses_correction():
            return self._get_correction_ocr()
        self._init_ocr()
        assert self._ocr is not None  # _init_ocr guarantees this
        return self._ocr

    def _worker_loop(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    return
                image_id, image, options = self._queue.popleft()
            self._process_one(image_id, image, options)

    def _process_one(
        self, image_id: str, image: np.ndarray, options: OCRRunOptions
    ) -> None:
        try:
            if not self._preload_done.wait(timeout=_PRELOAD_TIMEOUT):
                self.error_occurred.emit("OCR model loading timed out")
                return
            if self._preload_error is not None:
                self.error_occurred.emit(f"OCR model failed to load: {self._preload_error}")
                return
            self._init_ocr()  # fallback if preload() was never called

            h, w = image.shape[:2]
            ocr = self._select_ocr(options)
            # Correction runs use a dedicated engine built with corrections on;
            # the per-call flags below are consistent there and all False for
            # the normal engine.
            predict_kwargs = options.predict_kwargs()

            future = self._predict_pool.submit(ocr.predict, image, **predict_kwargs)  # type: ignore[union-attr]
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

            items = []
            idx = 0
            for text, score, poly, box in zip(texts, scores, polys, boxes):
                if float(score) < options.min_confidence:
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

            self.result_ready.emit(image_id, OCRResults(items, w, h))
        except Exception as e:
            self.error_occurred.emit(str(e))

    def shutdown(self) -> None:
        with self._lock:
            self._queue.clear()
        if self._worker is not None:
            self._worker.join(timeout=5)
        self._predict_pool.shutdown(wait=False)
