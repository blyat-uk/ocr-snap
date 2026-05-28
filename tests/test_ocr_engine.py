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
