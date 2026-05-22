from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from ocr_snap.runtime_bootstrap import (
    PADDLEOCR_SPEC,
    ensure_paddle_installed,
    is_paddle_installed,
)


@pytest.fixture
def restore_sys_path():
    saved = list(sys.path)
    yield
    sys.path[:] = saved


def _fake_pip_that_creates_paddle(target: Path):
    def _inner(args):
        (target / "paddle").mkdir(parents=True, exist_ok=True)
        (target / "paddle" / "__init__.py").write_text("")
        return 0
    return _inner


def test_is_paddle_installed_false_for_empty_dir(tmp_path: Path) -> None:
    assert not is_paddle_installed(tmp_path)


def test_is_paddle_installed_true_when_package_exists(tmp_path: Path) -> None:
    (tmp_path / "paddle").mkdir()
    (tmp_path / "paddle" / "__init__.py").write_text("")
    assert is_paddle_installed(tmp_path)


def test_ensure_installs_when_missing(tmp_path: Path, restore_sys_path) -> None:
    messages: list[str] = []
    with patch(
        "pip._internal.cli.main.main",
        side_effect=_fake_pip_that_creates_paddle(tmp_path),
    ) as m:
        ensure_paddle_installed(tmp_path, "paddlepaddle", on_progress=messages.append)

    m.assert_called_once()
    args = m.call_args.args[0]
    assert "install" in args
    assert "--target" in args
    assert str(tmp_path) in args
    assert "paddlepaddle" in args
    assert PADDLEOCR_SPEC in args
    assert sys.path[0] == str(tmp_path)
    assert messages, "expected at least one progress message"


def test_ensure_skips_pip_when_paddle_present(tmp_path: Path, restore_sys_path) -> None:
    (tmp_path / "paddle").mkdir()
    (tmp_path / "paddle" / "__init__.py").write_text("")
    with patch("pip._internal.cli.main.main") as m:
        ensure_paddle_installed(tmp_path, "paddlepaddle")
    m.assert_not_called()
    assert sys.path[0] == str(tmp_path)


def test_ensure_uses_gpu_package_string(tmp_path: Path, restore_sys_path) -> None:
    with patch(
        "pip._internal.cli.main.main",
        side_effect=_fake_pip_that_creates_paddle(tmp_path),
    ) as m:
        ensure_paddle_installed(tmp_path, "paddlepaddle-gpu")

    args = m.call_args.args[0]
    assert "paddlepaddle-gpu" in args
    # The CPU package name must not appear as a standalone arg.
    assert "paddlepaddle" not in [a for a in args if a == "paddlepaddle"]


def test_ensure_raises_on_pip_failure(tmp_path: Path, restore_sys_path) -> None:
    with patch("pip._internal.cli.main.main", return_value=1):
        with pytest.raises(RuntimeError, match="exit code 1"):
            ensure_paddle_installed(tmp_path, "paddlepaddle")


def test_ensure_does_not_duplicate_sys_path_entry(tmp_path: Path, restore_sys_path) -> None:
    (tmp_path / "paddle").mkdir()
    (tmp_path / "paddle" / "__init__.py").write_text("")
    ensure_paddle_installed(tmp_path, "paddlepaddle")
    ensure_paddle_installed(tmp_path, "paddlepaddle")
    assert sys.path.count(str(tmp_path)) == 1
