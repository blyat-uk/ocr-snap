"""Draw the application icon: src/ocr_snap/resources/app-icon.png (1024 px).

A dark tile holding a snapped image: lines of text, one of them picked out
by the blue detection box and corner handles the canvas draws around OCR
results. No fonts: the text is drawn as bars, so any machine renders the
same icon. Run it with the dev venv when the design changes; the PNG is
committed, and the build derives .ico/.icns from it.

    .venv/bin/python packaging/make_icon.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen

OUT = Path(__file__).resolve().parent.parent / "src" / "ocr_snap" / "resources" / "app-icon.png"
SIZE = 1024
TILE = "#14161a"          # theme.Tokens.bg_base
CARD = "#23262c"
TEXT = "#5b606b"
TEXT_HOT = "#e8eaee"
ACCENT = "#4a9eff"        # theme.Tokens.accent


def draw() -> QImage:
    img = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # The tile: the app's canvas colour, a macOS-like squircle margin.
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(64, 64, SIZE - 128, SIZE - 128), 200, 200)
    p.fillPath(tile, QColor(TILE))

    # The snapped image: a card, slightly tilted like a pasted screenshot.
    p.save()
    p.translate(SIZE / 2, SIZE / 2)
    p.rotate(-6)
    card = QRectF(-300, -330, 600, 660)
    shape = QPainterPath()
    shape.addRoundedRect(card, 48, 48)
    p.fillPath(shape, QColor(CARD))

    # Its text: rows of rounded bars.
    p.setPen(Qt.PenStyle.NoPen)
    rows = ((-250, 380), (-170, 460), (-10, 420), (70, 300), (150, 440), (230, 340))
    hot_row = 2
    for i, (y, width) in enumerate(rows):
        p.setBrush(QColor(TEXT_HOT if i == hot_row else TEXT))
        p.drawRoundedRect(QRectF(-230, y, width, 44), 22, 22)
    p.restore()

    # The detection box, upright over the tilted line: what OCR found.
    p.save()
    p.translate(SIZE / 2, SIZE / 2)
    p.rotate(-6)
    box = QRectF(-262, -42, 484, 108)
    p.setBrush(QColor(74, 158, 255, 46))
    pen = QPen(QColor(ACCENT), 14)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawRoundedRect(box, 18, 18)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(ACCENT))
    for corner in (box.topLeft(), box.topRight(), box.bottomLeft(), box.bottomRight()):
        p.drawEllipse(QPointF(corner), 26, 26)
    p.restore()
    p.end()
    return img


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not draw().save(str(OUT)):
        sys.exit(f"could not write {OUT}")
    print(OUT)
