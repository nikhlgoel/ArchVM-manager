"""
Application iconography, drawn with QPainter so it stays crisp at every size
and needs no external image files.

The mark: a rounded-square "chip" with a blue->violet gradient, a white Arch
chevron, and a small status pip. Tray variants recolour the pip so VM state is
readable at 16px.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QLinearGradient, QPainterPath, QBrush, QPen,
)

GRAD_TOP = "#5b8cff"
GRAD_BOT = "#8b5cf6"

STATE_COLORS = {
    "stopped": "#8b93ad",
    "running": "#34d399",
    "busy": "#fbbf24",
    "error": "#f87171",
    None: None,
}


def _draw(size: int, state: str | None = None, *, mono: bool = False) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

    s = float(size)
    margin = s * 0.055
    body = QRectF(margin, margin, s - margin * 2, s - margin * 2)
    radius = s * 0.235

    # chip body
    path = QPainterPath()
    path.addRoundedRect(body, radius, radius)
    if mono:
        p.fillPath(path, QBrush(QColor("#ffffff")))
    else:
        g = QLinearGradient(body.topLeft(), body.bottomRight())
        g.setColorAt(0.0, QColor(GRAD_TOP))
        g.setColorAt(1.0, QColor(GRAD_BOT))
        p.fillPath(path, QBrush(g))

        # subtle top sheen
        sheen = QLinearGradient(body.topLeft(), QPointF(body.left(), body.center().y()))
        sheen.setColorAt(0.0, QColor(255, 255, 255, 54))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(sheen))

        # hairline
        p.setPen(QPen(QColor(255, 255, 255, 46), max(1.0, s * 0.012)))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(body, radius, radius)

    # Arch chevron
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
    p.fillPath(chev, QBrush(QColor("#0d1020" if mono else "#ffffff")))

    # state pip
    col = STATE_COLORS.get(state)
    if col and size >= 20:
        d = s * 0.30
        pip = QRectF(s - d - margin * 0.6, s - d - margin * 0.6, d, d)
        p.setPen(QPen(QColor(13, 16, 32, 210), max(1.0, s * 0.028)))
        p.setBrush(QBrush(QColor(col)))
        p.drawEllipse(pip)

    p.end()
    return pm


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


def _png_bytes(pm) -> bytes:
    """QPixmap -> PNG bytes, without touching the filesystem."""
    from PySide6.QtCore import QBuffer, QByteArray
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    pm.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def write_ico(dest: Path, sizes=(16, 24, 32, 48, 64, 128, 256)) -> bool:
    """
    Write a multi-resolution .ico for the executable and shortcuts.
    Uses Pillow when available; falls back to Qt's single-size writer.
    """
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
