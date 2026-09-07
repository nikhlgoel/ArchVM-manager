#!/usr/bin/env python3
"""
Render candidate application icons.

Each variant keeps the same silhouette and chevron, and differs only in how a
dark aqua accent meets the edges. Run it, look at the sheet, then set the
chosen variant in archvm/icons.py.

    python app/tools/icon_variants.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QLinearGradient, QRadialGradient, QPainterPath,
    QBrush, QPen, QFont,
)
from PySide6.QtWidgets import QApplication

BLUE = "#5b8cff"
VIOLET = "#8b5cf6"
AQUA_DEEP = "#0b5566"      # dark aqua, the accent asked for
AQUA_MID = "#0e7490"
AQUA_LIGHT = "#22b8cf"

OUT = Path(__file__).resolve().parent.parent.parent / "docs" / "icons"


# --------------------------------------------------------------------------- #
def _body_path(s: float) -> tuple[QPainterPath, QRectF, float]:
    margin = s * 0.055
    body = QRectF(margin, margin, s - margin * 2, s - margin * 2)
    radius = s * 0.235
    path = QPainterPath()
    path.addRoundedRect(body, radius, radius)
    return path, body, radius


def _chevron(p: QPainter, s: float, colour: str = "#ffffff") -> None:
    cx = s * 0.5
    top = s * 0.235
    bot = s * 0.745
    half = s * 0.225
    notch = s * 0.115
    chev = QPainterPath()
    chev.moveTo(cx, top)
    chev.lineTo(cx + half, bot)
    chev.lineTo(cx + half * 0.46, bot)
    chev.lineTo(cx, bot - notch * 1.5)
    chev.lineTo(cx - half * 0.46, bot)
    chev.lineTo(cx - half, bot)
    chev.closeSubpath()
    p.fillPath(chev, QBrush(QColor(colour)))


def _sheen(p: QPainter, path: QPainterPath, body: QRectF, alpha: int = 54) -> None:
    g = QLinearGradient(body.topLeft(), QPointF(body.left(), body.center().y()))
    g.setColorAt(0.0, QColor(255, 255, 255, alpha))
    g.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(path, QBrush(g))


def _base(p: QPainter, s: float, stops) -> tuple[QPainterPath, QRectF, float]:
    path, body, radius = _body_path(s)
    g = QLinearGradient(body.topLeft(), body.bottomRight())
    for at, colour in stops:
        g.setColorAt(at, QColor(colour))
    p.fillPath(path, QBrush(g))
    return path, body, radius


# --------------------------------------------------------------------------- #
#  Variants
# --------------------------------------------------------------------------- #
def v_rim(p: QPainter, s: float) -> None:
    """A: dark aqua rim along the lower-right edges, as if lit from top-left."""
    path, body, radius = _base(p, s, [(0.0, BLUE), (1.0, VIOLET)])
    _sheen(p, path, body)

    p.save()
    p.setClipPath(path)
    pen = QPen(QColor(AQUA_DEEP), max(1.2, s * 0.055))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    inset = body.adjusted(s * 0.012, s * 0.012, -s * 0.012, -s * 0.012)
    # bottom-right arc only: from ~ -60 deg sweeping to -220 deg
    p.drawArc(inset, int(-58 * 16), int(-150 * 16))
    p.restore()

    p.setPen(QPen(QColor(255, 255, 255, 46), max(1.0, s * 0.012)))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(body, radius, radius)
    _chevron(p, s)


def v_bevel(p: QPainter, s: float) -> None:
    """B: aqua inner shadow bottom-right, white inner highlight top-left."""
    path, body, radius = _base(p, s, [(0.0, BLUE), (1.0, VIOLET)])
    _sheen(p, path, body, 44)

    p.save()
    p.setClipPath(path)
    # aqua inner shadow
    g = QLinearGradient(body.bottomRight(), body.center())
    c0 = QColor(AQUA_DEEP); c0.setAlpha(150)
    c1 = QColor(AQUA_DEEP); c1.setAlpha(0)
    g.setColorAt(0.0, c0)
    g.setColorAt(0.55, c1)
    p.fillRect(body, QBrush(g))
    # white inner highlight
    g2 = QLinearGradient(body.topLeft(), body.center())
    h0 = QColor(255, 255, 255, 110)
    h1 = QColor(255, 255, 255, 0)
    g2.setColorAt(0.0, h0)
    g2.setColorAt(0.5, h1)
    p.fillRect(body, QBrush(g2))
    p.restore()

    p.setPen(QPen(QColor(255, 255, 255, 54), max(1.0, s * 0.012)))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(body, radius, radius)
    _chevron(p, s)


def v_corner(p: QPainter, s: float) -> None:
    """C: an aqua wedge tucked into the lower-left corner."""
    path, body, radius = _base(p, s, [(0.0, BLUE), (1.0, VIOLET)])

    p.save()
    p.setClipPath(path)
    wedge = QPainterPath()
    wedge.moveTo(body.left(), body.bottom())
    wedge.lineTo(body.left(), body.top() + body.height() * 0.38)
    wedge.lineTo(body.left() + body.width() * 0.62, body.bottom())
    wedge.closeSubpath()
    g = QLinearGradient(QPointF(body.left(), body.bottom()),
                        QPointF(body.center().x(), body.center().y()))
    c0 = QColor(AQUA_MID); c0.setAlpha(190)
    c1 = QColor(AQUA_DEEP); c1.setAlpha(0)
    g.setColorAt(0.0, c0)
    g.setColorAt(1.0, c1)
    p.fillPath(wedge, QBrush(g))
    p.restore()

    _sheen(p, path, body, 40)
    p.setPen(QPen(QColor(255, 255, 255, 46), max(1.0, s * 0.012)))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(body, radius, radius)
    _chevron(p, s)


def v_trigrad(p: QPainter, s: float) -> None:
    """D: aqua folded into the gradient itself, showing at the top-left edge."""
    path, body, radius = _base(p, s, [
        (0.0, AQUA_MID), (0.30, BLUE), (1.0, VIOLET)])
    _sheen(p, path, body, 48)
    p.setPen(QPen(QColor(255, 255, 255, 50), max(1.0, s * 0.012)))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(body, radius, radius)
    _chevron(p, s)


def v_halo(p: QPainter, s: float) -> None:
    """E: a thin dark aqua outline tracing the whole silhouette."""
    path, body, radius = _base(p, s, [(0.0, BLUE), (1.0, VIOLET)])
    _sheen(p, path, body)

    pen = QPen(QColor(AQUA_DEEP), max(1.4, s * 0.05))
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(body, radius, radius)
    # inner hairline keeps it from looking like a sticker
    p.setPen(QPen(QColor(255, 255, 255, 60), max(1.0, s * 0.014)))
    inner = body.adjusted(s * 0.035, s * 0.035, -s * 0.035, -s * 0.035)
    p.drawRoundedRect(inner, radius * 0.86, radius * 0.86)
    _chevron(p, s)


def v_underglow(p: QPainter, s: float) -> None:
    """F: aqua light pooling under the lower edge, like the chip sits on it."""
    path, body, radius = _base(p, s, [(0.0, BLUE), (1.0, "#7c4ff0")])

    p.save()
    p.setClipPath(path)
    rg = QRadialGradient(QPointF(body.center().x(), body.bottom() + s * 0.06),
                         body.width() * 0.78)
    c0 = QColor(AQUA_LIGHT); c0.setAlpha(165)
    c1 = QColor(AQUA_DEEP); c1.setAlpha(0)
    rg.setColorAt(0.0, c0)
    rg.setColorAt(1.0, c1)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(rg))
    p.drawRect(body)
    p.restore()

    _sheen(p, path, body, 40)
    p.setPen(QPen(QColor(255, 255, 255, 46), max(1.0, s * 0.012)))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(body, radius, radius)
    _chevron(p, s)


VARIANTS = [
    ("A", "Rim", "dark aqua edge along the lower-right", v_rim),
    ("B", "Bevel", "aqua inner shadow, white inner highlight", v_bevel),
    ("C", "Corner", "aqua wedge in the lower-left", v_corner),
    ("D", "Tri-gradient", "aqua folded into the gradient", v_trigrad),
    ("E", "Halo", "thin aqua outline around the whole shape", v_halo),
    ("F", "Underglow", "aqua pooling beneath the lower edge", v_underglow),
]


def draw(fn, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    fn(p, float(size))
    p.end()
    return pm


def sheet(dark_bg: bool) -> QPixmap:
    cell_w, cell_h = 250, 210
    cols = 3
    rows = (len(VARIANTS) + cols - 1) // cols
    W = cols * cell_w + 40
    H = rows * cell_h + 96

    bg = "#12151f" if dark_bg else "#eef2fb"
    fg = "#e9ecf5" if dark_bg else "#101728"
    sub = "#8590b0" if dark_bg else "#6b7692"

    canvas = QPixmap(W, H)
    canvas.fill(QColor(bg))
    p = QPainter(canvas)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

    f = QFont("Segoe UI", 14); f.setBold(True)
    p.setFont(f); p.setPen(QColor(fg))
    p.drawText(24, 36, "ArchVM icon variants  —  dark aqua edge accents")
    f2 = QFont("Segoe UI", 9)
    p.setFont(f2); p.setPen(QColor(sub))
    p.drawText(24, 56, "shown at 128, 48, 32 and 16 px  ·  "
                       + ("dark background" if dark_bg else "light background"))

    for i, (key, name, desc, fn) in enumerate(VARIANTS):
        cx = 24 + (i % cols) * cell_w
        cy = 78 + (i // cols) * cell_h

        f3 = QFont("Segoe UI", 11); f3.setBold(True)
        p.setFont(f3); p.setPen(QColor(fg))
        p.drawText(cx, cy + 14, f"{key}  {name}")
        p.setFont(f2); p.setPen(QColor(sub))
        p.drawText(QRectF(cx, cy + 20, cell_w - 20, 30),
                   Qt.TextWordWrap, desc)

        y = cy + 56
        p.drawPixmap(cx, y, draw(fn, 128))
        x2 = cx + 140
        p.drawPixmap(x2, y + 8, draw(fn, 48))
        p.drawPixmap(x2 + 60, y + 8, draw(fn, 32))
        p.drawPixmap(x2 + 60, y + 50, draw(fn, 16))
        p.setPen(QColor(sub))
        p.drawText(x2, y + 74, "48")
        p.drawText(x2 + 60, y + 74, "32")
        p.drawText(x2 + 60, y + 88, "16")

    p.end()
    return canvas


def main() -> int:
    app = QApplication.instance() or QApplication([])
    OUT.mkdir(parents=True, exist_ok=True)

    for key, name, _desc, fn in VARIANTS:
        draw(fn, 256).save(str(OUT / f"variant-{key}-{name.lower()}.png"), "PNG")
        print(f"  variant {key} {name}", flush=True)

    sheet(False).save(str(OUT / "variants-light.png"), "PNG")
    sheet(True).save(str(OUT / "variants-dark.png"), "PNG")
    print(f"\nsheets written to {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
