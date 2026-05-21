from __future__ import annotations

from ocr_snap.ocr_engine import OCREngine
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
