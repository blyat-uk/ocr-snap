from __future__ import annotations


def test_theme_module_imports() -> None:
    """Smoke test that the module file is parseable."""
    import ocr_snap.theme  # noqa: F401
