"""
Theme engine: light/dark/auto palettes, gradient surfaces, and Windows
translucency (Mica / Acrylic) with graceful fallbacks everywhere.
"""
from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette


# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    bg_alt: str
    panel: str
    card: str
    card_hi: str
    border: str
    text: str
    muted: str
    accent: str
    on_accent: str
    green: str
    amber: str
    red: str
    grad_a: str
    grad_b: str
    grad_c: str
    shadow: str
    focus: str


DARK = Palette(
    name="dark",
    bg="#0c0e14", bg_alt="#11141d",
    panel="#141827", card="#1a1e2d", card_hi="#222739",
    border="#2b3145",
    text="#e9ecf5", muted="#858caa",
    accent="#4f8cff", on_accent="#ffffff",
    green="#34d399", amber="#fbbf24", red="#f87171",
    grad_a="#151a2e", grad_b="#0d1018", grad_c="#1a1430",
    shadow="rgba(0,0,0,140)", focus="#7aa9ff",
)

LIGHT = Palette(
    name="light",
    bg="#f4f6fb", bg_alt="#eef1f8",
    panel="#ffffff", card="#ffffff", card_hi="#f0f3fa",
    border="#d8dee9",
    text="#141824", muted="#5c6480",
    accent="#2f6fe4", on_accent="#ffffff",
    green="#0f9d63", amber="#b8860b", red="#c53030",
    grad_a="#e8edfa", grad_b="#f7f9fd", grad_c="#efe9fb",
    shadow="rgba(20,30,60,38)", focus="#1d5fd0",
)


def system_prefers_dark() -> bool:
    """Read the Windows apps-theme preference; default dark if unknown."""
    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        winreg.CloseKey(k)
        return val == 0
    except Exception:
        return True


def resolve(mode: str) -> Palette:
    if mode == "light":
        return LIGHT
    if mode == "dark":
        return DARK
    return DARK if system_prefers_dark() else LIGHT


def high_contrast_active() -> bool:
    """Respect the OS high-contrast setting by dropping decorative effects."""
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


# --------------------------------------------------------------------------- #
#  Windows backdrop (Mica / Acrylic).  Silently no-ops on unsupported builds.
# --------------------------------------------------------------------------- #
def apply_backdrop(win, dark: bool, enabled: bool = True) -> bool:
    """
    Ask DWM for a translucent system backdrop behind the window.
    Returns True if the call was accepted.  Never raises.
    """
    if sys.platform != "win32" or not enabled:
        return False
    try:
        hwnd = int(win.winId())
        dwm = ctypes.windll.dwmapi

        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        DWMSBT_MAINWINDOW = 2          # Mica

        mode = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(mode), ctypes.sizeof(mode))

        backdrop = ctypes.c_int(DWMSBT_MAINWINDOW)
        res = dwm.DwmSetWindowAttribute(
            hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(backdrop), ctypes.sizeof(backdrop))
        return res == 0
    except Exception:
        return False


# --------------------------------------------------------------------------- #
def qpalette(p: Palette) -> QPalette:
    """A matching QPalette so native/unstyled widgets don't look wrong."""
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(p.bg))
    pal.setColor(QPalette.WindowText, QColor(p.text))
    pal.setColor(QPalette.Base, QColor(p.card))
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


