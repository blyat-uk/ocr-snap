from __future__ import annotations

import threading

import numpy as np

from ocr_snap.ocr_engine import OCREngine, OCRRunOptions
from ocr_snap.perf_settings import OCRPerfSettings


def test_engine_effective_long_side_cpu(qapp) -> None:
    """When perf.device='cpu', engine.effective_long_side is capped at 1600."""
    perf = OCRPerfSettings(device="cpu", ocr_max_long_side=2400)
    engine = OCREngine(perf)
    assert engine.effective_long_side == 1600


def test_engine_effective_long_side_cpu_below_cap(qapp) -> None:
    """When perf.ocr_max_long_side is below the CPU cap, it's used as-is."""
    perf = OCRPerfSettings(device="cpu", ocr_max_long_side=1280)
    engine = OCREngine(perf)
    assert engine.effective_long_side == 1280


def test_engine_effective_long_side_auto_no_cuda(qapp) -> None:
    """On a machine without CUDA, auto resolves to cpu, so the cap applies."""
    perf = OCRPerfSettings(device="auto", ocr_max_long_side=2400)
    engine = OCREngine(perf)
    # On the CI runner / dev mac, paddle.is_compiled_with_cuda() is False.
    # If you're on a CUDA-enabled box, this assertion will need to be either
    # skipped or split.
    assert engine.effective_long_side == 1600


def test_build_kwargs_disables_mkldnn_on_cpu(qapp) -> None:
    """paddlepaddle 3.3.x raises NotImplementedError from its PIR oneDNN
    executor on the PP-OCRv5 detection models, so CPU runs must opt out."""
    engine = OCREngine(OCRPerfSettings(device="cpu"))
    assert engine._build_kwargs(corrections=False)["enable_mkldnn"] is False


def test_build_kwargs_omits_mkldnn_on_gpu(qapp) -> None:
    """oneDNN is a CPU-only backend; the kwarg has no business on GPU runs."""
    engine = OCREngine(OCRPerfSettings(device="auto"))
    engine._resolved_device = "gpu"
    assert "enable_mkldnn" not in engine._build_kwargs(corrections=False)


class _FakeOCR:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def predict(self, image, **kwargs):  # noqa: ANN001
        self.calls.append(kwargs)
        return [
            {
                "rec_texts": ["hi"],
                "rec_scores": [0.9],
                "rec_polys": [np.array([[0, 0], [10, 0], [10, 10], [0, 10]])],
                "rec_boxes": [np.array([0, 0, 10, 10])],
            }
        ]


def _ready_engine(qapp) -> OCREngine:
    engine = OCREngine(OCRPerfSettings(device="cpu"))
    engine._preload_done = threading.Event()
    engine._preload_done.set()
    return engine


def test_process_one_normal_passes_no_correction(qapp) -> None:
    engine = _ready_engine(qapp)
    fake = _FakeOCR()
    engine._ocr = fake
    results: list = []
    engine.result_ready.connect(lambda _id, r: results.append(r))

    image = np.zeros((10, 10, 3), dtype=np.uint8)
    engine._process_one("img1", image, OCRRunOptions())

    assert len(results) == 1
    assert results[0].items[0].text == "hi"
    assert fake.calls[0]["use_textline_orientation"] is False
    assert "text_det_thresh" not in fake.calls[0]


def test_process_one_correction_uses_correction_engine(qapp) -> None:
    engine = _ready_engine(qapp)
    normal = _FakeOCR()
    correction = _FakeOCR()
    engine._ocr = normal
    engine._correction_ocr = correction

    image = np.zeros((10, 10, 3), dtype=np.uint8)
    opts = OCRRunOptions(
        use_doc_orientation_classify=True,
        use_doc_unwarping=True,
        use_textline_orientation=True,
    )
    engine._process_one("img1", image, opts)

    assert len(correction.calls) == 1
    assert len(normal.calls) == 0
    assert correction.calls[0]["use_textline_orientation"] is True


def test_process_one_filters_by_min_confidence(qapp) -> None:
    engine = _ready_engine(qapp)

    class _LowConf(_FakeOCR):
        def predict(self, image, **kwargs):  # noqa: ANN001
            self.calls.append(kwargs)
            return [
                {
                    "rec_texts": ["x"],
                    "rec_scores": [0.4],
                    "rec_polys": [np.array([[0, 0], [1, 0], [1, 1], [0, 1]])],
                    "rec_boxes": [np.array([0, 0, 1, 1])],
                }
            ]

    engine._ocr = _LowConf()
    results: list = []
    engine.result_ready.connect(lambda _id, r: results.append(r))

    engine._process_one("img1", np.zeros((4, 4, 3), dtype=np.uint8), OCRRunOptions(min_confidence=0.5))
    assert results[0].items == []


def test_process_one_passes_detection_thresholds(qapp) -> None:
    engine = _ready_engine(qapp)
    fake = _FakeOCR()
    engine._ocr = fake
    opts = OCRRunOptions(text_det_thresh=0.1, text_det_box_thresh=0.3, text_det_unclip_ratio=2.0)
    engine._process_one("img1", np.zeros((4, 4, 3), dtype=np.uint8), opts)
    assert fake.calls[0]["text_det_thresh"] == 0.1
    assert fake.calls[0]["text_det_box_thresh"] == 0.3
    assert fake.calls[0]["text_det_unclip_ratio"] == 2.0


