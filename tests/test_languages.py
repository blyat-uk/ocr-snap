from __future__ import annotations

from ocr_snap import languages as L


def test_curated_set_has_ten_languages() -> None:
    assert len(L.LANGUAGES) == 10


def test_languages_are_sorted_alphabetically_by_label() -> None:
    labels = [opt.label for opt in L.LANGUAGES]
    assert labels == sorted(labels)


def test_default_language_is_chinese_simplified() -> None:
    assert L.DEFAULT_LANGUAGE == "ch"
    assert L.option_for("ch").label == "Chinese (Simplified)"


def test_option_for_known_code() -> None:
    opt = L.option_for("ru")
    assert opt.paddle_code == "ru"
    assert opt.label == "Russian"
    assert opt.deepl_source == "RU"


def test_option_for_unknown_code_falls_back_to_default() -> None:
    assert L.option_for("klingon").paddle_code == "ch"


def test_deepl_source_for_maps_codes() -> None:
    assert L.deepl_source_for("ch") == "ZH"
    assert L.deepl_source_for("chinese_cht") == "ZH"
    assert L.deepl_source_for("en") == "EN"
    assert L.deepl_source_for("japan") == "JA"
    assert L.deepl_source_for("ar") == "AR"


def test_is_supported() -> None:
    assert L.is_supported("fr") is True
    assert L.is_supported("nope") is False
