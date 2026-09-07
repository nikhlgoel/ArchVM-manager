"""
Theme engine.

The default is a light, blue-toned scheme drawn from the application icon's
own gradient (#5b8cff -> #8b5cf6). Depth comes from a painted backdrop —
layered radial blooms, a fine noise grain and a soft vignette — rather than
from flat fills, so surfaces read as glass sitting above a lit surface.

Every effect degrades: Windows Mica when available, a painted gradient when
not, and flat colour under high contrast.
"""
from __future__ import annotations

import ctypes
import math
import random
import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QColor, QPalette, QPixmap, QPainter, QRadialGradient, QLinearGradient,
    QBrush, QImage,
)

# Brand gradient, taken from the icon.
BRAND_A = "#5b8cff"
BRAND_B = "#8b5cf6"


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    bg_alt: str
    panel: str
    card: str
    card_hi: str
    border: str
    border_soft: str
    text: str
    text_soft: str
    muted: str
    accent: str
    accent_soft: str
    on_accent: str
    green: str
    amber: str
    red: str
    shadow: str
    focus: str
    # backdrop bloom colours
    bloom_a: str
    bloom_b: str
    bloom_c: str
    base: str


LIGHT = Palette(
    name="light",
    bg="#eef2fb", bg_alt="#f7f9ff",
    panel="#ffffff", card="#ffffff", card_hi="#f2f6ff",
    border="#d3ddf0", border_soft="#e4ebf8",
    text="#101728", text_soft="#33405c", muted="#6b7692",
    accent="#3b74e8", accent_soft="#dce7ff", on_accent="#ffffff",
    green="#0e9f6e", amber="#b45309", red="#dc2626",
    shadow="#8fa3c8", focus="#1f5fd8",
    bloom_a="#7aa5ff", bloom_b="#b79bff", bloom_c="#8fd8ff",
    base="#e9eefb",
)

DARK = Palette(
    name="dark",
    bg="#0b0e17", bg_alt="#121727",
    panel="#141a2b", card="#182034", card_hi="#1f2942",
    border="#2a3552", border_soft="#222c46",
    text="#eaeefb", text_soft="#c3cbe4", muted="#8590b0",
    accent="#5b8cff", accent_soft="#1c2a4d", on_accent="#ffffff",
    green="#34d399", amber="#fbbf24", red="#f87171",
    shadow="#000000", focus="#7aa9ff",
    bloom_a="#2d4a9e", bloom_b="#4c2f8f", bloom_c="#12507a",
    base="#0b0e17",
)


# --------------------------------------------------------------------------- #
def system_prefers_dark() -> bool:
    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        winreg.CloseKey(k)
        return val == 0
    except Exception:
        return False          # light is this app's house style


def resolve(mode: str) -> Palette:
    if mode == "dark":
        return DARK
    if mode == "light":
        return LIGHT
    return DARK if system_prefers_dark() else LIGHT


def high_contrast_active() -> bool:
    try:
        SPI_GETHIGHCONTRAST = 0x0042

        class HIGHCONTRAST(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint),
                        ("dwFlags", ctypes.c_uint),
                        ("lpszDefaultScheme", ctypes.c_wchar_p)]

        hc = HIGHCONTRAST()
        hc.cbSize = ctypes.sizeof(HIGHCONTRAST)
        if ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETHIGHCONTRAST, hc.cbSize, ctypes.byref(hc), 0):
            return bool(hc.dwFlags & 0x00000001)
    except Exception:
        pass
    return False


def accent_from_windows() -> str | None:
    """The user's Windows accent colour, if they want the app to follow it."""
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent")
        val, _ = winreg.QueryValueEx(k, "AccentColorMenu")
        winreg.CloseKey(k)
        # stored ABGR
        b = (val >> 16) & 0xFF
        g = (val >> 8) & 0xFF
        r = val & 0xFF
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return None


# --------------------------------------------------------------------------- #
#  Painted backdrop
# --------------------------------------------------------------------------- #
_noise_cache: dict[tuple[int, str], QPixmap] = {}


def _noise_tile(size: int, colour: str, strength: int) -> QPixmap:
    """A tileable grain texture. Cached — regenerating this per paint is slow."""
    key = (size, f"{colour}{strength}")
    if key in _noise_cache:
        return _noise_cache[key]
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    base = QColor(colour)
    rnd = random.Random(0xA5C1)          # fixed seed: stable across repaints
    for y in range(size):
        for x in range(size):
            a = rnd.randint(0, strength)
            if a:
                img.setPixelColor(x, y, QColor(base.red(), base.green(),
                                               base.blue(), a))
    pm = QPixmap.fromImage(img)
    _noise_cache[key] = pm
    return pm


