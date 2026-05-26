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


def _register_frozen_resource_finder(package: str = "pip._vendor.distlib") -> None:
    """Make pip's vendored distlib usable when running inside a PyInstaller bundle.

    On Windows, importing pip's install command pulls in
    ``pip._vendor.distlib.scripts``, whose module-level code pre-loads the
    bundled ``.exe`` launchers via ``distlib.resources.finder(<distlib pkg>)``.
    That registry is keyed by module-loader *type* and only knows the stdlib
    loaders, so PyInstaller's ``PyiFrozenImporter`` misses and it raises
    ``DistlibException: Unable to locate finder``. PyInstaller extracts the
    bundle to a real directory (``sys._MEIPASS``), so the plain filesystem
    ``ResourceFinder`` works once we register it for the frozen loader's type.
    Importing distlib's ``resources`` module is safe — it does not import the
    broken ``scripts`` module.
    """
    import importlib

    from pip._vendor.distlib.resources import ResourceFinder, register_finder

    module = importlib.import_module(package)
    register_finder(module.__loader__, ResourceFinder)


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
        if getattr(sys, "frozen", False):
            # Bundled pip can't read its own vendored distlib resources under
            # PyInstaller until we teach distlib about the frozen loader.
            _register_frozen_resource_finder()
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
