# OCR Snap

Extract text from any image in seconds. Paste or drag-drop an image, and OCR Snap
instantly recognizes text using PaddleOCR -- with optional automatic translation
to English via DeepL.

No cloud upload. No waiting. Just fast, local OCR with a clean dark interface.

## Why OCR Snap

- **Instant text extraction** -- paste from clipboard or drag-drop image files and
  get results in seconds
- **Works offline** -- OCR runs entirely on your machine using PaddleOCR with GPU
  acceleration
- **Automatic translation** -- non-English text is translated to English via DeepL
  (optional, requires free API key)
- **Interactive results** -- click any detected text region to highlight it on the
  image, copy individual results, or merge multiple selections
- **Multi-image workflow** -- load several images and switch between them without
  losing your place; zoom, pan, and selection state are preserved per image
- **Dark, distraction-free UI** -- built with PyQt6, designed to stay out of your way

## Showcase

### Main Interface

<!-- TODO: Replace with actual screenshot -->
![Main interface showing OCR results](media/main-interface.png)

*Paste an image and see extracted text appear in the sidebar with bounding boxes
overlaid on the canvas.*

### OCR Processing

<!-- TODO: Replace with actual screenshot -->
![Processing animation](media/processing.png)

*Animated scanning effect while OCR processes your image.*

### Interactive Results

<!-- TODO: Replace with actual screenshot -->
![Hovering over a result highlights it on the canvas](media/interactive-results.png)

*Hover over any result in the sidebar to highlight the corresponding region on the
image. Click to select, Ctrl+Click to multi-select.*

### Translation

<!-- TODO: Replace with actual screenshot -->
![Translation results](media/translation.png)

*Non-English text is automatically translated. Original and translated text shown
side by side.*

### Multi-Image Gallery

<!-- TODO: Replace with actual screenshot -->
![Gallery with multiple images](media/gallery.png)

*Load multiple images and switch between them using the thumbnail gallery. Each image
retains its own OCR results, zoom level, and selections.*

## Download

Grab the latest build for your OS from
[Releases](https://github.com/blyat-uk/ocr-snap/releases/latest):

| OS | File |
|---|---|
| Windows 10/11 (x64) | `ocr-snap-vX.Y.Z-win.exe` (installer, no admin rights needed) or `-win.zip` (portable) |
| macOS 14.5+ (Apple Silicon) | `ocr-snap-vX.Y.Z-mac.dmg` |
| Linux x86_64 (glibc 2.34+) | `ocr-snap-vX.Y.Z-linux.AppImage` or `-linux.tar.gz` (portable) |

Each download is a self-contained Python runtime with the app and every
dependency except the OCR engine. On first start OCR Snap installs PaddlePaddle
into your user data folder: the CUDA build when it finds an NVIDIA GPU with a
recent enough driver (it checks that the GPU build actually works, and falls
back to the CPU build if not), the CPU build otherwise. Run it with
`--setup-engine` (or use the "OCR engine setup" shortcut) to switch later.

The builds are not code-signed: on Windows, SmartScreen may ask you to confirm
(More info → Run anyway); on macOS, open the app once with right-click → Open.

## Running from source

Requires Python 3.12 (Paddle currently requires `>=3.12,<3.13`).

```bash
git clone https://github.com/blyat-uk/ocr-snap.git
cd ocr-snap

python3 -m venv .venv               # Windows: python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate

pip install -e '.[ocr]'             # CPU
# or
pip install -e '.[ocr-gpu]'         # NVIDIA GPU (CUDA build of PaddlePaddle)
```

From source, OCR Snap uses whichever Paddle the environment has and never
installs one itself. It auto-detects CUDA at startup; you can force CPU from
**Settings → OCR engine → Device** if a low-VRAM GPU causes crashes.

A [DeepL API key](https://www.deepl.com/pro-api) (free tier available) is
optional; enter it in **Settings** to translate results.

## Settings

OCR Snap is configured entirely through its in-app **Settings** dialog --
open it from the button in the status bar (bottom of the window) or with
`Ctrl+,`.

### Translation (DeepL)

Paste your [DeepL API key](https://www.deepl.com/account/summary) into the
**Translation** section and click **Test key** to verify it. Free-tier keys
end with `:fx`; the dialog routes to the correct DeepL endpoint automatically.
Translation is optional -- without a key, OCR still works, you just won't get
translations.

### Performance tier

The **Hardware profile** section picks a preset that controls model size,
device, OCR input resolution, and the processing animation. On first launch
OCR Snap detects your RAM/CPU and chooses a tier automatically; you can
override it any time:

- **Performance** -- mobile model, CPU only, smaller input, animation off.
  Best for low-VRAM GPUs or ≤ 6 GB RAM machines.
- **Balanced** -- mobile model, auto device, medium input. The default for
  most modern laptops.
- **Quality** -- server model, auto device, full input resolution. Best for
  GPUs with plenty of VRAM where accuracy matters more than latency.

Use **Auto-detect** in the dialog to reset to the recommended tier. Tier or
device changes require an app restart to take effect; DeepL key and animation
changes apply immediately.

## Usage

From a source checkout, with the virtual environment activated:

```bash
ocr-snap                            # or: python -m ocr_snap
```

### How to use

1. **Load an image** -- press `Ctrl+V` to paste from clipboard, or drag-drop an
   image file onto the window
2. **Wait for OCR** -- a scanning animation plays while text is being extracted
3. **Browse results** -- detected text appears in the sidebar with confidence scores;
   hover over any entry to see its location highlighted on the image
4. **Copy text** -- click the copy button next to any result to copy it to your
   clipboard
5. **Merge selections** -- Ctrl+Click to select multiple results, then right-click
   to merge them into a single text block
6. **Navigate** -- use `Ctrl+Scroll` to zoom, click and drag to pan
7. **Multiple images** -- paste or drop additional images; a thumbnail gallery
   appears for switching between them
8. **Tune things** — open Settings (button in the status bar, or `Ctrl+,`)
   to enter your DeepL key, switch performance tier, or change the OCR model
   and device. See the [Settings](#settings) section above for details.

## Building the release bundles

`packaging/build.py` builds the artifacts for the OS it runs on (stdlib only,
any Python 3.11+): a [python-build-standalone](https://github.com/astral-sh/python-build-standalone)
interpreter with the pinned dependencies (`packaging/requirements-bundle.txt`,
`packaging/constraints-bundle.txt`), the app's sources, and native launchers —
an AppImage and tarball on Linux, an Inno Setup installer and zip on Windows
(needs MSVC and Inno Setup 6), a signed-ad-hoc `.app` in a `.dmg` on macOS.

```bash
python packaging/build.py                       # artifacts into dist/
python packaging/build.py run -- --self-test    # run the built bundle
```

Pushing a `vX.Y.Z` tag that matches `src/ocr_snap/version.py` makes CI run the
tests, build all three, smoke-test each (engine install and a real OCR run
included) and publish the release.

## License

MIT — see [LICENSE](LICENSE).
