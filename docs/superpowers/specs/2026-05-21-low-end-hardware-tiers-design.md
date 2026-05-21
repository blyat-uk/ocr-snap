# Low-End Hardware Tiers — Design

**Date:** 2026-05-21
**Status:** Approved (pending spec review)

## Problem

A user on Windows with 6 GB RAM and an NVIDIA GTX 1650 (4 GB VRAM) reports
OCR Snap crashes after pasting an image. Root cause is high confidence:

- `ocr_engine.py` hardcodes the PP-OCRv5 **server** detection and recognition
  models (`ocr_engine.py:58-59`). Server weights plus cuDNN workspace exceed
  the GTX 1650's free VRAM, especially with the OS/browser also using the
  card. PaddlePaddle GPU OOMs typically present as native segfaults that
  bypass Python's `try/except` at `ocr_engine.py:90-95`, so the user sees a
  hard crash rather than an error message.
- There is no way to choose mobile models or to force CPU inference.
- Several secondary issues compound memory pressure on low-end machines:
  - Full-resolution numpy array kept forever in `ImageState.array`.
  - Full-resolution `QPixmap` kept in `ImageState.pixmap` and again as a
    gallery thumbnail (no resize on the gallery side).
  - Processing animation spawns ~90 `QGraphicsEllipseItem`s per second with
    radial gradients (`canvas.py:_anim_tick`).
  - OCR downscale cap is 2000 px long-side regardless of hardware.
  - PaddleOCR receives no `cpu_threads` / `enable_mkldnn` tuning.

## Goal

Introduce a hardware-tier system modelled on the sibling project
`/Users/user/Code/subs/sub-label-pos` so OCR Snap auto-detects machine
capability on first run, picks safe defaults, and exposes a per-knob
override UI for power users.

## Non-goals

- VRAM detection on Windows (requires `pynvml` or WMI, deferred). RAM is
  used as the proxy.
- Live model swap without restart. Model/device changes require an app
  restart; we follow sub-label-pos's restart-prompt UX.
- Translating UI strings (English only, like today).

## Tiers and defaults

Tier names match sub-label-pos for consistency. RAM thresholds copied
verbatim so a 6 GB Windows user lands on Performance.

| | low | medium | high |
|---|---|---|---|
| User-facing label | **Performance** | **Balanced** | **Quality** |
| RAM threshold | ≤ 6 GB | 6–16 GB | > 16 GB |
| `model_variant` | `mobile` | `mobile` | `server` |
| `device` | `cpu` | `auto` | `auto` |
| `ocr_max_long_side` | 1280 | 2000 | 2400 |
| `drop_array_after_ocr` | True | True | False |
| `processing_animation` | `off` | `minimal` | `full` |
| `paddle_cpu_threads` | 2 | 4 | 0 |

(Note: `gallery_thumb_max_dim` was originally listed here but removed
during plan review — `GalleryThumbnail` already downscales internally
to 74×100 and discards the source pixmap, so a tier knob there would
save kilobytes at most. Real per-image memory is dominated by
`ImageState.array`, which `drop_array_after_ocr` handles.)

`mobile` = `PP-OCRv5_mobile_det` + `PP-OCRv5_mobile_rec`.
`server` = current `PP-OCRv5_server_det` + `PP-OCRv5_server_rec`.
`device = "auto"` resolves to GPU iff `paddle.is_compiled_with_cuda()`
returns True at engine init.
`processing_animation`:
- `off` — dim overlay only, no scan line, no sparks, animation timer
  never starts.
- `minimal` — scan line + overlay, zero sparks per tick.
- `full` — current behavior (3 sparks/tick).
`paddle_cpu_threads = 0` means "let Paddle decide".

CPU-core override (copied from sub-label-pos): if detected
`cpu_cores < 4`, force `paddle_cpu_threads = 1` regardless of tier.

## Architecture

### New module: `src/ocr_snap/hardware_profile.py`

Port of sub-label-pos's `services/hardware_profile.py`. Pure detection
with no PyQt imports:

- `_total_ram_bytes()` — tries `/proc/meminfo`, then `sysctl hw.memsize`,
  then `GlobalMemoryStatusEx` on Windows. Returns `None` if all fail.
- `_pick_tier(ram_gb)` — returns `"low"` for ≤ 6 GB, `"medium"` for
  ≤ 16 GB, `"high"` otherwise.
- `detect()` — returns `HardwareProfile(total_ram_gb, cpu_cores, tier)`.
  If RAM detection fails, assumes 4 GB / `"low"` (defensive default).

### New module: `src/ocr_snap/perf_settings.py`

Typed dataclasses and tier defaults:

```python
@dataclass
class OCRPerfSettings:
    model_variant: Literal["mobile", "server"] = "mobile"
    device: Literal["cpu", "auto"] = "auto"
    ocr_max_long_side: int = 2000
    drop_array_after_ocr: bool = True
    processing_animation: Literal["off", "minimal", "full"] = "minimal"
    paddle_cpu_threads: int = 4

@dataclass
class AppSettings:
    deepl_api_key: str = ""
    perf: OCRPerfSettings = field(default_factory=OCRPerfSettings)
    hardware_tier: str = "medium"
    detected_ram_gb: float = 0.0
    detected_cpu_cores: int = 0
    version: int = 1

TIER_ORDER = ["low", "medium", "high"]
TIER_LABELS = {"low": "Performance", "medium": "Balanced", "high": "Quality"}
_TIER_DEFAULTS: dict[str, OCRPerfSettings] = {...}  # as in table above

def apply_tier(settings: AppSettings, tier: str) -> AppSettings: ...
def from_profile(profile: HardwareProfile, deepl_key: str = "") -> AppSettings: ...
```

`apply_tier` overwrites `settings.perf` with the tier's defaults.
`from_profile` applies the CPU-core cap.

### Extend `src/ocr_snap/config.py`

The existing module already manages `~/.config/ocr-snap/config.json`
with a `deepl_api_key` field. We extend it (do not replace) so the file
remains a single source of truth.

```python
def load_app_settings() -> AppSettings: ...
def save_app_settings(settings: AppSettings) -> None: ...
def save_perf_settings(perf: OCRPerfSettings) -> None: ...  # convenience
```

`load_app_settings` behavior:
1. Read JSON; if missing or `perf` key absent, run
   `hardware_profile.detect()`, build settings via `from_profile`,
   merge any existing `deepl_api_key`, save back.
2. Otherwise deserialize, dropping unknown keys (forward-compat).

Existing helpers `load_config`, `save_config`, `resolve_deepl_key`,
`set_deepl_key` stay; they read/write the same JSON file.
`set_deepl_key` is updated to preserve the `perf` block.

### Parameterize `OCREngine`

```python
class OCREngine(QObject):
    model_load_failed = pyqtSignal(str)  # new

    def __init__(self, perf: OCRPerfSettings, parent: QObject | None = None) -> None:
        ...
        self._perf = perf
        self._max_long_side = perf.ocr_max_long_side
```

Inside `_init_ocr`:

```python
det = "PP-OCRv5_mobile_det" if perf.model_variant == "mobile" else "PP-OCRv5_server_det"
rec = "PP-OCRv5_mobile_rec" if perf.model_variant == "mobile" else "PP-OCRv5_server_rec"

kwargs = dict(
    text_detection_model_name=det,
    text_recognition_model_name=rec,
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)
device = self._resolve_device()  # "gpu" or "cpu"
kwargs["device"] = device
if device == "cpu" and perf.paddle_cpu_threads > 0:
    kwargs["cpu_threads"] = perf.paddle_cpu_threads
self._ocr = PaddleOCR(**kwargs)
```

`_resolve_device` returns a string suitable for PaddleOCR's `device`
keyword (`"gpu"` or `"cpu"`):
- `perf.device == "cpu"` → `"cpu"`.
- `perf.device == "auto"` → `"gpu"` iff `paddle.is_compiled_with_cuda()`
  returns True at runtime, else `"cpu"`.

The `OCRPerfSettings.device` field stays `"cpu" | "auto"` (user-facing
choice); the resolved `"gpu" | "cpu"` is an internal detail of the
engine, not persisted.

Errors during `_init_ocr` emit `model_load_failed(str)`; existing
`error_occurred` semantics for per-image errors unchanged.

### Extend `ImageState`

`models.py`:

```python
class ImageState:
    array: np.ndarray | None  # was: np.ndarray
```

Plus a helper used by re-OCR when the array has been dropped:

```python
def array_from_pixmap(pixmap: QPixmap) -> np.ndarray: ...
```

Implementation is the existing QImage → RGB888 → numpy copy lifted out
of `OCRCanvas._load_qimage` into a shared helper.

### `OCRCanvas` animation tier

Add a setter and gate spawn count:

```python
class OCRCanvas(QGraphicsView):
    def set_animation_mode(self, mode: Literal["off", "minimal", "full"]) -> None: ...
```

In `_start_processing`: if mode is `"off"`, add only the dim overlay,
do not create the scan line, do not start `_anim_timer`. In `_anim_tick`,
read `self._sparks_per_tick` (0 for `"minimal"`, 3 for `"full"`).

### Settings dialog rebuild

`settings_dialog.py` becomes a multi-group dialog with three sections:

1. **Translation** — existing DeepL key field, "Show" toggle, and a
   dedicated **"Test key"** button that performs the existing
   `https://api(-free).deepl.com/v2/usage` round-trip and updates an
   inline status label. The dialog's primary **OK** button saves all
   sections together; if the DeepL key field was edited but never
   tested (or the last test failed), OK still saves the key as entered
   — testing is advisory, not gating. (This is a small UX shift from
   the current single-purpose dialog where OK *was* the test.)
2. **OCR engine** — `Model:` combo (Mobile / Server), `Device:` combo
   (Auto / CPU). Bound to `settings.perf.model_variant` and `.device`.
3. **Hardware profile** — `Profile:` combo (Performance / Balanced /
   Quality) + "Auto-detect" button + read-only detected info line
   (`Detected: X.X GB RAM · N cores · auto-tier Y`) + restart-required
   hint.