def test_get_correction_ocr_builds_lazily_and_caches(qapp) -> None:
    engine = _ready_engine(qapp)
    built: list[bool] = []

    def fake_build(*, corrections: bool) -> _FakeOCR:
        built.append(corrections)
        return _FakeOCR()

    engine._build_ocr = fake_build  # type: ignore[method-assign]
    first = engine._get_correction_ocr()
    second = engine._get_correction_ocr()
    assert first is second  # cached, not rebuilt
    assert built == [True]  # built once, with corrections enabled


def test_run_supersedes_pending_for_same_image(qapp) -> None:
    """Re-running for an image_id with a pending queue entry replaces it,
    preserving pending entries for other image_ids."""
    engine = OCREngine(OCRPerfSettings(device="cpu"))
    engine._start_worker = lambda: None  # type: ignore[method-assign]
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    b = np.ones((4, 4, 3), dtype=np.uint8) * 128
    c = np.full((4, 4, 3), 64, dtype=np.uint8)

    engine.run("img1", a)
    engine.run("img2", c)
    engine.run("img1", b)  # supersedes the first img1 entry

    queue = list(engine._queue)
    ids = [q[0] for q in queue]
    # Order: img2 was added before the supersede; the new img1 entry appends
    # at the tail (preserves fairness — other images don't get bumped).
    assert ids == ["img2", "img1"]
    img1_entry = next(q for q in queue if q[0] == "img1")
    assert img1_entry[1] is b


def test_run_no_op_when_no_pending_entry(qapp) -> None:
    """A single run with no pre-existing pending entry still leaves exactly
    one queue entry (the no-op path of the supersede rebuild)."""
    engine = OCREngine(OCRPerfSettings(device="cpu"))
    engine._start_worker = lambda: None  # type: ignore[method-assign]
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    engine.run("img1", a)
    queue = list(engine._queue)
    assert len(queue) == 1
    assert queue[0][0] == "img1"
    assert queue[0][1] is a


def test_resolve_models_ch_mobile(qapp) -> None:
    engine = OCREngine(OCRPerfSettings(model_variant="mobile", device="cpu"), language="ch")
    assert engine._resolve_models("ch") == ("PP-OCRv5_mobile_det", "PP-OCRv5_mobile_rec")


def test_resolve_models_ch_server(qapp) -> None:
    engine = OCREngine(OCRPerfSettings(model_variant="server", device="cpu"), language="ch")
    assert engine._resolve_models("ch") == ("PP-OCRv5_server_det", "PP-OCRv5_server_rec")


def test_resolve_models_japan_server_uses_unified_rec(qapp) -> None:
    engine = OCREngine(OCRPerfSettings(model_variant="server", device="cpu"))
    assert engine._resolve_models("japan") == ("PP-OCRv5_server_det", "PP-OCRv5_server_rec")


def test_resolve_models_per_language_rec(qapp) -> None:
    engine = OCREngine(OCRPerfSettings(model_variant="mobile", device="cpu"))
    assert engine._resolve_models("en") == ("PP-OCRv5_mobile_det", "en_PP-OCRv5_mobile_rec")
    assert engine._resolve_models("korean") == ("PP-OCRv5_mobile_det", "korean_PP-OCRv5_mobile_rec")
    assert engine._resolve_models("fr") == ("PP-OCRv5_mobile_det", "latin_PP-OCRv5_mobile_rec")
    assert engine._resolve_models("de") == ("PP-OCRv5_mobile_det", "latin_PP-OCRv5_mobile_rec")
    assert engine._resolve_models("es") == ("PP-OCRv5_mobile_det", "latin_PP-OCRv5_mobile_rec")
    assert engine._resolve_models("ru") == ("PP-OCRv5_mobile_det", "eslav_PP-OCRv5_mobile_rec")
    assert engine._resolve_models("ar") == ("PP-OCRv5_mobile_det", "arabic_PP-OCRv5_mobile_rec")


def test_build_kwargs_shape(qapp) -> None:
    engine = OCREngine(OCRPerfSettings(model_variant="mobile", device="cpu", paddle_cpu_threads=3), language="fr")
    kw = engine._build_kwargs(corrections=False)
    assert kw["text_detection_model_name"] == "PP-OCRv5_mobile_det"
    assert kw["text_recognition_model_name"] == "latin_PP-OCRv5_mobile_rec"
    assert kw["device"] == "cpu"
    assert kw["cpu_threads"] == 3
    assert kw["use_textline_orientation"] is False


def test_set_language_change_triggers_rebuild(qapp) -> None:
    engine = _ready_engine(qapp)
    engine._built_language = "ch"
    engine._ocr = _FakeOCR()  # stale model for the old language
    built_langs: list[str] = []

    def fake_build(*, corrections: bool) -> _FakeOCR:
        built_langs.append(engine._language)
        return _FakeOCR()

    engine._build_ocr = fake_build  # type: ignore[method-assign]
    engine.set_language("en")
    engine._process_one("img1", np.zeros((4, 4, 3), dtype=np.uint8), OCRRunOptions())
    assert built_langs == ["en"]  # rebuilt for the new language


def test_set_language_same_value_no_rebuild(qapp) -> None:
    engine = _ready_engine(qapp)
    engine._built_language = "ch"
    fake = _FakeOCR()
    engine._ocr = fake

    def boom(*, corrections: bool):  # must not be called
        raise AssertionError("should not rebuild")

    engine._build_ocr = boom  # type: ignore[method-assign]
    engine.set_language("ch")  # no change
    engine._process_one("img1", np.zeros((4, 4, 3), dtype=np.uint8), OCRRunOptions())
    assert len(fake.calls) == 1  # reused the cached model
