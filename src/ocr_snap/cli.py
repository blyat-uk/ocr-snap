"""The headless command-line modes of `python -m ocr_snap` (CI hooks).

`--self-test`
    Imports every module of the `ocr_snap` package, checks that the
    interpreter has what the app and the first-run installer need (ssl for
    downloads, pip for the engine install) and prints one JSON report
    (`"ok"` plus the details). Exit 0 when everything passed, else 1. The
    OCR engine is reported but not required.

`--install-engine {auto,cpu,gpu}`
    Installs the OCR engine into the data dir (bundles only). Progress as
    `[step] ...`, `[progress] <done> of <total> bytes`, `[notice] ...` and
    `  | <pip output>` lines; the last line is `RESULT <json>`. Exit 0
    installed; 1 failed; 2 not a bundle; 3 `gpu` was asked for but no GPU
    build fits this machine, or the GPU build failed and CPU was installed;
    130 interrupted (Ctrl+C).

`--ocr-smoke`
    Builds the OCR engine the way the window does (saved settings, resolved
    device), OCRs a rendered line of text and prints `RESULT <json>`. Exit 0
    when any text was recognised, else 1.

Output goes to stdout (the log file under pythonw).
"""
from __future__ import annotations

import importlib
import json
import os
import pkgutil
import platform
import subprocess
import sys
import threading
import time
import traceback

from ocr_snap.bootstrap import Boot
from ocr_snap.runtime.proc import TEXT_ENCODING, hidden_child
from ocr_snap.version import __version__

PACKAGE = "ocr_snap"
# Imported for their side effects or run as scripts, never by the app.
SKIP_MODULES = ("ocr_snap.__main__",)
STDLIB_NEEDED = ("ssl", "sqlite3", "ctypes", "zoneinfo", "lzma", "bz2")
PIP_TIMEOUT = 120
SMOKE_TEXT = "OCR Snap 12345"
EXIT_OK, EXIT_FAIL, EXIT_NOT_BUNDLE, EXIT_NO_GPU, EXIT_INTERRUPTED = 0, 1, 2, 3, 130
_smoke_app = None                       # the QGuiApplication --ocr-smoke renders with, when none exists


def _emit(line: str) -> None:
    print(line, flush=True)


# --------------------------------------------------------------------------
# --self-test
# --------------------------------------------------------------------------

def import_all(package_name: str = PACKAGE) -> tuple[list[str], dict[str, str]]:
    """Import every module of `package_name`; (imported, {module: error})."""
    imported: list[str] = []
    failed: dict[str, str] = {}
    package = importlib.import_module(package_name)
    imported.append(package_name)
    for info in pkgutil.walk_packages(package.__path__, prefix=f"{package_name}."):
        if info.name in SKIP_MODULES:
            continue
        try:
            importlib.import_module(info.name)
            imported.append(info.name)
        except Exception as exc:                            # noqa: BLE001 - reported, not raised
            failed[info.name] = f"{type(exc).__name__}: {exc}"
    return imported, failed


def check_stdlib(names: tuple[str, ...] = STDLIB_NEEDED) -> dict[str, str]:
    """The stdlib modules the downloads and paddle's dependencies need;
    {module: error} for those that do not import."""
    failed = {}
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as exc:                            # noqa: BLE001
            failed[name] = f"{type(exc).__name__}: {exc}"
    return failed


def check_pip() -> dict:
    """`python -m pip --version` with the interpreter the installer uses."""
    from ocr_snap.runtime.pip import parse_pip_version, python_for_subprocess

    python = python_for_subprocess(sys.executable)
    try:
        done = subprocess.run([python, "-m", "pip", "--version"], capture_output=True, text=True,
                              timeout=PIP_TIMEOUT, check=False, **TEXT_ENCODING, **hidden_child())
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}
    version = parse_pip_version(done.stdout or "")
    return {"ok": done.returncode == 0 and bool(version), "version": ".".join(map(str, version)),
            **({} if done.returncode == 0 else {"error": (done.stderr or "").strip()[-500:]})}


