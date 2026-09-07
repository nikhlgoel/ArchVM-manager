"""
Application iconography.

The mark is an isometric block: a Hyprland tiling split drawn across the top
face, a dark-aqua left face and a blue-to-violet right face. It is drawn with
QPainter rather than shipped as bitmaps so it stays sharp at every size, and
because the detail has to *change* with size — the split lines that make it
legible at 128px turn to mud at 16px.

Level of detail:
  >= 64 px   contact shadow, tiling split, hairline highlights
  32-63 px   block plus a single split line
  <  32 px   solid faces only, contrast pushed up
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QLinearGradient, QBrush, QPen, QPolygonF,
)

# Brand
AQUA = "#17b8c4"
AQUA_DEEP = "#0b5566"
AQUA_DARK = "#083f4d"
BLUE = "#4f86ff"
BLUE_DEEP = "#2f5fd0"
VIOLET = "#8b5cf6"
VIOLET_DEEP = "#3a2a7a"

STATE_COLORS = {
    "stopped": "#8b93ad",
    "running": "#22c55e",
    "busy": "#f5a524",
    "error": "#ef4444",
}


def _draw(size: int, state: str | None = None, *, mono: bool = False) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

    s = float(size)
    detail = size >= 64
    tiny = size < 32

    # Geometry. Slightly smaller and higher when a state pip is present, so the
    # pip has somewhere to sit without overlapping the block.
    pip = bool(state) and size >= 20
    scale = 0.90 if pip else 1.0
    cx = s * (0.48 if pip else 0.5)
    cy = s * (0.48 if pip else 0.50)
    w = s * 0.415 * scale          # half-width of the top rhombus
    hh = s * 0.215 * scale         # half-height of the top rhombus
    d = s * 0.255 * scale          # body depth

    top = QPolygonF([QPointF(cx, cy - hh), QPointF(cx + w, cy),
                     QPointF(cx, cy + hh), QPointF(cx - w, cy)])
    left = QPolygonF([QPointF(cx - w, cy), QPointF(cx, cy + hh),
                      QPointF(cx, cy + hh + d), QPointF(cx - w, cy + d)])
    right = QPolygonF([QPointF(cx + w, cy), QPointF(cx, cy + hh),
                       QPointF(cx, cy + hh + d), QPointF(cx + w, cy + d)])

    # ---- contact shadow, so the block sits on something ----
    if detail and not mono:
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(11, 34, 51, 46)))
        p.drawEllipse(QPointF(cx, cy + hh + d + s * 0.045),
                      w * 0.86, hh * 0.34)

    p.setPen(Qt.NoPen)

    if mono:
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawPolygon(left)
        p.drawPolygon(right)
        p.drawPolygon(top)
        p.setPen(QPen(QColor(0, 0, 0, 190), max(1.0, s * 0.022)))
        p.drawLine(QPointF(cx - w, cy), QPointF(cx, cy + hh))
        p.drawLine(QPointF(cx + w, cy), QPointF(cx, cy + hh))
        p.drawLine(QPointF(cx, cy + hh), QPointF(cx, cy + hh + d))
        p.end()
        return pm

    # ---- left face: dark aqua, the accent that grounds the whole mark ----
    gl = QLinearGradient(QPointF(cx - w, cy), QPointF(cx, cy + hh + d))
    gl.setColorAt(0.0, QColor(AQUA_DEEP))
    gl.setColorAt(1.0, QColor(AQUA_DARK if not tiny else AQUA_DEEP))
    p.setBrush(QBrush(gl))
    p.drawPolygon(left)

    # ---- right face ----
    gr = QLinearGradient(QPointF(cx, cy + hh), QPointF(cx + w, cy + d))
    gr.setColorAt(0.0, QColor(BLUE_DEEP))
    gr.setColorAt(1.0, QColor(VIOLET_DEEP))
    p.setBrush(QBrush(gr))
    p.drawPolygon(right)

    # ---- top face ----
    gt = QLinearGradient(QPointF(cx - w, cy + hh), QPointF(cx + w, cy - hh))
    gt.setColorAt(0.0, QColor(AQUA))
    gt.setColorAt(0.48, QColor(BLUE))
    gt.setColorAt(1.0, QColor(VIOLET))
    p.setBrush(QBrush(gt))
    p.drawPolygon(top)

    # ---- tiling split across the top face ----
    # One vertical gutter with a branch: a master pane on the left, two stacked
    # on the right. In isometric the axes run along the rhombus edges.
    if not tiny:
        lw = max(1.0, s * (0.026 if detail else 0.030))
        p.setPen(QPen(QColor(255, 255, 255, 205 if detail else 225), lw,
                      Qt.SolidLine, Qt.RoundCap))

        def iso(u: float, v: float) -> QPointF:
            """u across the width (-1..1), v along the depth (-1..1)."""
            return QPointF(cx + (u + v) * w * 0.5,
                           cy + (v - u) * hh * 0.5)

        # main gutter, front-left to back-right
        p.drawLine(iso(-0.08, -0.92), iso(-0.08, 0.92))
        if detail:
            # branch splitting the right side into two panes
            p.drawLine(iso(-0.08, 0.12), iso(0.92, 0.12))

    # ---- edge definition ----
    if not tiny:
        p.setPen(QPen(QColor(255, 255, 255, 96), max(1.0, s * 0.016)))
        p.drawLine(QPointF(cx - w, cy), QPointF(cx, cy - hh))
        p.drawLine(QPointF(cx, cy - hh), QPointF(cx + w, cy))
    # front vertical seam keeps the two side faces apart at any size
    p.setPen(QPen(QColor(0, 0, 0, 70), max(1.0, s * 0.018)))
    p.drawLine(QPointF(cx, cy + hh), QPointF(cx, cy + hh + d))

    # ---- state pip ----
    colour = STATE_COLORS.get(state or "")
    if colour and pip:
        r = s * 0.155
        c = QPointF(s - r - s * 0.055, s - r - s * 0.055)
        p.setPen(QPen(QColor(255, 255, 255, 230), max(1.0, s * 0.030)))
        p.setBrush(QBrush(QColor(colour)))
        p.drawEllipse(c, r, r)

    p.end()
    return pm


# --------------------------------------------------------------------------- #
def app_icon() -> QIcon:
    ic = QIcon()
    for n in (16, 20, 24, 32, 40, 48, 64, 96, 128, 256):
        ic.addPixmap(_draw(n))
    return ic


def tray_icon(state: str = "stopped") -> QIcon:
    ic = QIcon()
    for n in (16, 20, 24, 32, 48, 64):
        ic.addPixmap(_draw(n, state))
    return ic


def mark(size: int = 256) -> QPixmap:
    """The plain mark, for the splash and documentation."""
    return _draw(size)


def _png_bytes(pm: QPixmap) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    pm.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def write_ico(dest: Path, sizes=(16, 24, 32, 48, 64, 128, 256)) -> bool:
    """Multi-resolution .ico for the executable and shortcuts."""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    try:
        import io as _io
        from PIL import Image
        frames = [Image.open(_io.BytesIO(_png_bytes(_draw(n)))).convert("RGBA")
                  for n in sizes]
        frames[-1].save(dest, format="ICO",
                        sizes=[(f.width, f.height) for f in frames])
        return True
    except Exception:
        try:
            return bool(_draw(256).save(str(dest), "ICO"))
        except Exception:
            return False


def write_png(dest: Path, size: int = 512) -> bool:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        return bool(_draw(size).save(str(dest), "PNG"))
    except Exception:
        return False
