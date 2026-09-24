"""Startup: stdout/stderr redirection without a console, the bootstrap's
engine activation, the CLI flags, and the engine setup dialog."""
from __future__ import annotations

import json
import os
import site
import subprocess
import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from ocr_snap.runtime import engine
from ocr_snap.runtime.engine import EngineState

SRC = Path(__file__).resolve().parent.parent / "src"


def _child(args: list[str], env: dict | None = None, **kwargs) -> subprocess.CompletedProcess:
    full = {k: v for k, v in os.environ.items() if k != "OCR_SNAP_BUNDLE"}
    full.update(env or {})
    return subprocess.run([sys.executable, *args], cwd=SRC, capture_output=True, text=True, env=full,
                          timeout=300, check=False, **kwargs)


# --------------------------------------------------------------------------
# ocr_snap.runtime.logfile (in child processes: it dup2()s fds 1 and 2)
# --------------------------------------------------------------------------

PYTHONW = """
import os, sys
os.close(1); os.close(2)
sys.stdout = None; sys.stderr = None          # what pythonw.exe gives a program
from ocr_snap.runtime.logfile import needs_redirect, redirect_if_needed
assert needs_redirect()
path = redirect_if_needed(__import__('pathlib').Path(sys.argv[1]))
print('python-level stdout')
sys.stderr.write('python-level stderr\\n')
os.write(1, b'fd 1\\n'); os.write(2, b'fd 2\\n')
print('redirected', path is not None)
"""


def test_no_console_output_goes_to_the_log_file(tmp_path):
    log = tmp_path / "logs" / "ocr-snap.log"
    log.parent.mkdir()
    log.write_text("previous run\n")
    done = _child(["-c", PYTHONW, str(log)])
    assert done.returncode == 0, done.stderr
    text = log.read_text()
    for expected in ("python-level stdout", "python-level stderr", "fd 1", "fd 2", "redirected True"):
        assert expected in text
    assert (tmp_path / "logs" / "ocr-snap.log.1").read_text() == "previous run\n"


def test_devnull_output_counts_as_nowhere_only_when_asked():
    code = ("from ocr_snap.runtime.logfile import needs_redirect; "
            "import sys; sys.exit(10 * needs_redirect() + needs_redirect(discard_devnull=True))")
    done = subprocess.run([sys.executable, "-c", code], cwd=SRC, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=60, check=False)
    assert done.returncode == (0 if sys.platform == "win32" else 1)
    assert _child(["-c", code]).returncode == 0          # pipes are real output


# --------------------------------------------------------------------------
# ocr_snap.bootstrap
# --------------------------------------------------------------------------

@pytest.fixture
def bundle_env(tmp_path, monkeypatch):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "bundle.json").write_text(json.dumps({"version": "5.1.0", "os": "linux", "arch": "x86_64"}))
    (root / "constraints.txt").write_text("numpy==2.4.2\n")
    data = tmp_path / "data"
    monkeypatch.setenv("OCR_SNAP_BUNDLE", str(root))
    monkeypatch.setenv("OCR_SNAP_DATA_DIR", str(data))
    saved_path = list(sys.path)
    saved_site = (site.ENABLE_USER_SITE, site.USER_BASE, site.USER_SITE)
    saved_base = os.environ.get("PYTHONUSERBASE")
    yield root, data
    sys.path[:] = saved_path
    site.ENABLE_USER_SITE, site.USER_BASE, site.USER_SITE = saved_site
    if saved_base is None:
        os.environ.pop("PYTHONUSERBASE", None)
    else:
        os.environ["PYTHONUSERBASE"] = saved_base


def _install_fake_engine(data: Path, variant: str = "cpu") -> Path:
    directory = engine.engine_dir(data)
    engine.site_dir(directory).mkdir(parents=True)
    engine.write_state(directory, EngineState(variant=variant, verified=True, models_ready=True))
    return directory


def test_boot_in_developer_mode_leaves_sys_path_alone(monkeypatch):
    """A venv's own paddle (the CUDA build on a dev box) must never be shadowed."""
    from ocr_snap.bootstrap import boot

    monkeypatch.delenv("OCR_SNAP_BUNDLE", raising=False)
    before = list(sys.path)
    started = boot()
    assert not started.bundled and started.state is None and started.log_path is None
    assert not started.needs_engine
    assert sys.path == before


def test_boot_in_a_bundle_activates_the_installed_engine(bundle_env):
    from ocr_snap.bootstrap import boot

    _root, data = bundle_env
    started = boot()
    assert started.bundled and started.needs_engine
    directory = _install_fake_engine(data)
    started = boot()
    assert started.state is not None and started.state.variant == "cpu" and not started.needs_engine
    assert site.USER_SITE == str(engine.site_dir(directory))


def test_boot_reports_a_broken_bundle(monkeypatch, tmp_path):
    from ocr_snap.bootstrap import boot

    monkeypatch.setenv("OCR_SNAP_BUNDLE", str(tmp_path / "nowhere"))
    started = boot()
    assert not started.bundled and started.bundle_error and "not a directory" in started.bundle_error


# --------------------------------------------------------------------------
# CLI flags
# --------------------------------------------------------------------------

def test_version_flag():
    from ocr_snap.version import __version__

    done = _child(["-m", "ocr_snap", "--version"])
    assert done.returncode == 0 and done.stdout.strip() == __version__


def test_self_test_flag_reports_json():
    done = _child(["-m", "ocr_snap", "--self-test"], env={"QT_QPA_PLATFORM": "offscreen"})
    report = json.loads(done.stdout)
    assert report["imports"]["failed"] == {} and report["imports"]["count"] > 20
    assert report["stdlib"]["failed"] == {}
    assert report["bundle"] is None and report["engine"] == {"bundled": False}
    assert done.returncode == (0 if report["ok"] else 1)