def engine_report(boot: Boot) -> dict:
    from ocr_snap.runtime.engine import engine_dir

    report: dict = {"bundled": boot.bundled}
    if boot.bundled:
        report["dir"] = str(engine_dir())
        report["installed"] = boot.state is not None
        if boot.state is not None:
            report.update(variant=boot.state.variant, models_ready=boot.state.models_ready,
                          fallback_reason=boot.state.fallback_reason)
    return report


def self_test(boot: Boot) -> int:
    imported, failed = import_all()
    stdlib_failed = check_stdlib()
    pip_report = check_pip()
    ok = not failed and not stdlib_failed and not boot.bundle_error and pip_report["ok"]
    report = {
        "ok": ok,
        "version": __version__,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "bundle": None if boot.bundle is None else {
            "root": str(boot.bundle.root), "version": boot.bundle.version,
            "os": boot.bundle.os, "arch": boot.bundle.arch},
        "bundle_error": boot.bundle_error,
        "imports": {"count": len(imported), "failed": failed},
        "stdlib": {"failed": stdlib_failed},
        "pip": pip_report,
        "engine": engine_report(boot),
    }
    _emit(json.dumps(report, indent=2, ensure_ascii=False))
    return EXIT_OK if ok else EXIT_FAIL


# --------------------------------------------------------------------------
# --install-engine
# --------------------------------------------------------------------------

class _Printer:
    """InstallEvent -> lines; byte progress at most once a second."""

    def __init__(self) -> None:
        self._last = 0.0

    def __call__(self, event) -> None:
        if event.kind == "progress":
            now = time.monotonic()
            if now - self._last < 1.0 and event.done_bytes < event.total_bytes:
                return
            self._last = now
            _emit(f"[progress] {event.done_bytes} of {event.total_bytes} bytes")
        elif event.kind == "step":
            _emit(f"[step] {event.text}")
        elif event.kind == "notice":
            _emit(f"[notice] {event.text}")
        else:
            _emit(f"  | {event.text}")


def install_engine(boot: Boot, request: str) -> int:
    from ocr_snap.runtime import resolve_request
    from ocr_snap.runtime.gpu import CPU, describe, probe_gpus, variant_label
    from ocr_snap.runtime.install import EngineInstaller, InstallContext

    if boot.bundle is None:
        _emit("--install-engine needs a portable bundle ($OCR_SNAP_BUNDLE); in developer mode paddle "
              "comes from your environment." + (f" ({boot.bundle_error})" if boot.bundle_error else ""))
        return EXIT_NOT_BUNDLE
    probe = probe_gpus(boot.bundle.os)
    variant, choice = resolve_request(request, boot.bundle, probe)
    _emit(f"[hardware] {describe(probe)}")
    _emit(f"[choice] {variant_label(choice.variant)}: {choice.reason}")
    if request == "gpu" and variant == CPU:
        _emit(f"RESULT {json.dumps({'ok': False, 'error': 'no GPU build fits: ' + choice.reason})}")
        return EXIT_NO_GPU
    _emit(f"[install] {variant_label(variant)}")
    installer = EngineInstaller(InstallContext.for_bundle(boot.bundle), emit=_Printer())
    cancel = threading.Event()
    box: dict = {}

    def work() -> None:
        try:
            box["result"] = installer.install(variant, choice.gpu if variant != CPU else None, cancel)
        except BaseException as exc:                         # noqa: BLE001
            box["error"] = "".join(traceback.format_exception(exc))

    thread = threading.Thread(target=work, name="engine-install")
    thread.start()
    interrupted = False
    while thread.is_alive():
        try:
            thread.join(0.5)
        except KeyboardInterrupt:
            interrupted = True
            _emit("[step] Cancelling")
            cancel.set()
    if "error" in box:
        _emit(box["error"])
        _emit(f"RESULT {json.dumps({'ok': False, 'error': 'installer crashed'})}")
        return EXIT_FAIL
    result = box["result"]
    summary = {"ok": result.ok, "variant": result.variant, "fell_back": result.fell_back,
               "fallback_reason": result.fallback_reason, "error": result.error, "warnings": result.warnings,
               "engine_dir": str(result.engine_dir) if result.engine_dir else None,
               "state": result.state.to_json() if result.state else None}
    _emit(f"RESULT {json.dumps(summary, ensure_ascii=False)}")
    if result.cancelled or interrupted:
        return EXIT_INTERRUPTED
    if not result.ok:
        return EXIT_FAIL
    if request == "gpu" and result.fell_back:
        return EXIT_NO_GPU
    return EXIT_OK


