from __future__ import annotations

import pytest

import ocr_snap.translator as tr


class _FakeResp:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"translations": [{"text": "hello", "detected_source_language": "ZH"}]}


@pytest.fixture
def capture_post(monkeypatch: pytest.MonkeyPatch) -> dict:
    captured: dict = {}

    def fake_post(url, data=None, headers=None, timeout=None):  # noqa: ANN001
        captured["url"] = url
        captured["data"] = data
        return _FakeResp()

    monkeypatch.setattr(tr.requests, "post", fake_post)
    return captured


def test_run_worker_includes_source_lang(capture_post: dict) -> None:
    engine = tr.TranslationEngine("key:fx")
    engine._run_worker("img", [(0, "你好")], "ZH")
    assert ("source_lang", "ZH") in capture_post["data"]
    assert ("target_lang", "EN") in capture_post["data"]
    assert ("text", "你好") in capture_post["data"]


def test_run_worker_omits_source_lang_when_none(capture_post: dict) -> None:
    engine = tr.TranslationEngine("key:fx")
    engine._run_worker("img", [(0, "hola")], None)
    assert not any(k == "source_lang" for k, _ in capture_post["data"])
    assert ("target_lang", "EN") in capture_post["data"]


def test_translate_returns_false_without_key() -> None:
    engine = tr.TranslationEngine("")
    assert engine.translate("img", [(0, "x")], source_lang="ZH") is False
