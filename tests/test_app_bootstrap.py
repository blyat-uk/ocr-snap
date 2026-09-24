from __future__ import annotations

from unittest.mock import patch

from ocr_snap.app import _paddle_importable, _run_first_run_install


def test_paddle_importable_reflects_find_spec() -> None:
    """_paddle_importable is a thin wrapper over importlib's spec lookup."""
    with patch("importlib.util.find_spec", return_value=None) as m:
        assert _paddle_importable() is False
        m.assert_called_once_with("paddle")
    with patch("importlib.util.find_spec", return_value=object()):
        assert _paddle_importable() is True


def test_first_run_install_skipped_when_paddle_importable() -> None:
    """A source checkout with the ocr/ocr-gpu extra already has paddle on
    sys.path. Prepending the runtime dir there would shadow it with the
    bootstrap's CPU-only build, so the bootstrap must not run at all."""
    with (
        patch("ocr_snap.app._paddle_importable", return_value=True),
        patch("ocr_snap.app.ensure_paddle_installed") as ensure,
        patch("ocr_snap.app.is_paddle_installed") as is_installed,
    ):
        assert _run_first_run_install() is True

    ensure.assert_not_called()
    is_installed.assert_not_called()


def test_first_run_install_prepends_when_paddle_missing() -> None:
    """The frozen binary ships without paddle, so the runtime dir still gets
    prepended on every launch after the first-run install."""
    with (
        patch("ocr_snap.app._paddle_importable", return_value=False),
        patch("ocr_snap.app.is_paddle_installed", return_value=True),
        patch("ocr_snap.app.ensure_paddle_installed") as ensure,
        patch("ocr_snap.app.default_runtime_dir", return_value="/runtime"),
    ):
        assert _run_first_run_install() is True

    ensure.assert_called_once()
    assert ensure.call_args.args[0] == "/runtime"
