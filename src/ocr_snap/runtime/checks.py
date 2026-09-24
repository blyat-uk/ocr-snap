"""The installer's checks, each run in a child process of the bundled interpreter:

    python -s -E -X utf8 -m ocr_snap.runtime.checks verify   --engine DIR --device gpu|cpu
    python -s -E -X utf8 -m ocr_snap.runtime.checks prefetch --engine DIR --device gpu|cpu

(cwd = the source root, so `-m` finds the package under -E.)

- `verify` imports paddle from the engine dir and runs a small conv2d on
  the device. For "gpu" it first requires a CUDA-compiled paddle and at
  least one CUDA device, then `set_device("gpu:0")`.
- `prefetch` builds the OCR engine once, exactly as the app does
  (`OCREngine` with the user's saved model and language), so paddlex
  downloads the models, and runs one prediction on a blank image. It
  reports whether the models are on disk afterwards, so the parent can tell
  a download failure from a device failure.

A child in its own process means a crash (a CUDA library that does not
load, a segfault in a driver) costs the check, not the app. The last line
of output is `RESULT <json>`; the exit code is 0 on success.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

RESULT_PREFIX = "RESULT "
CONV_EXPECTED = 4 * 14 * 14 * 27.0         # ones(1,3,16,16) * ones(4,3,3,3), no padding


def models_cache_dir() -> Path:
    """Where paddlex keeps downloaded models."""
    base = os.environ.get("PADDLE_PDX_CACHE_HOME", "").strip()
    return (Path(base) if base else Path.home() / ".paddlex") / "official_models"


def models_present(names: tuple[str, ...], cache: Path | None = None) -> bool:
    cache = models_cache_dir() if cache is None else cache
    return all((cache / name / "inference.yml").is_file() for name in names)


def verify(device: str) -> dict:
    import paddle

    from ocr_snap.runtime.engine import PADDLE_VERSION

    info: dict = {"paddle": paddle.__version__, "compiled_with_cuda": bool(paddle.device.is_compiled_with_cuda())}
    if not str(paddle.__version__).startswith(PADDLE_VERSION):
        raise RuntimeError(f"paddle {paddle.__version__} is installed, expected {PADDLE_VERSION}")
    if device == "gpu":
        if not info["compiled_with_cuda"]:
            raise RuntimeError("this paddle build has no CUDA support")
        count = paddle.device.cuda.device_count()
        info["device_count"] = count
        if count < 1:
            raise RuntimeError("paddle sees no CUDA device")
        paddle.set_device("gpu:0")
        info["device_name"] = paddle.device.cuda.get_device_name(0)
    else:
        paddle.set_device("cpu")
    x = paddle.ones([1, 3, 16, 16], dtype="float32")
    w = paddle.ones([4, 3, 3, 3], dtype="float32")
    value = float(paddle.nn.functional.conv2d(x, w).sum())
    info["conv2d"] = value
    if value != CONV_EXPECTED:
        raise RuntimeError(f"conv2d returned {value}, expected {CONV_EXPECTED}")
    info["device"] = str(paddle.get_device())
    return info


def app_engine(device: str):
    """An `OCREngine` as the app builds it from the saved settings, pinned
    to `device` ("gpu" means the settings' "auto", which picks the GPU)."""
    from dataclasses import replace

    from ocr_snap.config import load_app_settings
    from ocr_snap.ocr_engine import OCREngine

    settings = load_app_settings()
    perf = replace(settings.perf, device="auto" if device == "gpu" else "cpu")
    return OCREngine(perf, settings.ocr_language)


def prefetch(device: str) -> dict:
    import numpy as np

    engine = app_engine(device)
    if engine.device != device:
        raise RuntimeError(f"asked for {device} but paddle would run on {engine.device}")
    blank = np.zeros((64, 320, 3), dtype=np.uint8)
    list(engine.load_models().predict(blank))  # type: ignore[attr-defined]
    return {"device": engine.device, "models": list(engine.model_names())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ocr_snap.runtime.checks")
    parser.add_argument("check", choices=("verify", "prefetch"))
    parser.add_argument("--engine", required=True, help="the engine dir to activate")
    parser.add_argument("--device", choices=("gpu", "cpu"), required=True)
    args = parser.parse_args(argv)

    from ocr_snap.runtime.engine import activate

    activate(Path(args.engine))
    result: dict = {"check": args.check, "device": args.device, "ok": False}
    code = 1
    try:
        result.update(verify(args.device) if args.check == "verify" else prefetch(args.device))
        result["ok"] = True
        code = 0
    except BaseException as exc:          # noqa: BLE001 - the parent wants every failure as a result
        traceback.print_exc()
        result["error"] = f"{type(exc).__name__}: {exc}"
    if args.check == "prefetch":
        try:
            names = app_engine("cpu").model_names()
            result["models"] = models_present(names)
        except Exception:                 # noqa: BLE001 - no settings/paddle: the models are not there
            result["models"] = False
    sys.stdout.flush()
    print(RESULT_PREFIX + json.dumps(result), flush=True)
    return code


def parse_result(lines: list[str]) -> dict | None:
    for line in reversed(lines):
        if line.startswith(RESULT_PREFIX):
            try:
                value = json.loads(line[len(RESULT_PREFIX):])
            except ValueError:
                return None
            return value if isinstance(value, dict) else None
    return None


if __name__ == "__main__":
    sys.exit(main())
