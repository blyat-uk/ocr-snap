"""First-run bootstrap: install paddle/paddleocr into a user-data dir.

The PyInstaller binary ships without paddle. On first launch we pip-install
paddlepaddle (or paddlepaddle-gpu) and paddleocr into a user-data directory,
then prepend that directory to ``sys.path`` so the existing lazy imports in
``ocr_engine.py`` resolve against the runtime install.

The CPU/GPU flavor is determined at build time by
``_build_info.PADDLE_PACKAGE``, which ``tools/set_flavor.py`` rewrites in CI.
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

PADDLEOCR_SPEC = "paddleocr>=3.0"


def is_paddle_installed(target_dir: Path) -> bool:
    return (target_dir / "paddle" / "__init__.py").exists()


def ensure_paddle_installed(
    target_dir: Path,
    paddle_package: str,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Install paddle into ``target_dir`` if missing, then prepend it to sys.path.

    Raises ``RuntimeError`` if pip returns a non-zero exit code.
    """
    if not is_paddle_installed(target_dir):
        target_dir.mkdir(parents=True, exist_ok=True)
        if on_progress is not None:
            on_progress(
                f"Installing {paddle_package} (this can take several minutes)..."
            )
        from pip._internal.cli.main import main as pip_main
        rc = pip_main(
            [
                "install",
                "--target", str(target_dir),
                "--no-cache-dir",
                paddle_package,
                PADDLEOCR_SPEC,
            ]
        )
        if rc != 0:
            raise RuntimeError(f"pip install failed with exit code {rc}")
        if not is_paddle_installed(target_dir):
            raise RuntimeError(
                f"pip reported success but paddle is not importable from {target_dir}"
            )

    if str(target_dir) not in sys.path:
        sys.path.insert(0, str(target_dir))


def default_runtime_dir() -> Path:
    from platformdirs import user_data_dir
    return Path(user_data_dir("ocr-snap")) / "runtime"
