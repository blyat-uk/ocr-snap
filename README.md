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

- Python 3.12 or newer
- A GPU with CUDA support is recommended for fast OCR (CPU fallback works but is slower)
- A [DeepL API key](https://www.deepl.com/pro-api) (free tier available) if you want
  automatic translation

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

> **Note on GPU support:** OCR Snap auto-detects GPU support at startup and
> chooses CPU or GPU based on your hardware profile. If you're on a low-VRAM
> GPU and the app crashes after pasting, open Settings → OCR engine and set
> Device to "CPU only", or switch Profile to Performance.

## Configuration

Copy the example environment file and add your DeepL API key:

```bash
cp .env.example .env
```

Edit `.env` and set your key:

```
DEEPL_API_KEY=your-api-key-here
```

Translation is optional. If no API key is provided, OCR Snap will still extract
text -- it just won't translate.

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
8. **Pick a hardware profile** — open Settings (gear icon in the sidebar)
   to choose Performance / Balanced / Quality. On first run the app picks
   one based on detected RAM. Use Performance on low-VRAM GPUs or
   ≤ 6 GB RAM machines.

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
