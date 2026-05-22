from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "set_flavor.py"
BUILD_INFO = REPO_ROOT / "src" / "ocr_snap" / "_build_info.py"


@pytest.fixture
def restore_build_info():
    saved = BUILD_INFO.read_text()
    yield
    BUILD_INFO.write_text(saved)


@pytest.mark.parametrize("flavor,expected", [
    ("linux-cpu", "paddlepaddle"),
    ("linux-gpu", "paddlepaddle-gpu"),
    ("windows-cpu", "paddlepaddle"),
    ("windows-gpu", "paddlepaddle-gpu"),
    ("macos-cpu", "paddlepaddle"),
])
def test_set_flavor_writes_expected_package(flavor: str, expected: str, restore_build_info) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), flavor], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    content = BUILD_INFO.read_text()
    assert f'PADDLE_PACKAGE = "{expected}"' in content


def test_set_flavor_idempotent(restore_build_info) -> None:
    subprocess.run([sys.executable, str(SCRIPT), "linux-gpu"], check=True)
    first = BUILD_INFO.read_text()
    subprocess.run([sys.executable, str(SCRIPT), "linux-gpu"], check=True)
    second = BUILD_INFO.read_text()
    assert first == second


def test_set_flavor_rejects_unknown_flavor() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "bogus"], capture_output=True, text=True
    )
    assert result.returncode == 2
    assert "usage:" in result.stderr
