from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QFontMetrics

from ocr_snap.models import OCRResultItem

_PADDING_H = 6
_PADDING_V = 3
_MARGIN = 8


def place_labels(
    items: list[OCRResultItem],
    image_rect: QRectF,
    font_metrics: QFontMetrics,
) -> list[tuple[QRectF, QPointF]]:
    """Return (label_rect, anchor_point) for each item.

    Tries right → left → above → below placement with collision avoidance.
    """
    placed: list[QRectF] = []
    bbox_rects = [
        QRectF(it.bbox[0], it.bbox[1], it.bbox[2] - it.bbox[0], it.bbox[3] - it.bbox[1])
        for it in items
    ]
    results: list[tuple[QRectF, QPointF]] = []

    for i, item in enumerate(items):
        text_width = font_metrics.horizontalAdvance(item.text)
        label_w = text_width + 2 * _PADDING_H
        label_h = font_metrics.height() + 2 * _PADDING_V

        br = bbox_rects[i]
        cx = br.center().x()
        cy = br.center().y()

        candidates = [
            # right
            QRectF(br.right() + _MARGIN, cy - label_h / 2, label_w, label_h),
            # left
            QRectF(br.left() - _MARGIN - label_w, cy - label_h / 2, label_w, label_h),
            # above
            QRectF(cx - label_w / 2, br.top() - _MARGIN - label_h, label_w, label_h),
            # below
            QRectF(cx - label_w / 2, br.bottom() + _MARGIN, label_w, label_h),
        ]

        best = None
        for cand in candidates:
            if _is_valid(cand, bbox_rects, placed, image_rect):
                best = cand
                break

        if best is None:
            # Fallback: nudge outward with increasing multipliers
            for mult in (1.5, 2.0, 3.0):
                for cand in candidates:
                    nudged = _nudge(cand, br.center(), mult)
                    clamped = _clamp(nudged, image_rect)
                    if _is_valid(clamped, bbox_rects, placed, image_rect, strict=False):
                        best = clamped
                        break
                if best is not None:
                    break

        if best is None:
            # Last resort: use right candidate clamped to bounds
            best = _clamp(candidates[0], image_rect)

        anchor = QPointF(
            best.left() if best.center().x() > cx else best.right(),
            best.center().y(),
        )
        placed.append(best)
        results.append((best, anchor))

    return results


def _is_valid(
    rect: QRectF,
    bbox_rects: list[QRectF],
    placed: list[QRectF],
    image_rect: QRectF,
    strict: bool = True,
) -> bool:
    if strict and not image_rect.contains(rect):
        return False
    for br in bbox_rects:
        if rect.intersects(br):
            return False
    for pr in placed:
        if rect.intersects(pr):
            return False
    return True


def _nudge(rect: QRectF, center: QPointF, multiplier: float) -> QRectF:
    dx = rect.center().x() - center.x()
    dy = rect.center().y() - center.y()
    return rect.translated(dx * (multiplier - 1), dy * (multiplier - 1))


def _clamp(rect: QRectF, bounds: QRectF) -> QRectF:
    x = max(bounds.left(), min(rect.left(), bounds.right() - rect.width()))
    y = max(bounds.top(), min(rect.top(), bounds.bottom() - rect.height()))
    return QRectF(x, y, rect.width(), rect.height())