def paint_backdrop(painter: QPainter, rect: QRectF, pal: Palette, *,
                   depth: bool = True, grain: bool = True) -> None:
    """
    Draw the layered background: base wash, three soft blooms, a fine grain,
    and a vignette. Called from a widget's paintEvent.
    """
    painter.setRenderHint(QPainter.Antialiasing, True)
    w, h = rect.width(), rect.height()
    if w <= 0 or h <= 0:
        return

    # 1. base vertical wash
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0.0, QColor(pal.bg_alt))
    g.setColorAt(1.0, QColor(pal.base))
    painter.fillRect(rect, QBrush(g))

    if not depth:
        return

    # 2. blooms — large, low-opacity radial gradients that give the surface
    #    a sense of being lit from a few directions
    blooms = (
        (0.14, -0.05, 0.78, pal.bloom_a, 74),
        (1.02, 0.28, 0.72, pal.bloom_b, 60),
        (0.52, 1.10, 0.85, pal.bloom_c, 46),
    )
    painter.save()
    painter.setPen(Qt.NoPen)
    for fx, fy, fr, colour, alpha in blooms:
        cx = rect.left() + w * fx
        cy = rect.top() + h * fy
        radius = max(w, h) * fr
        rg = QRadialGradient(QPointF(cx, cy), radius)
        c0 = QColor(colour); c0.setAlpha(alpha)
        c1 = QColor(colour); c1.setAlpha(0)
        rg.setColorAt(0.0, c0)
        rg.setColorAt(1.0, c1)
        painter.setBrush(QBrush(rg))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)
    painter.restore()

    # 3. grain — breaks up the banding that large gradients produce
    if grain:
        strength = 10 if pal.name == "light" else 14
        tile = _noise_tile(64, "#000000" if pal.name == "light" else "#ffffff",
                           strength)
        painter.save()
        painter.setOpacity(0.5)
        painter.drawTiledPixmap(rect, tile)
        painter.restore()

    # 4. vignette — settles the edges so cards float
    vg = QRadialGradient(rect.center(), max(w, h) * 0.78)
    v0 = QColor(pal.shadow); v0.setAlpha(0)
    v1 = QColor(pal.shadow); v1.setAlpha(30 if pal.name == "light" else 70)
    vg.setColorAt(0.55, v0)
    vg.setColorAt(1.0, v1)
    painter.fillRect(rect, QBrush(vg))


# --------------------------------------------------------------------------- #
def apply_backdrop(win, dark: bool, enabled: bool = True) -> bool:
    """Windows Mica behind the window. Silently no-ops where unsupported."""
    if sys.platform != "win32" or not enabled:
        return False
    try:
        hwnd = int(win.winId())
        dwm = ctypes.windll.dwmapi
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        DWMSBT_MAINWINDOW = 2

        mode = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                                  ctypes.byref(mode), ctypes.sizeof(mode))
        backdrop = ctypes.c_int(DWMSBT_MAINWINDOW)
        return dwm.DwmSetWindowAttribute(
            hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(backdrop), ctypes.sizeof(backdrop)) == 0
    except Exception:
        return False


def qpalette(p: Palette) -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(p.bg))
    pal.setColor(QPalette.WindowText, QColor(p.text))
    pal.setColor(QPalette.Base, QColor(p.bg_alt))
    pal.setColor(QPalette.AlternateBase, QColor(p.card_hi))
    pal.setColor(QPalette.Text, QColor(p.text))
    pal.setColor(QPalette.Button, QColor(p.card_hi))
    pal.setColor(QPalette.ButtonText, QColor(p.text))
    pal.setColor(QPalette.Highlight, QColor(p.accent))
    pal.setColor(QPalette.HighlightedText, QColor(p.on_accent))
    pal.setColor(QPalette.ToolTipBase, QColor(p.card))
    pal.setColor(QPalette.ToolTipText, QColor(p.text))
    pal.setColor(QPalette.PlaceholderText, QColor(p.muted))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(p.muted))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(p.muted))
    return pal