def stylesheet(p: Palette, *, gradient: bool = True, translucent: bool = True,
               font_scale: int = 100, accent: str | None = None) -> str:
    """Build the full QSS.  All effects degrade to flat colour if disabled."""
    a = accent or p.accent
    hc = high_contrast_active()
    if hc:
        gradient = False
        translucent = False

    fs = max(80, min(160, font_scale)) / 100.0

    def px(n: float) -> str:
        return f"{max(9, round(n * fs))}px"

    # Root surface: gradient, optionally see-through so the Mica backdrop shows.
    if gradient:
        alpha = "0.86" if translucent else "1.0"
        root_bg = (
            f"qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {_rgba(p.grad_a, alpha)}, "
            f"stop:0.55 {_rgba(p.grad_b, alpha)}, "
            f"stop:1 {_rgba(p.grad_c, alpha)})"
        )
    else:
        root_bg = p.bg

    card_alpha = "0.72" if (translucent and gradient) else "1.0"
    panel_alpha = "0.60" if (translucent and gradient) else "1.0"

    border_w = "2px" if hc else "1px"

    return f"""
* {{
    font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Inter', sans-serif;
    font-size: {px(13)};
}}

QWidget#Root {{ background: {root_bg}; }}
QMainWindow {{ background: {p.bg}; }}
QWidget {{ color: {p.text}; background: transparent; }}

QToolTip {{
    background: {p.card}; color: {p.text};
    border: {border_w} solid {p.border}; border-radius: 6px; padding: 6px 9px;
}}

/* ---------- sidebar ---------- */
#Sidebar {{
    background: {_rgba(p.panel, panel_alpha)};
    border-right: {border_w} solid {p.border};
}}
#Brand    {{ font-size: {px(16)}; font-weight: 700; color: {p.text}; }}
#BrandSub {{ font-size: {px(11)}; color: {p.muted}; }}

QPushButton#Nav {{
    background: transparent; border: {border_w} solid transparent;
    border-radius: 9px; padding: 11px 14px; text-align: left;
    color: {p.muted}; font-size: {px(13)}; font-weight: 600;
}}
QPushButton#Nav:hover   {{ background: {_rgba(p.card_hi, '0.8')}; color: {p.text}; }}
QPushButton#Nav:checked {{
    background: {_rgba(a, '0.16')}; color: {p.text};
    border-color: {_rgba(a, '0.42')};
}}
QPushButton#Nav:focus {{ border-color: {p.focus}; outline: none; }}

/* ---------- cards ---------- */
#Card {{
    background: {_rgba(p.card, card_alpha)};
    border: {border_w} solid {p.border};
    border-radius: 14px;
}}
#CardTitle {{ font-size: {px(13)}; font-weight: 700; color: {p.text}; }}
#CardHint  {{ font-size: {px(11.5)}; color: {p.muted}; }}
#PageTitle {{ font-size: {px(23)}; font-weight: 700; color: {p.text}; }}
#PageSub   {{ font-size: {px(12)}; color: {p.muted}; }}
#StatBig   {{ font-size: {px(25)}; font-weight: 700; color: {p.text}; }}
#StatLabel {{ font-size: {px(10.5)}; color: {p.muted}; font-weight: 700;
             letter-spacing: 0.6px; }}
#Muted     {{ color: {p.muted}; }}

/* ---------- buttons ---------- */
QPushButton {{
    background: {_rgba(p.card_hi, '0.92')};
    border: {border_w} solid {p.border};
    border-radius: 9px; padding: 10px 16px;
    color: {p.text}; font-weight: 600; font-size: {px(13)};
    min-height: 18px;
}}
QPushButton:hover    {{ background: {_rgba(a, '0.16')}; border-color: {_rgba(a, '0.5')}; }}
QPushButton:pressed  {{ background: {_rgba(a, '0.28')}; }}
QPushButton:focus    {{ border-color: {p.focus}; outline: none; }}
QPushButton:disabled {{ color: {p.muted}; background: {_rgba(p.card, '0.5')}; }}

QPushButton#Primary {{
    background: {a}; border: {border_w} solid {a}; color: {p.on_accent};
}}
QPushButton#Primary:hover  {{ background: {_lighten(a, 14)}; border-color: {_lighten(a, 14)}; }}
QPushButton#Primary:pressed{{ background: {_darken(a, 10)}; }}
QPushButton#Primary:disabled {{
    background: {_rgba(a, '0.3')}; border-color: transparent; color: {_rgba(p.on_accent, '0.6')};
}}
QPushButton#Danger {{ background: {p.red}; border-color: {p.red}; color: #ffffff; }}
QPushButton#Danger:hover {{ background: {_lighten(p.red, 10)}; }}
QPushButton#Ghost {{ background: transparent; }}

/* ---------- inputs ---------- */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QSlider {{
    background: {_rgba(p.bg_alt, '0.92')};
    border: {border_w} solid {p.border}; border-radius: 9px;
    padding: 9px 11px; color: {p.text};
    selection-background-color: {a}; selection-color: {p.on_accent};
    min-height: 17px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {p.focus}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {p.muted}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {p.card}; border: {border_w} solid {p.border};
    border-radius: 8px; padding: 5px;
    selection-background-color: {a}; selection-color: {p.on_accent};
    color: {p.text};
}}
QPlainTextEdit, QTextEdit#Mono, QLabel#Cmd {{
    font-family: 'Cascadia Mono', 'Consolas', monospace;
    font-size: {px(12)};
}}
QLabel#Cmd {{
    background: {_rgba(p.bg_alt, '0.95')}; color: {p.green};
    border: {border_w} solid {p.border}; border-radius: 9px; padding: 12px;
}}

/* ---------- checkbox ---------- */
QCheckBox {{ spacing: 10px; color: {p.text}; padding: 3px 0; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 5px;
    border: {border_w} solid {p.border}; background: {p.bg_alt};
}}
QCheckBox::indicator:hover   {{ border-color: {a}; }}
QCheckBox::indicator:checked {{ background: {a}; border-color: {a}; }}
QCheckBox:focus {{ outline: none; }}

/* ---------- scrollbars ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 3px; }}
QScrollBar::handle:vertical {{
    background: {_rgba(p.muted, '0.42')}; border-radius: 5px; min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {_rgba(p.muted, '0.7')}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 3px; }}
QScrollBar::handle:horizontal {{
    background: {_rgba(p.muted, '0.42')}; border-radius: 5px; min-width: 32px;
}}

/* ---------- misc ---------- */
#Sep {{ background: {p.border}; max-height: 1px; border: none; }}
QMenu {{
    background: {p.card}; border: {border_w} solid {p.border};
    border-radius: 10px; padding: 6px;
}}
QMenu::item {{ padding: 8px 26px 8px 14px; border-radius: 7px; color: {p.text}; }}
QMenu::item:selected {{ background: {a}; color: {p.on_accent}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}
QProgressBar {{
    background: {p.bg_alt}; border: {border_w} solid {p.border};
    border-radius: 7px; height: 8px; text-align: center; color: {p.text};
}}
QProgressBar::chunk {{ background: {a}; border-radius: 6px; }}
"""


# --------------------------------------------------------------------------- #
def _rgba(hex_or_rgba: str, alpha: str) -> str:
    """Convert #rrggbb + alpha into an rgba() string; pass through rgba()."""
    if hex_or_rgba.startswith("rgba"):
        return hex_or_rgba
    try:
        c = QColor(hex_or_rgba)
        if not c.isValid():
            return hex_or_rgba
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"
    except Exception:
        return hex_or_rgba


def _lighten(hex_color: str, amount: int) -> str:
    try:
        c = QColor(hex_color)
        return c.lighter(100 + amount).name()
    except Exception:
        return hex_color


def _darken(hex_color: str, amount: int) -> str:
    try:
        c = QColor(hex_color)
        return c.darker(100 + amount).name()
    except Exception:
        return hex_color
