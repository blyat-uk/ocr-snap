"""Rewrite src/ocr_snap/_build_info.py for the requested build flavor.

Usage:
    python tools/set_flavor.py {linux-cpu,linux-gpu,windows-cpu,windows-gpu,macos-cpu}

Used in CI by .github/workflows/release.yml before invoking PyInstaller.
Idempotent: running twice with the same flavor produces the same file.
"""
from __future__ import annotations

import sys
from pathlib import Path

FLAVOR_TO_PACKAGE = {
    "linux-cpu": "paddlepaddle",
    "linux-gpu": "paddlepaddle-gpu",
    "windows-cpu": "paddlepaddle",
    "windows-gpu": "paddlepaddle-gpu",
    "macos-cpu": "paddlepaddle",
}

BUILD_INFO_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "ocr_snap" / "_build_info.py"
)


def render(package: str) -> str:
    return (
        "# Rewritten by tools/set_flavor.py in CI before each PyInstaller build.\n"
        f'PADDLE_PACKAGE = "{package}"\n'
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in FLAVOR_TO_PACKAGE:
        print(
            f"usage: set_flavor.py {{{','.join(FLAVOR_TO_PACKAGE)}}}",
            file=sys.stderr,
        )
        return 2
    package = FLAVOR_TO_PACKAGE[argv[1]]
    BUILD_INFO_PATH.write_text(render(package))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