Signals:
- existing `accepted` continues to expose the saved DeepL key
- `tier_overridden(str)` — emitted on OK if the tier combo value changed
- `perf_changed()` — emitted on OK if any individual OCR-engine override
  changed
- `hardware_redetect_requested()` — emitted when "Auto-detect" is clicked

On OK: dialog mutates the passed-in `AppSettings`, calls
`config.save_app_settings`, then emits whichever signals apply.

### `MainWindow` wiring

In `__init__`:

```python
self._app_settings = config.load_app_settings()
self._ocr_engine = OCREngine(self._app_settings.perf, self)
self._ocr_engine.model_load_failed.connect(self._on_model_load_failed)
self._canvas.set_animation_mode(self._app_settings.perf.processing_animation)
```

In `_on_ocr_results`: after `state.ocr_results = results`, if
`self._app_settings.perf.drop_array_after_ocr` and `results.items`,
set `state.array = None`.

In `_on_reocr_requested`: if `state.array is None`, rebuild via
`array_from_pixmap(state.pixmap)`.

In `_on_settings_requested`: open the new dialog with the current
`AppSettings`. Handle:
- `dialog.tier_overridden` and `dialog.perf_changed` → show
  `QMessageBox.information` with a "Restart OCR Snap for the new OCR
  engine settings to take effect." message. The animation mode applies
  live (re-call `set_animation_mode` after save).
- `dialog.hardware_redetect_requested` → `from_profile(detect())`,
  preserve DeepL key, save, refresh the dialog's detected line.

New slot `_on_model_load_failed(message)` shows a persistent status-bar
message and a one-time `QMessageBox.critical` so the user knows to
switch tier or device.

## Files touched

| File | Change |
|---|---|
| `src/ocr_snap/hardware_profile.py` | New |
| `src/ocr_snap/perf_settings.py` | New |
| `src/ocr_snap/config.py` | Extend with `AppSettings` load/save; preserve `deepl_api_key` flow |
| `src/ocr_snap/ocr_engine.py` | Constructor takes `OCRPerfSettings`; remove hardcoded model names; add `model_load_failed` signal; device resolution; cpu_threads wiring |
| `src/ocr_snap/settings_dialog.py` | Rebuild as multi-group dialog (Translation / OCR engine / Hardware profile) |
| `src/ocr_snap/canvas.py` | `set_animation_mode()`; conditional scan line and spark count; lift `array_from_pixmap` helper out of `_load_qimage` |
| `src/ocr_snap/main_window.py` | Load settings → engine; drop-array after OCR; animation mode; restart-prompt UX; model-load-failed handler |
| `src/ocr_snap/models.py` | `ImageState.array: np.ndarray \| None` |
| `pyproject.toml` | No new runtime deps (pure stdlib detection). If desired later, add an optional `nvidia` extra with `pynvml`. |
| `tests/test_hardware_profile.py` | New: `_pick_tier` parametrized + `detect` smoke test |
| `tests/test_perf_settings.py` | New: tier defaults, `apply_tier`, `from_profile` CPU cap, JSON round-trip, first-run detection |

A `tests/` directory does not yet exist in the repo; the implementation
plan should bootstrap it (with a `conftest.py` if needed).

## Tests

Following sub-label-pos's pattern:

- `tests/test_hardware_profile.py`
  - `_pick_tier` parametrized over boundary values (2, 4, 6, 8, 12, 16,
    24, 64 GB → expected tier).
  - `detect()` returns a profile with `total_ram_gb > 0`,
    `cpu_cores >= 1`, `tier in {"low", "medium", "high"}`.
- `tests/test_perf_settings.py`
  - Each tier's `OCRPerfSettings` matches the table above.
  - `apply_tier(settings, "low")` overwrites `perf` fields exactly.
  - `from_profile(HardwareProfile(2.0, 2, "low"))` caps
    `paddle_cpu_threads` to 1.
  - JSON round-trip via `config.save_app_settings` /
    `config.load_app_settings` (using a temp path) preserves all fields.
  - First-run path: missing file → `detect()` is called, file is
    created, returned settings reflect the detected tier.

## UX notes

- The 6 GB / GTX 1650 user, on first launch after upgrading, gets:
  - Auto-detected RAM ≈ 6 GB → Performance tier.
  - Mobile model + CPU device → no GPU OOM, slower but stable.
  - 1280 px downscale, dimmer animation → less RAM/CPU during OCR.
- A user who *wants* to try the server model on a strong machine flips
  the Profile to Quality (or just toggles the Model combo to Server),
  clicks OK, restarts. No code change required.
- Restart prompt only appears when model or device changes — animation
  mode change is live.

## Implementation-time verifications

Not open design questions, but things the implementer must confirm
against the installed version before merging:

- The exact PaddleOCR `device` keyword (3.x uses `device="gpu"|"cpu"`).
- That `paddle.is_compiled_with_cuda()` works without instantiating a
  PaddleOCR object first (so `_resolve_device` can be called cheaply).
- The exact mobile model names (`PP-OCRv5_mobile_det` /
  `PP-OCRv5_mobile_rec`) match what `paddleocr>=3.0` ships with.
