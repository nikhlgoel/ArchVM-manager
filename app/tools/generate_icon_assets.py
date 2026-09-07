#!/usr/bin/env python3
"""
Generate the complete official icon and brand asset suite for ArchVM.

Produces:
  - High-resolution marks: 16, 24, 32, 48, 64, 96, 128, 256, 512, 1024 px PNGs
  - Windows multi-resolution .ico bundles (16..256 px)
  - System tray state icons (stopped, running, busy, error)
  - Monochrome / high-contrast icons
  - Dark and Light themed badges for store and documentation
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
    QPixmap, QPainter, QColor, QLinearGradient, QPainterPath, QBrush, QPen,
)
from PySide6.QtWidgets import QApplication

from archvm import icons

APP_DIR = ROOT
ASSETS_DIR = APP_DIR / "assets"
DOCS_ICONS = APP_DIR.parent / "docs" / "icons"
SUITE_DIR = ASSETS_DIR / "icon_suite"


def save_pixmap(pm: QPixmap, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    return pm.save(str(dest), "PNG")


def render_badge(size: int, dark: bool = True) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

    s = float(size)
    bg = "#12151f" if dark else "#f4f6fb"
    border = "#252b3d" if dark else "#dce1ee"

    # Rounded card
    m = s * 0.05
    rect = QRectF(m, m, s - m * 2, s - m * 2)
    radius = s * 0.22
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    p.fillPath(path, QBrush(QColor(bg)))
    p.setPen(QPen(QColor(border), max(1.0, s * 0.015)))
    p.drawPath(path)

    # Center mark
    mark_s = int(s * 0.72)
    mark_pm = icons._draw(mark_s)
    offset = (s - mark_s) / 2.0
    p.drawPixmap(int(offset), int(offset), mark_pm)
    p.end()
    return pm


def main() -> int:
    app = QApplication.instance() or QApplication([])

    print("Generating ArchVM Official Icon & Asset Suite...\n")
    for d in (ASSETS_DIR, DOCS_ICONS, SUITE_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # 1. Standard PNG sizes
    sizes = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256, 512, 1024)
    print("  [1/5] Rendering standard mark resolutions...")
    for sz in sizes:
        pm = icons._draw(sz)
        # Save to assets/icon_suite
        save_pixmap(pm, SUITE_DIR / f"archvm-{sz}.png")
        # Save primary sizes to docs/icons and app/assets
        if sz in (16, 32, 48, 64, 128, 256, 512, 1024):
            save_pixmap(pm, DOCS_ICONS / f"mark-{sz}.png")
        if sz == 512:
            save_pixmap(pm, ASSETS_DIR / "archvm.png")
            save_pixmap(pm, DOCS_ICONS / "mark-512.png")
    print(f"        Saved {len(sizes)} resolutions to {SUITE_DIR}")

    # 2. State variants for tray and status
    print("  [2/5] Rendering tray & notification state variants...")
    for state in ("stopped", "running", "busy", "error"):
        for sz in (16, 24, 32, 64):
            pm = icons._draw(sz, state=state)
            save_pixmap(pm, SUITE_DIR / f"state-{state}-{sz}.png")
            if sz == 64:
                save_pixmap(pm, DOCS_ICONS / f"state-{state}.png")

    # 3. Monochrome / High Contrast
    print("  [3/5] Rendering monochrome & high-contrast assets...")
    for sz in (16, 32, 64, 128, 256):
        pm = icons._draw(sz, mono=True)
        save_pixmap(pm, SUITE_DIR / f"archvm-mono-{sz}.png")
        if sz == 256:
            save_pixmap(pm, DOCS_ICONS / "mark-mono.png")

    # 4. Themed Badges
    print("  [4/5] Rendering branded store & presentation badges...")
    dark_badge = render_badge(512, dark=True)
    light_badge = render_badge(512, dark=False)
    save_pixmap(dark_badge, DOCS_ICONS / "badge-dark-512.png")
    save_pixmap(light_badge, DOCS_ICONS / "badge-light-512.png")
    save_pixmap(dark_badge, SUITE_DIR / "badge-dark-512.png")
    save_pixmap(light_badge, SUITE_DIR / "badge-light-512.png")

    # 5. Multi-resolution Windows .ico
    print("  [5/5] Packaging multi-resolution Windows .ico...")
    ico_path = ASSETS_DIR / "archvm.ico"
    icons.write_ico(ico_path)
    icons.write_ico(DOCS_ICONS / "archvm.ico")
    icons.write_ico(SUITE_DIR / "archvm.ico")
    print(f"        Generated multi-layer .ico at {ico_path}")

    print("\nAsset suite generation complete! All assets synchronized.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
