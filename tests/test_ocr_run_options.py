from __future__ import annotations

import math

from ocr_snap.models import Adjustments
from ocr_snap.ocr_engine import OCRRunOptions


def test_default_options_no_correction_no_thresholds() -> None:
    opt = OCRRunOptions()
    assert opt.uses_correction() is False
    kw = opt.predict_kwargs()
    assert kw["use_textline_orientation"] is False
    assert "text_det_thresh" not in kw
    assert "text_det_box_thresh" not in kw
    assert "text_det_unclip_ratio" not in kw


def test_from_adjustments_identity() -> None:
    opt = OCRRunOptions.from_adjustments(Adjustments(), min_confidence=0.5)
    assert opt.min_confidence == 0.5
    assert opt.uses_correction() is False
    assert opt.text_det_thresh is None


def test_from_adjustments_smart_fix_sets_all_flags() -> None:
    opt = OCRRunOptions.from_adjustments(Adjustments(smart_fix=True), min_confidence=0.4)
    assert opt.use_doc_orientation_classify is True
    assert opt.use_doc_unwarping is True
    assert opt.use_textline_orientation is True
    assert opt.uses_correction() is True


def test_from_adjustments_sensitivity_full() -> None:
    opt = OCRRunOptions.from_adjustments(Adjustments(det_sensitivity=1.0), min_confidence=0.5)
    assert math.isclose(opt.text_det_thresh, 0.1)
    assert math.isclose(opt.text_det_box_thresh, 0.3)
    assert math.isclose(opt.text_det_unclip_ratio, 2.0)


def test_from_adjustments_sensitivity_half() -> None:
    opt = OCRRunOptions.from_adjustments(Adjustments(det_sensitivity=0.5), min_confidence=0.5)
    assert math.isclose(opt.text_det_thresh, 0.2)
    assert math.isclose(opt.text_det_box_thresh, 0.45)
    assert math.isclose(opt.text_det_unclip_ratio, 1.75)


def test_predict_kwargs_includes_thresholds_when_set() -> None:
    opt = OCRRunOptions.from_adjustments(Adjustments(det_sensitivity=1.0), min_confidence=0.5)
    kw = opt.predict_kwargs()
    assert math.isclose(kw["text_det_thresh"], 0.1)
    assert math.isclose(kw["text_det_box_thresh"], 0.3)
    assert math.isclose(kw["text_det_unclip_ratio"], 2.0)
