#!/usr/bin/env python3
"""Render the chosen icon at every shipped size and state, for review."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import QApplication

from archvm import icons

OUT = Path(__file__).resolve().parent.parent.parent / "docs" / "icons"
SIZES = [16, 20, 24, 32, 48, 64, 96, 128, 256]
STATES = [("stopped", "stopped"), ("running", "running"),
          ("busy", "busy"), ("error", "error")]


def sheet(dark: bool) -> QPixmap:
    W, H = 900, 470
    bg = "#12151f" if dark else "#eef2fb"
    fg = "#e9ecf5" if dark else "#101728"
    sub = "#8590b0" if dark else "#6b7692"

    cv = QPixmap(W, H)
    cv.fill(QColor(bg))
    p = QPainter(cv)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

    f = QFont("Segoe UI", 14); f.setBold(True)
    p.setFont(f); p.setPen(QColor(fg))
    p.drawText(24, 36, "ArchVM  —  isometric mark")
    f2 = QFont("Segoe UI", 9)
    p.setFont(f2); p.setPen(QColor(sub))
    p.drawText(24, 55, "detail drops out with size so it stays readable small  ·  "
                       + ("dark" if dark else "light"))

    # size ladder
    x, base = 28, 90
    p.setPen(QColor(fg)); p.setFont(f2)
    p.drawText(24, base - 12, "application icon")
    for n in SIZES:
        pm = icons._draw(n)
        p.drawPixmap(x, base + (128 - n), pm)
        p.setPen(QColor(sub))
        p.drawText(QRectF(x, base + 134, max(n, 26), 14),
                   Qt.AlignLeft, f"{n}")
        x += max(n, 26) + 16

    # tray states
    y2 = base + 190
    p.setPen(QColor(fg)); p.setFont(f2)
    p.drawText(24, y2 - 12, "tray states (16 / 24 / 32 / 48 px)")
    x = 28
    for state, label in STATES:
        for n in (16, 24, 32, 48):
            p.drawPixmap(x, y2 + (48 - n), icons._draw(n, state))
            x += n + 8
        p.setPen(QColor(sub))
        p.drawText(QRectF(x - 130, y2 + 56, 130, 14), Qt.AlignLeft, label)
        p.setPen(QColor(fg))
        x += 34

    # 1:1 pixel view of the small sizes, magnified with no smoothing
    y3 = y2 + 100
    p.setPen(QColor(fg))
    p.drawText(24, y3 - 12, "16 and 24 px magnified 6x (no smoothing)")
    x = 28
    for n in (16, 24):
        pm = icons._draw(n)
        big = pm.scaled(n * 6, n * 6, Qt.KeepAspectRatio, Qt.FastTransformation)
        p.drawPixmap(x, y3, big)
        x += n * 6 + 26
    p.end()
    return cv


def main() -> int:
    QApplication.instance() or QApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    sheet(False).save(str(OUT / "mark-light.png"), "PNG")
    sheet(True).save(str(OUT / "mark-dark.png"), "PNG")
    icons.write_png(OUT / "mark-512.png", 512)
    ok = icons.write_ico(OUT / "archvm.ico")
    print(f"  ico written: {ok}", flush=True)
    print(f"  sheets -> {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
