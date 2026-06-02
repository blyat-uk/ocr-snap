from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageOption:
    """One selectable OCR language.

    ``paddle_code`` is the PaddleOCR ``lang`` value (also our internal id).
    ``deepl_source`` is the DeepL source-language code, or ``None`` when DeepL
    has no equivalent (translation falls back to auto-detect).
    """

    label: str
    paddle_code: str
    deepl_source: str | None


LANGUAGES: list[LanguageOption] = [
    LanguageOption("Chinese (Simplified)", "ch", "ZH"),
    LanguageOption("Chinese (Traditional)", "chinese_cht", "ZH"),
    LanguageOption("English", "en", "EN"),
    LanguageOption("Japanese", "japan", "JA"),
    LanguageOption("Korean", "korean", "KO"),
    LanguageOption("French", "fr", "FR"),
    LanguageOption("German", "de", "DE"),
    LanguageOption("Spanish", "es", "ES"),
    LanguageOption("Russian", "ru", "RU"),
    LanguageOption("Arabic", "ar", "AR"),
]

DEFAULT_LANGUAGE = "ch"

_BY_CODE: dict[str, LanguageOption] = {opt.paddle_code: opt for opt in LANGUAGES}


def option_for(code: str) -> LanguageOption:
    """Return the option for ``code``, falling back to the default language."""
    return _BY_CODE.get(code, _BY_CODE[DEFAULT_LANGUAGE])


def is_supported(code: str) -> bool:
    return code in _BY_CODE


def deepl_source_for(code: str) -> str | None:
    """DeepL source-language code for an OCR language, or ``None`` to auto-detect."""
    return option_for(code).deepl_source