def test_import_all_skips_main(monkeypatch):
    from ocr_snap import cli

    imported, failed = cli.import_all()
    assert "ocr_snap.__main__" not in imported and failed == {}
    assert {"ocr_snap.app", "ocr_snap.runtime.install", "ocr_snap.engine_setup"} <= set(imported)


def test_install_engine_needs_a_bundle():
    done = _child(["-m", "ocr_snap", "--install-engine", "cpu"])
    assert done.returncode == 2 and "needs a portable bundle" in done.stdout


def test_install_engine_gpu_without_a_gpu_build_exits_3(bundle_env, monkeypatch, capsys):
    from ocr_snap import cli
    from ocr_snap.bootstrap import boot
    from ocr_snap.runtime import gpu

    monkeypatch.setattr(gpu, "probe_gpus", lambda os_name: gpu.GpuProbe(error="no NVIDIA driver found"))
    assert cli.install_engine(boot(), "gpu") == cli.EXIT_NO_GPU
    out = capsys.readouterr().out
    assert "no NVIDIA driver found" in out and out.strip().splitlines()[-1].startswith("RESULT ")


def test_ocr_smoke_without_an_engine_in_a_bundle_fails_fast(bundle_env, capsys):
    from ocr_snap import cli
    from ocr_snap.bootstrap import boot

    assert cli.ocr_smoke(boot()) == cli.EXIT_FAIL
    assert "no OCR engine is installed" in capsys.readouterr().out


def test_smoke_line_renders_dark_text_on_white(qapp):
    from ocr_snap.cli import render_line

    image, family = render_line()
    assert image.shape == (128, 960, 3) and image.dtype.name == "uint8"
    assert (image < 128).any() and (image > 200).any() and family


def test_the_smoke_line_falls_back_to_pillow(monkeypatch):
    from ocr_snap import cli

    font = next((p for p in cli.FONT_FILES if os.path.exists(p)), None)
    if font is None:
        pytest.skip("no system font from cli.FONT_FILES")
    monkeypatch.setattr(cli, "FONT_FILES", ("/no/such/font.ttf", font))
    image, family = cli._render_with_pillow("OCR", 640, 96)
    assert image.shape == (96, 640, 3) and (image < 128).any()
    assert family == os.path.basename(font)


# --------------------------------------------------------------------------
# The engine setup dialog, driven by a fake service
# --------------------------------------------------------------------------

class _FakeSetup(QObject):
    step = pyqtSignal(str, object, object)
    progress = pyqtSignal(object, object)
    log = pyqtSignal(str)
    notice = pyqtSignal(str)
    finished = pyqtSignal(object)

    def __init__(self, gpu: bool = True) -> None:
        super().__init__()
        from ocr_snap.engine_setup import Offer

        self._offers = ([Offer("cu129", "GPU build (CUDA 12.9)", "about 5.4 GB to download", True)] if gpu
                        else []) + [Offer("cpu", "CPU build", "about 210 MB to download", not gpu)]
        self.started: list[str] = []
        self.cancelled = False

    def hardware_text(self) -> str:
        return "NVIDIA GeForce RTX 4090 · driver 580.65.06"

    def recommendation_reason(self) -> str:
        return "reason"

    def offers(self):
        return self._offers

    def installed_text(self) -> str:
        return ""

    def start(self, variant: str) -> None:
        self.started.append(variant)

    def cancel(self) -> None:
        self.cancelled = True

    def running(self) -> bool:
        return bool(self.started)


def test_setup_dialog_installs_the_recommended_build(qapp):
    from ocr_snap.engine_setup import EngineSetupDialog, SetupOutcome

    setup = _FakeSetup()
    dialog = EngineSetupDialog(setup)
    assert dialog.selected() == "cu129" and dialog.cancel_button.text() == "Quit"
    dialog.install_button.click()
    assert setup.started == ["cu129"] and dialog.state() == "installing"
    assert not dialog.option_buttons["cpu"].isEnabled()
    setup.step.emit("Downloading", 1_000_000_000, 5_400_000_000)
    assert "1.00 GB of about 5.40 GB" in dialog.bytes_label.text()
    setup.finished.emit(SetupOutcome(ok=True, title="CPU build", fell_back=True, fallback_reason="no CUDA"))
    assert dialog.state() == "done" and "no CUDA" in dialog.notice_label.text()
    dialog.install_button.click()
    assert dialog.result() == dialog.DialogCode.Accepted


def test_setup_dialog_close_while_installing_cancels_first(qapp):
    from ocr_snap.engine_setup import EngineSetupDialog, SetupOutcome

    setup = _FakeSetup(gpu=False)
    dialog = EngineSetupDialog(setup)
    assert dialog.selected() == "cpu"
    dialog.install_button.click()
    dialog.reject()
    assert setup.cancelled and dialog.state() == "installing"
    setup.finished.emit(SetupOutcome(ok=False, cancelled=True, error="Cancelled"))
    assert dialog.state() == "cancelled" and dialog.install_button.text() == "Install"


def test_setup_dialog_failure_offers_a_retry(qapp):
    from ocr_snap.engine_setup import EngineSetupDialog, SetupOutcome

    setup = _FakeSetup(gpu=False)
    dialog = EngineSetupDialog(setup, have_engine=True)
    assert dialog.cancel_button.text() == "Close"
    dialog.install_button.click()
    setup.finished.emit(SetupOutcome(ok=False, error="pip failed (exit code 1)"))
    assert dialog.state() == "failed" and dialog.install_button.text() == "Try again"
    assert "pip failed" in dialog.notice_label.text()
