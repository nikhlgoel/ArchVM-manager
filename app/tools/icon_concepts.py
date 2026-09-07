#!/usr/bin/env python3
"""
Distinct icon concepts, not variations on one shape.

The brief was that a rounded square with a glyph inside is generic — it is,
because almost everything ships one. These start from what the product
actually is: a *tiling* compositor running *inside* a window on another OS.
That gives two ideas worth drawing — tiles, and nesting — plus a few that
break the square silhouette entirely.

    python app/tools/icon_concepts.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QLinearGradient, QPainterPath, QBrush, QPen,
    QFont, QPolygonF,
)
from PySide6.QtWidgets import QApplication

BLUE = "#4f86ff"
BLUE_DEEP = "#2f5fd0"
VIOLET = "#8b5cf6"
AQUA = "#17b8c4"
AQUA_DEEP = "#0b5566"
INK = "#101a2e"
INK_SOFT = "#1b2743"

OUT = Path(__file__).resolve().parent.parent.parent / "docs" / "icons"


def _rr(s: float, inset: float = 0.055, radius: float = 0.235):
    m = s * inset
    body = QRectF(m, m, s - m * 2, s - m * 2)
    path = QPainterPath()
    path.addRoundedRect(body, s * radius, s * radius)
    return path, body


def _grad(a: str, b: str, r: QRectF) -> QLinearGradient:
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0.0, QColor(a))
    g.setColorAt(1.0, QColor(b))
    return g


def _edge(p: QPainter, body: QRectF, s: float, radius: float = 0.235,
          colour: str = AQUA_DEEP) -> None:
    """The dark aqua hint along the lower-right edges."""
    p.save()
    pen = QPen(QColor(colour), max(1.1, s * 0.045))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(body.adjusted(s * 0.01, s * 0.01, -s * 0.01, -s * 0.01),
              int(-58 * 16), int(-150 * 16))
    p.restore()


# --------------------------------------------------------------------------- #
def c_tiles(p: QPainter, s: float) -> None:
    """
    A: the tiling layout itself — one master pane, two stacked, with the
    focused pane ringed in aqua. Reads as a window manager, not an app chip.
    """
    path, body = _rr(s)
    p.fillPath(path, QBrush(QColor(INK)))
    p.save()
    p.setClipPath(path)

    gap = s * 0.045
    pad = s * 0.135
    inner = body.adjusted(pad, pad, -pad, -pad)
    lw = inner.width() * 0.54

    master = QRectF(inner.left(), inner.top(), lw, inner.height())
    rh = (inner.height() - gap) / 2
    top = QRectF(master.right() + gap, inner.top(),
                 inner.right() - master.right() - gap, rh)
    bot = QRectF(top.left(), top.bottom() + gap, top.width(), rh)

    r = s * 0.045
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(_grad(BLUE, VIOLET, master)))
    p.drawRoundedRect(master, r, r)
    p.setBrush(QBrush(QColor(INK_SOFT)))
    p.drawRoundedRect(top, r, r)
    p.drawRoundedRect(bot, r, r)

    # focus ring on the master pane
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(AQUA), max(1.0, s * 0.030)))
    p.drawRoundedRect(master.adjusted(-s * 0.012, -s * 0.012,
                                      s * 0.012, s * 0.012), r, r)
    p.restore()
    _edge(p, body, s)


def c_portal(p: QPainter, s: float) -> None:
    """
    B: a window inside a window. The outer frame is the host; the inner plane
    is tilted, as though you are looking through into another machine.
    """
    path, body = _rr(s)
    p.fillPath(path, QBrush(QColor(INK)))
    p.save()
    p.setClipPath(path)

    # title strip on the outer frame
    strip = QRectF(body.left(), body.top(), body.width(), s * 0.115)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(INK_SOFT)))
    p.drawRect(strip)
    d = s * 0.030
    for i, col in enumerate((AQUA, "#38507e", "#38507e")):
        p.setBrush(QBrush(QColor(col)))
        p.drawEllipse(QPointF(body.left() + s * 0.10 + i * s * 0.075,
                              strip.center().y()), d / 2, d / 2)

    # inner plane, in perspective
    quad = QPolygonF([
        QPointF(body.left() + body.width() * 0.20, body.top() + body.height() * 0.30),
        QPointF(body.right() - body.width() * 0.10, body.top() + body.height() * 0.19),
        QPointF(body.right() - body.width() * 0.10, body.bottom() - body.height() * 0.10),
        QPointF(body.left() + body.width() * 0.20, body.bottom() - body.height() * 0.21),
    ])
    g = QLinearGradient(quad.at(0), quad.at(2))
    g.setColorAt(0.0, QColor(AQUA))
    g.setColorAt(0.45, QColor(BLUE))
    g.setColorAt(1.0, QColor(VIOLET))
    p.setBrush(QBrush(g))
    p.setPen(Qt.NoPen)
    p.drawPolygon(quad)

    # depth: a darker left face
    side = QPolygonF([
        QPointF(body.left() + body.width() * 0.20, body.top() + body.height() * 0.30),
        QPointF(body.left() + body.width() * 0.20, body.bottom() - body.height() * 0.21),
        QPointF(body.left() + body.width() * 0.11, body.bottom() - body.height() * 0.26),
        QPointF(body.left() + body.width() * 0.11, body.top() + body.height() * 0.35),
    ])
    p.setBrush(QBrush(QColor(AQUA_DEEP)))
    p.drawPolygon(side)
    p.restore()
    _edge(p, body, s)


def c_knockout(p: QPainter, s: float) -> None:
    """
    C: the chevron cut clean out of the block, so the mark is the absence.
    Bold at any size because it is pure silhouette.
    """
    path, body = _rr(s)
    full = QPainterPath(path)

    cx = s * 0.5
    top = s * 0.245
    bot = s * 0.755
    half = s * 0.235
    chev = QPainterPath()
    chev.moveTo(cx, top)
    chev.lineTo(cx + half, bot)
    chev.lineTo(cx + half * 0.44, bot)
    chev.lineTo(cx, bot - s * 0.175)
    chev.lineTo(cx - half * 0.44, bot)
    chev.lineTo(cx - half, bot)
    chev.closeSubpath()

    cut = full.subtracted(chev)
    g = _grad(AQUA, VIOLET, body)
    g.setColorAt(0.42, QColor(BLUE))
    p.fillPath(cut, QBrush(g))

    p.save()
    p.setClipPath(cut)
    sh = QLinearGradient(body.topLeft(), QPointF(body.left(), body.center().y()))
    sh.setColorAt(0.0, QColor(255, 255, 255, 62))
    sh.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillRect(body, QBrush(sh))
    p.restore()
    _edge(p, body, s)


def c_stack(p: QPainter, s: float) -> None:
    """
    D: three planes receding — host, hypervisor, guest. No container at all,
    so the silhouette itself is unusual.
    """
    w = s * 0.62
    h = s * 0.30
    r = s * 0.055
    step = s * 0.115
    cx = s * 0.5
    base_y = s * 0.66

    layers = ((AQUA_DEEP, AQUA, 0.0), (BLUE_DEEP, BLUE, 1.0), (BLUE, VIOLET, 2.0))
    p.setPen(Qt.NoPen)
    for i, (a, b, k) in enumerate(layers):
        rect = QRectF(cx - w / 2 + k * s * 0.018,
                      base_y - k * step,
                      w, h)
        # shadow under each plane
        if i:
            sh = QColor(0, 0, 0, 60)
            p.setBrush(QBrush(sh))
            p.drawRoundedRect(rect.adjusted(s*0.012, s*0.03, s*0.012, s*0.03), r, r)
        p.setBrush(QBrush(_grad(a, b, rect)))
        p.drawRoundedRect(rect, r, r)
        # top hairline
        p.setPen(QPen(QColor(255, 255, 255, 70), max(1.0, s * 0.012)))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(rect.left() + r, rect.top() + s * 0.006),
                   QPointF(rect.right() - r, rect.top() + s * 0.006))
        p.setPen(Qt.NoPen)


def c_iso(p: QPainter, s: float) -> None:
    """
    E: an isometric block whose top face carries the tiling split. Genuinely
    three-dimensional, and the silhouette is a hexagon rather than a square.
    """
    cx, cy = s * 0.5, s * 0.52
    w = s * 0.40          # half-width
    hh = s * 0.21         # half-height of the top rhombus
    d = s * 0.24          # body depth

    top = QPolygonF([QPointF(cx, cy - hh), QPointF(cx + w, cy),
                     QPointF(cx, cy + hh), QPointF(cx - w, cy)])
    left = QPolygonF([QPointF(cx - w, cy), QPointF(cx, cy + hh),
                      QPointF(cx, cy + hh + d), QPointF(cx - w, cy + d)])
    right = QPolygonF([QPointF(cx + w, cy), QPointF(cx, cy + hh),
                       QPointF(cx, cy + hh + d), QPointF(cx + w, cy + d)])

    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(AQUA_DEEP)))
    p.drawPolygon(left)
    g = QLinearGradient(QPointF(cx, cy), QPointF(cx + w, cy + d))
    g.setColorAt(0.0, QColor(BLUE_DEEP))
    g.setColorAt(1.0, QColor("#3a2a7a"))
    p.setBrush(QBrush(g))
    p.drawPolygon(right)

    gt = QLinearGradient(QPointF(cx - w, cy), QPointF(cx + w, cy))
    gt.setColorAt(0.0, QColor(AQUA))
    gt.setColorAt(0.5, QColor(BLUE))
    gt.setColorAt(1.0, QColor(VIOLET))
    p.setBrush(QBrush(gt))
    p.drawPolygon(top)

    # tiling split drawn on the top face
    if s >= 28:
        p.setPen(QPen(QColor(255, 255, 255, 165), max(1.0, s * 0.020)))
        p.drawLine(QPointF(cx - w * 0.10, cy - hh * 0.45),
                   QPointF(cx + w * 0.52, cy + hh * 0.26))
        p.drawLine(QPointF(cx + w * 0.21, cy - hh * 0.10),
                   QPointF(cx - w * 0.30, cy + hh * 0.60))


def c_gap(p: QPainter, s: float) -> None:
    """
    F: the chevron formed by the gutters between panes — the negative space a
    tiling layout leaves behind. Most distinctive, needs the most size.
    """
    path, body = _rr(s)
    g = _grad(AQUA, VIOLET, body)
    g.setColorAt(0.45, QColor(BLUE))
    p.fillPath(path, QBrush(g))

    p.save()
    p.setClipPath(path)
    pen = QPen(QColor(INK), s * 0.085)
    pen.setCapStyle(Qt.FlatCap)
    pen.setJoinStyle(Qt.MiterJoin)
    p.setPen(pen)
    cx = s * 0.5
    p.drawLine(QPointF(cx, s * 0.10), QPointF(s * 0.94, s * 0.94))
    p.drawLine(QPointF(cx, s * 0.10), QPointF(s * 0.06, s * 0.94))
    p.drawLine(QPointF(cx, s * 0.50), QPointF(cx, s * 0.94))
    p.restore()
    _edge(p, body, s)


CONCEPTS = [
    ("A", "Tiles", "the tiling layout, focused pane ringed aqua", c_tiles),
    ("B", "Portal", "a window inside a window, in perspective", c_portal),
    ("C", "Knockout", "chevron cut out of the block", c_knockout),
    ("D", "Stack", "three receding planes, no container", c_stack),
    ("E", "Isometric", "a real 3D block, hexagonal silhouette", c_iso),
    ("F", "Gutters", "chevron formed by the gaps between panes", c_gap),
]


def draw(fn, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    fn(p, float(size))
    p.end()
    return pm


def sheet(dark: bool) -> QPixmap:
    cw, ch, cols = 250, 216, 3
    rows = (len(CONCEPTS) + cols - 1) // cols
    W, H = cols * cw + 40, rows * ch + 96
    bg = "#12151f" if dark else "#eef2fb"
    fg = "#e9ecf5" if dark else "#101728"
    sub = "#8590b0" if dark else "#6b7692"

    cv = QPixmap(W, H)
    cv.fill(QColor(bg))
    p = QPainter(cv)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

    f = QFont("Segoe UI", 14); f.setBold(True)
    p.setFont(f); p.setPen(QColor(fg))
    p.drawText(24, 36, "ArchVM  —  icon concepts")
    f2 = QFont("Segoe UI", 9)
    p.setFont(f2); p.setPen(QColor(sub))
    p.drawText(24, 56, "128 / 48 / 32 / 16 px  ·  "
                       + ("dark background" if dark else "light background"))

    for i, (key, name, desc, fn) in enumerate(CONCEPTS):
        cx = 24 + (i % cols) * cw
        cy = 78 + (i // cols) * ch
        f3 = QFont("Segoe UI", 11); f3.setBold(True)
        p.setFont(f3); p.setPen(QColor(fg))
        p.drawText(cx, cy + 14, f"{key}  {name}")
        p.setFont(f2); p.setPen(QColor(sub))
        p.drawText(QRectF(cx, cy + 20, cw - 18, 32), Qt.TextWordWrap, desc)

        y = cy + 60
        p.drawPixmap(cx, y, draw(fn, 128))
        x2 = cx + 140
        p.drawPixmap(x2, y + 8, draw(fn, 48))
        p.drawPixmap(x2 + 62, y + 8, draw(fn, 32))
        p.drawPixmap(x2 + 62, y + 52, draw(fn, 16))
        p.setPen(QColor(sub))
        p.drawText(x2, y + 76, "48")
        p.drawText(x2 + 62, y + 76, "32")
        p.drawText(x2 + 62, y + 90, "16")
    p.end()
    return cv


def main() -> int:
    QApplication.instance() or QApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    for key, name, _d, fn in CONCEPTS:
        draw(fn, 256).save(str(OUT / f"concept-{key}-{name.lower()}.png"), "PNG")
        print(f"  {key} {name}", flush=True)
    sheet(False).save(str(OUT / "concepts-light.png"), "PNG")
    sheet(True).save(str(OUT / "concepts-dark.png"), "PNG")
    print(f"\nsheets -> {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
