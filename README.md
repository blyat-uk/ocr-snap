# OCR Snap

**Paste an image, translate the text.** Press `Ctrl+V` and OCR Snap reads every line in the screenshot or photo, on your own machine. Copy any of it, or turn on Overlay and read it right on the image.

[![OCR Snap](.github/readme/website.png)](https://ocr-snap.blyat.uk/)

**Website: [ocr-snap.blyat.uk](https://ocr-snap.blyat.uk/)**

## Download

Get the latest build from the [releases page](https://github.com/blyat-uk/ocr-snap/releases/latest):

| OS | File |
|---|---|
| Windows 10/11 (x64) | `-win.exe` installer (per-user, no admin rights needed), or `-win.zip` portable |
| macOS 14.5+ (Apple Silicon) | `-mac.dmg` |
| Linux x86_64 | `-linux.AppImage`, or `-linux.tar.gz` portable |

Each release lists every file and what it is for, plus `SHA256SUMS.txt` to verify them against.

## First run

The OCR engine (PaddlePaddle) is not in the download; OCR Snap installs it the first time it starts. On an NVIDIA GPU with a recent driver it picks the matching CUDA build (2–5.5 GB to download, up to 8 GB on disk) and checks that it works; otherwise, or if the GPU check fails, it installs the CPU build (about 0.2 GB). Run it with `--setup-engine` (or use the "OCR engine setup" shortcut) to switch between GPU and CPU later.

The engine and the OCR models live in your user data folder, not in the app:

| OS | Data folder |
|---|---|
| Windows | `%LOCALAPPDATA%\ocr-snap` |
| macOS | `~/Library/Application Support/ocr-snap` |
| Linux | `~/.local/share/ocr-snap` |

Translation is optional: paste a [DeepL API key](https://www.deepl.com/pro-api) (the free tier works) into Settings (`Ctrl+,`) to translate results into English.

## Platform notes

- **Windows:** the installer is not code-signed; SmartScreen may ask you to confirm (More info → Run anyway).
- **macOS:** the app is not notarized. Open it once with right-click → Open, or allow it under System Settings → Privacy & Security, or run `xattr -dr com.apple.quarantine "/Applications/OCR Snap.app"`.
- **Linux:** needs an X11 or Wayland desktop and glibc 2.34+; on X11 install `libxcb-cursor0` if the window does not open.

## Run from source

Python 3.12.

```bash
git clone https://github.com/blyat-uk/ocr-snap.git
cd ocr-snap
python3 -m venv .venv
.venv/bin/pip install -e '.[ocr-gpu]'   # or: '.[ocr]' (CPU)
.venv/bin/python -m ocr_snap
```

From source, OCR Snap uses whichever Paddle the environment has and never installs one itself.

## Develop

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q   # tests
python packaging/build.py                                  # release build for this OS
python packaging/build.py run -- --self-test               # run the built bundle
```

Pushing a `vX.Y.Z` tag that matches `src/ocr_snap/version.py` builds, tests and publishes a release for all three platforms. Its notes are the downloads table and the commits since the previous tag, nothing else, so anything a user needs to know goes in this README.

## License

[MIT](LICENSE)