# --------------------------------------------------------------------------
# --ocr-smoke
# --------------------------------------------------------------------------

# System font files Pillow can draw the smoke line with when Qt has none.
FONT_FILES = (
    r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
)


def render_line(text: str = SMOKE_TEXT):
    """(RGB numpy image, the font used) -- black text on white, drawn with
    Qt, or with Pillow from a system font when Qt draws nothing."""
    import numpy as np
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

    global _smoke_app
    if QGuiApplication.instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        if sys.platform == "win32" and os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            # The offscreen platform looks for fonts in Qt's own folder, which
            # the wheel does not ship; Windows keeps them here.
            os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
        _smoke_app = QGuiApplication([sys.argv[0] if sys.argv else "ocr-snap"])
    width, height = 960, 128
    image = QImage(width, height, QImage.Format.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    font = QFont()
    font.setPixelSize(64)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    painter.drawText(image.rect(), int(Qt.AlignmentFlag.AlignCenter), text)
    painter.end()
    bits = image.constBits()
    assert bits is not None
    data = bits.asstring(image.sizeInBytes())          # a copy: the QImage's memory goes with it
    rgb = np.frombuffer(data, np.uint8).reshape(height, image.bytesPerLine())[:, :width * 3]
    rgb = np.ascontiguousarray(rgb.reshape(height, width, 3))
    if (rgb < 128).any():
        return rgb, font.family()
    return _render_with_pillow(text, width, height)


def _render_with_pillow(text: str, width: int, height: int):
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    path = next((p for p in FONT_FILES if os.path.exists(p)), None)
    if path is None:
        raise RuntimeError("no font to draw the smoke-test line with")
    font = ImageFont.truetype(path, 64)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((width - (right - left)) / 2 - left, (height - (bottom - top)) / 2 - top), text,
              font=font, fill="black")
    return np.asarray(image), os.path.basename(path)


def ocr_smoke(boot: Boot) -> int:
    if boot.bundled and boot.state is None:
        _emit(f"RESULT {json.dumps({'ok': False, 'error': 'no OCR engine is installed (--install-engine)'})}")
        return EXIT_FAIL
    started = time.monotonic()
    try:
        image, family = render_line()
        from ocr_snap.config import load_app_settings
        from ocr_snap.ocr_engine import OCREngine, OCRRunOptions

        settings = load_app_settings()
        engine = OCREngine(settings.perf, settings.ocr_language)
        texts: list[str] = []
        scores: list[float] = []
        for page in engine.load_models().predict(image, **OCRRunOptions().predict_kwargs()):  # type: ignore[attr-defined]
            texts.extend(str(text) for text in page["rec_texts"])
            scores.extend(float(score) for score in page["rec_scores"])
    except Exception as exc:                                # noqa: BLE001
        traceback.print_exc()
        _emit(f"RESULT {json.dumps({'ok': False, 'error': f'{type(exc).__name__}: {exc}'})}")
        return EXIT_FAIL
    recognized = " ".join(texts).strip()
    report = {"ok": bool(recognized), "device": engine.device, "language": settings.ocr_language,
              "models": list(engine.model_names()), "font": family, "expected": SMOKE_TEXT,
              "recognized": recognized, "scores": [round(score, 4) for score in scores],
              "exact": recognized.replace(" ", "").lower() == SMOKE_TEXT.replace(" ", "").lower(),
              "seconds": round(time.monotonic() - started, 1)}
    _emit(f"RESULT {json.dumps(report, ensure_ascii=False)}")
    return EXIT_OK if recognized else EXIT_FAIL
