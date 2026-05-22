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

## Requirements

- Python 3.12 (Paddle currently requires `>=3.12,<3.13`)
- Optional: a CUDA-capable GPU for faster OCR -- install with the `[gpu]` extra
  (see [GPU support](#gpu-support-optional)). CPU works out of the box.
- Optional: a [DeepL API key](https://www.deepl.com/pro-api) (free tier available)
  for automatic translation -- enter it in **Settings** at runtime.

## Installation

### Linux

```bash
# Clone the repository
git clone https://codeberg.org/BuGiPoP/ocr-snap.git
cd ocr-snap

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package
pip install -e .
```

### Windows

```powershell
# Clone the repository
git clone https://codeberg.org/BuGiPoP/ocr-snap.git
cd ocr-snap

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install the package
pip install -e .
```

### macOS

```bash
# Clone the repository
git clone https://codeberg.org/BuGiPoP/ocr-snap.git
cd ocr-snap

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package
pip install -e .
```

### GPU support (optional)

The default install runs PaddleOCR on CPU. To enable CUDA-backed inference,
install the GPU extra after the base install:

```bash
pip install -e '.[gpu]'
```

This pulls `paddlepaddle-gpu` in addition to the CPU runtime. OCR Snap
auto-detects CUDA at startup; if a GPU is found it will be used, otherwise it
falls back to CPU. You can also force CPU from **Settings → OCR engine → Device**
if a low-VRAM GPU causes crashes.

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

With the virtual environment activated:

```bash
ocr-snap
```

Or run directly without activating the environment:

```bash
# Linux / macOS
.venv/bin/python -m ocr_snap

# Windows
.venv\Scripts\python -m ocr_snap
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

## License

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