# --------------------------------------------------------------------------- #
def stylesheet(p: Palette, *, gradient: bool = True, translucent: bool = True,
               font_scale: int = 100, accent: str | None = None) -> str:
    a = accent or p.accent
    hc = high_contrast_active()
    if hc:
        gradient = translucent = False

    fs = max(80, min(160, font_scale)) / 100.0

    def px(n: float) -> str:
        return f"{max(9, round(n * fs))}px"

    glass = "0.74" if (translucent and gradient) else "1.0"
    rail = "0.66" if (translucent and gradient) else "1.0"
    bw = "2px" if hc else "1px"

    # A hairline highlight along the top of raised surfaces is what sells
    # depth on a light theme; shadows alone read as dirt.
    return f"""
* {{
    font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Inter', sans-serif;
    font-size: {px(13)};
}}
QWidget {{ color: {p.text}; background: transparent; }}
QMainWindow, QDialog {{ background: {p.bg}; }}
QWidget#Root, QWidget#Backdrop {{ background: transparent; }}

QToolTip {{
    background: {p.card}; color: {p.text};
    border: {bw} solid {p.border}; border-radius: 8px; padding: 7px 10px;
}}

/* ---------------- sidebar ---------------- */
#Sidebar {{
    background: {_rgba(p.panel, rail)};
    border-right: {bw} solid {p.border_soft};
}}
#Brand    {{ font-size: {px(16.5)}; font-weight: 800; color: {p.text};
             letter-spacing: -0.2px; }}
#BrandSub {{ font-size: {px(11)}; color: {p.muted}; }}

QPushButton#Nav {{
    background: transparent; border: {bw} solid transparent;
    border-radius: 10px; padding: 11px 13px; text-align: left;
    color: {p.text_soft}; font-size: {px(13)}; font-weight: 600;
}}
QPushButton#Nav:hover {{
    background: {_rgba(p.card_hi, '0.95')}; color: {p.text};
    border-color: {p.border_soft};
}}
QPushButton#Nav:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {_rgba(a, '0.18')}, stop:1 {_rgba(BRAND_B, '0.10')});
    color: {p.text}; border-color: {_rgba(a, '0.34')}; font-weight: 700;
}}
QPushButton#Nav:focus {{ border-color: {p.focus}; outline: none; }}

/* ---------------- cards ---------------- */
#Card {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {_rgba(p.card, glass)},
        stop:1 {_rgba(p.card_hi, glass)});
    border: {bw} solid {p.border_soft};
    border-top: {bw} solid {_rgba('#ffffff', '0.9' if p.name == 'light' else '0.10')};
    border-radius: 16px;
}}
#CardFlat {{
    background: {_rgba(p.card, glass)};
    border: {bw} solid {p.border_soft}; border-radius: 14px;
}}
#Hero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {_rgba(a, '0.16')},
        stop:0.55 {_rgba(BRAND_B, '0.10')},
        stop:1 {_rgba(p.bloom_c, '0.12')});
    border: {bw} solid {_rgba(a, '0.26')};
    border-radius: 18px;
}}
#CardTitle {{ font-size: {px(13.5)}; font-weight: 700; color: {p.text}; }}
#CardHint  {{ font-size: {px(11.5)}; color: {p.muted}; }}
#PageTitle {{ font-size: {px(25)}; font-weight: 800; color: {p.text};
              letter-spacing: -0.4px; }}
#PageSub   {{ font-size: {px(12.5)}; color: {p.muted}; }}
#StatBig   {{ font-size: {px(26)}; font-weight: 800; color: {p.text};
              letter-spacing: -0.5px; }}
#StatLabel {{ font-size: {px(10)}; color: {p.muted}; font-weight: 700;
              letter-spacing: 0.8px; }}
#Muted     {{ color: {p.muted}; }}
#Divider   {{ background: {p.border_soft}; max-height: 1px; border: none; }}

/* ---------------- buttons ---------------- */
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {_rgba('#ffffff', '0.96' if p.name == 'light' else '0.05')},
        stop:1 {_rgba(p.card_hi, '0.98')});
    border: {bw} solid {p.border};
    border-radius: 10px; padding: 10px 17px;
    color: {p.text}; font-weight: 650; font-size: {px(13)};
    min-height: 18px;
}}
QPushButton:hover {{
    background: {_rgba(a, '0.10')}; border-color: {_rgba(a, '0.45')};
    color: {p.text};
}}
QPushButton:pressed  {{ background: {_rgba(a, '0.20')}; }}
QPushButton:focus    {{ border-color: {p.focus}; outline: none; }}
QPushButton:disabled {{
    color: {p.muted}; background: {_rgba(p.card_hi, '0.5')};
    border-color: {p.border_soft};
}}

QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {a}, stop:1 {BRAND_B});
    border: {bw} solid {_rgba(a, '0.85')};
    color: {p.on_accent}; font-weight: 700;
}}
QPushButton#Primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {_lighten(a, 12)}, stop:1 {_lighten(BRAND_B, 12)});
}}
QPushButton#Primary:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {_darken(a, 12)}, stop:1 {_darken(BRAND_B, 12)});
}}
QPushButton#Primary:disabled {{
    background: {_rgba(a, '0.32')}; border-color: transparent;
    color: {_rgba(p.on_accent, '0.75')};
}}
QPushButton#Danger {{
    background: {p.red}; border-color: {_darken(p.red, 8)}; color: #ffffff;
}}
QPushButton#Danger:hover {{ background: {_lighten(p.red, 10)}; }}
QPushButton#Ghost {{
    background: transparent; border-color: transparent; color: {p.muted};
    font-weight: 600;
}}
QPushButton#Ghost:hover {{ color: {p.text}; background: {_rgba(p.card_hi, '0.9')}; }}

/* ---------------- inputs ---------------- */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {_rgba(p.bg_alt, '0.96')};
    border: {bw} solid {p.border}; border-radius: 10px;
    padding: 9px 11px; color: {p.text};
    selection-background-color: {a}; selection-color: {p.on_accent};
    min-height: 17px;
}}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{ border-color: {_rgba(a, '0.5')}; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {p.focus}; background: {p.panel};
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {p.panel}; border: {bw} solid {p.border};
    border-radius: 10px; padding: 5px; outline: none;
    selection-background-color: {a}; selection-color: {p.on_accent};
    color: {p.text};
}}
QPlainTextEdit, QTextEdit#Mono {{
    font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: {px(12)};
    background: {_rgba(p.bg_alt, '0.98')};
}}
QLabel#Cmd {{
    font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: {px(12)};
    background: {_rgba(p.bg_alt, '0.98')}; color: {p.text};
    border: {bw} solid {p.border}; border-left: 3px solid {a};
    border-radius: 10px; padding: 12px 14px;
}}
QLabel#Chip {{
    background: {_rgba(a, '0.14')}; color: {_darken(a, 12) if p.name == 'light' else a};
    border: {bw} solid {_rgba(a, '0.30')};
    border-radius: 9px; padding: 4px 10px;
    font-size: {px(11)}; font-weight: 700;
}}

/* ---------------- checkbox / slider ---------------- */
QCheckBox {{ spacing: 10px; color: {p.text}; padding: 3px 0; }}
QCheckBox::indicator {{
    width: 19px; height: 19px; border-radius: 6px;
    border: {bw} solid {p.border}; background: {p.panel};
}}
QCheckBox::indicator:hover   {{ border-color: {a}; }}
QCheckBox::indicator:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {a}, stop:1 {BRAND_B});
    border-color: {a};
}}
QSlider::groove:horizontal {{
    height: 6px; border-radius: 3px; background: {p.border_soft};
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {a}, stop:1 {BRAND_B});
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {p.panel}; border: 2px solid {a};
    width: 15px; height: 15px; margin: -6px 0; border-radius: 9px;
}}
QSlider::handle:horizontal:hover {{ border-color: {BRAND_B}; }}

/* ---------------- scrollbars ---------------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 3px; }}
QScrollBar::handle:vertical {{
    background: {_rgba(p.muted, '0.38')}; border-radius: 5px; min-height: 34px;
}}
QScrollBar::handle:vertical:hover {{ background: {_rgba(a, '0.6')}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 3px; }}
QScrollBar::handle:horizontal {{
    background: {_rgba(p.muted, '0.38')}; border-radius: 5px; min-width: 34px;
}}

/* ---------------- menus / progress ---------------- */
QMenu {{
    background: {p.panel}; border: {bw} solid {p.border};
    border-radius: 12px; padding: 6px;
}}
QMenu::item {{ padding: 8px 28px 8px 14px; border-radius: 8px; color: {p.text}; }}
QMenu::item:selected {{ background: {a}; color: {p.on_accent}; }}
QMenu::item:disabled {{ color: {p.muted}; }}
QMenu::separator {{ height: 1px; background: {p.border_soft}; margin: 5px 8px; }}
QProgressBar {{
    background: {p.border_soft}; border: none;
    border-radius: 6px; height: 10px; text-align: center;
    color: {p.text}; font-size: {px(10)};
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {a}, stop:1 {BRAND_B});
    border-radius: 6px;
}}
"""


# --------------------------------------------------------------------------- #
def _rgba(colour: str, alpha: str) -> str:
    if colour.startswith("rgba"):
        return colour
    try:
        c = QColor(colour)
        if not c.isValid():
            return colour
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"
    except Exception:
        return colour


def _lighten(colour: str, amount: int) -> str:
    try:
        return QColor(colour).lighter(100 + amount).name()
    except Exception:
        return colour


def _darken(colour: str, amount: int) -> str:
    try:
        return QColor(colour).darker(100 + amount).name()
    except Exception:
        return colour
