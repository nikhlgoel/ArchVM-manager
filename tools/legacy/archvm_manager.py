#!/usr/bin/env python3
"""
ArchVM Manager - control panel for the Arch Linux + Hyprland QEMU VM.

virt-manager is Linux-only, so this fills the gap on Windows: hardware config,
install/run modes, host->guest text injection, SSH, snapshots and live logs.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QTimer, Signal, QObject, QSize
from PySide6.QtGui import QIcon, QTextCursor, QFont, QPainter, QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QLineEdit, QPlainTextEdit,
    QMessageBox, QTabWidget, QFormLayout, QCheckBox, QFrame, QInputDialog,
    QStackedWidget, QButtonGroup, QSizePolicy, QScrollArea, QTextEdit,
)

BASE = Path(__file__).resolve().parent.parent
QEMU_DIR = Path(r"C:\Program Files\qemu")
QEMU = QEMU_DIR / "qemu-system-x86_64.exe"
QEMU_IMG = QEMU_DIR / "qemu-img.exe"
CONFIG = BASE / "manager" / "config.json"
SEED_DIR = BASE / "seed"

INSTALL_CMD = "mkdir -p /s && mount /dev/sr1 /s && bash /s/bootstrap.sh"

# --------------------------------------------------------------------------- #
#  Design tokens
# --------------------------------------------------------------------------- #
BG        = "#0d0e13"
PANEL     = "#141621"
CARD      = "#1a1d2a"
CARD_HI   = "#212436"
BORDER    = "#282c3d"
TEXT      = "#e9ecf5"
MUTED     = "#7e849b"
ACCENT    = "#4f8cff"
GREEN     = "#34d399"
AMBER     = "#fbbf24"
RED       = "#f87171"


# --------------------------------------------------------------------------- #
#  QEMU monitor - lets us type into the guest (there is no clipboard channel)
# --------------------------------------------------------------------------- #
KEYMAP = {
    " ": "spc", "\n": "ret", "\r": "ret", "\t": "tab",
    "-": "minus", "_": "shift-minus", "=": "equal", "+": "shift-equal",
    "[": "bracket_left", "{": "shift-bracket_left",
    "]": "bracket_right", "}": "shift-bracket_right",
    ";": "semicolon", ":": "shift-semicolon",
    "'": "apostrophe", '"': "shift-apostrophe",
    "`": "grave_accent", "~": "shift-grave_accent",
    "\\": "backslash", "|": "shift-backslash",
    ",": "comma", "<": "shift-comma",
    ".": "dot", ">": "shift-dot",
    "/": "slash", "?": "shift-slash",
    "!": "shift-1", "@": "shift-2", "#": "shift-3", "$": "shift-4",
    "%": "shift-5", "^": "shift-6", "&": "shift-7", "*": "shift-8",
    "(": "shift-9", ")": "shift-0",
}


def char_to_key(ch: str) -> str | None:
    if ch in KEYMAP:
        return KEYMAP[ch]
    if ch.isdigit():
        return ch
    if "a" <= ch <= "z":
        return ch
    if "A" <= ch <= "Z":
        return f"shift-{ch.lower()}"
    return None


class Monitor(QObject):
    """Talks HMP to QEMU over TCP so we can inject keystrokes."""
    progress = Signal(int, int)
    done = Signal(str)

    def __init__(self, port: int):
        super().__init__()
        self.port = port

    def type_text(self, text: str) -> None:
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, text: str) -> None:
        keys, skipped = [], 0
        for ch in text:
            k = char_to_key(ch)
            if k:
                keys.append(k)
            else:
                skipped += 1
        if not keys:
            self.done.emit("Nothing typeable in that text.")
            return
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=4) as s:
                s.settimeout(2.0)
                try:
                    s.recv(8192)          # monitor banner
                except socket.timeout:
                    pass
                for i, k in enumerate(keys):
                    s.sendall(f"sendkey {k}\n".encode())
                    # QEMU drops keys if pushed too fast
                    time.sleep(0.012)
                    if i % 16 == 0:
                        self.progress.emit(i, len(keys))
                time.sleep(0.2)
            msg = f"Typed {len(keys)} characters into the VM."
            if skipped:
                msg += f"  ({skipped} unsupported character(s) skipped.)"
            self.done.emit(msg)
        except OSError as e:
            self.done.emit(f"Could not reach the QEMU monitor on port {self.port}: {e}")


# --------------------------------------------------------------------------- #
#  Config
# --------------------------------------------------------------------------- #
@dataclass
class VMConfig:
    name: str = "Arch Hyprland"
    memory_mb: int = 8192
    cpus: int = 8
    disk: str = str(BASE / "disks" / "arch-hyprland.qcow2")
    iso: str = str(BASE / "iso" / "archlinux-x86_64.iso")
    seed_iso: str = str(BASE / "iso" / "seed.iso")
    ovmf_code: str = str(BASE / "disks" / "OVMF_CODE.fd")
    ovmf_vars: str = str(BASE / "disks" / "OVMF_VARS.fd")
    display: str = "gtk,gl=on"
    gpu: str = "virtio-vga-gl"
    width: int = 1920
    height: int = 1080
    accel: str = "whpx"
    cpu_model: str = "max"
    ssh_port: int = 2222
    monitor_port: int = 55555
    fullscreen: bool = True
    audio: bool = True
    keyboard: str = "ps2"          # ps2 | usb  (virtio drops shifted symbols)
    keymap: str = "en-us"
    username: str = "arch"

    @classmethod
    def load(cls) -> "VMConfig":
        if CONFIG.exists():
            try:
                data = json.loads(CONFIG.read_text(encoding="utf-8"))
                known = set(cls.__dataclass_fields__)
                return cls(**{k: v for k, v in data.items() if k in known})
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    def build_args(self, install_mode: bool) -> list[str]:
        a: list[str] = [
            "-name", self.name,
            "-machine", f"q35,accel={self.accel},kernel-irqchip=off",
            "-cpu", self.cpu_model,
            "-smp", str(self.cpus),
            "-m", str(self.memory_mb),
            "-rtc", "base=localtime",
            "-k", self.keymap,
        ]

        if Path(self.ovmf_code).exists():
            a += ["-drive", f"if=pflash,format=raw,readonly=on,file={self.ovmf_code}"]
        if Path(self.ovmf_vars).exists():
            a += ["-drive", f"if=pflash,format=raw,file={self.ovmf_vars}"]

        a += [
            "-drive", f"id=hd0,if=none,file={self.disk},format=qcow2,"
                      f"cache=writeback,discard=unmap",
            "-device", f"virtio-blk-pci,drive=hd0,bootindex={2 if install_mode else 1}",
        ]

        if install_mode:
            a += [
                "-drive", f"id=cd0,if=none,media=cdrom,file={self.iso}",
                "-device", "ide-cd,drive=cd0,bus=ide.0,bootindex=1",
                "-drive", f"id=cd1,if=none,media=cdrom,file={self.seed_iso}",
                "-device", "ide-cd,drive=cd1,bus=ide.1",
            ]

        a += [
            "-device", f"{self.gpu},xres={self.width},yres={self.height}",
            "-display", self.display,
        ]
        if self.fullscreen:
            a += ["-full-screen"]

        a += [
            "-netdev", f"user,id=n0,hostfwd=tcp::{self.ssh_port}-:22",
            "-device", "virtio-net-pci,netdev=n0",
        ]

        # Input.  A USB tablet gives an absolute pointer (no mouse grab).
        # The keyboard is deliberately NOT virtio: virtio-keyboard mistranslates
        # shifted symbols (Shift+0 etc) and can leave modifiers stuck on the host.
        a += ["-device", "qemu-xhci,id=xhci",
              "-device", "usb-tablet,bus=xhci.0"]
        if self.keyboard == "usb":
            a += ["-device", "usb-kbd,bus=xhci.0"]
        # ps2: QEMU's built-in i8042 keyboard, added automatically - most reliable

        if self.audio:
            a += ["-audiodev", "dsound,id=snd0",
                  "-device", "ich9-intel-hda",
                  "-device", "hda-duplex,audiodev=snd0"]

        # HMP monitor - used by "Send text to VM"
        a += ["-monitor", f"tcp:127.0.0.1:{self.monitor_port},server=on,wait=off"]

        return a


# --------------------------------------------------------------------------- #
#  Styling
# --------------------------------------------------------------------------- #
STYLE = f"""
* {{ font-family: 'Segoe UI Variable Display', 'Segoe UI', sans-serif; }}
QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; }}

#Sidebar {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
#Brand   {{ font-size: 15px; font-weight: 700; color: {TEXT}; }}
#BrandSub{{ font-size: 11px; color: {MUTED}; }}

QPushButton#Nav {{
    background: transparent; border: none; border-radius: 8px;
    padding: 10px 14px; text-align: left; color: {MUTED};
    font-size: 13px; font-weight: 600;
}}
QPushButton#Nav:hover   {{ background: {CARD}; color: {TEXT}; }}
QPushButton#Nav:checked {{ background: {CARD_HI}; color: {TEXT}; }}

#Card {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px;
}}
#CardTitle {{ font-size: 13px; font-weight: 700; color: {TEXT}; }}
#CardHint  {{ font-size: 11px; color: {MUTED}; }}

#PageTitle {{ font-size: 22px; font-weight: 700; color: {TEXT}; }}
#PageSub   {{ font-size: 12px; color: {MUTED}; }}

#StatBig   {{ font-size: 26px; font-weight: 700; color: {TEXT}; }}
#StatLabel {{ font-size: 11px; color: {MUTED}; font-weight: 600;
             letter-spacing: 0.5px; }}

QPushButton {{
    background: {CARD_HI}; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 10px 16px; color: {TEXT}; font-weight: 600; font-size: 13px;
}}
QPushButton:hover    {{ background: #2a2e44; border-color: #3a3f57; }}
QPushButton:pressed  {{ background: #191c2b; }}
QPushButton:disabled {{ color: #4d5266; background: #16182270; border-color: #22253400; }}

QPushButton#Primary {{ background: {ACCENT}; border: none; color: #ffffff; }}
QPushButton#Primary:hover {{ background: #6ba0ff; }}
QPushButton#Primary:disabled {{ background: #26355a; color: #6a7599; }}
QPushButton#Danger {{ background: #7f2c34; border: none; color: #ffe9ea; }}
QPushButton#Danger:hover {{ background: #9b3540; }}

QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: #0b0d15; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 10px; color: {TEXT}; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {CARD}; border: 1px solid {BORDER}; padding: 4px;
    selection-background-color: {ACCENT}; color: {TEXT};
}}
QPlainTextEdit, QTextEdit#Mono {{
    font-family: 'Cascadia Mono', Consolas, monospace; font-size: 12px;
    background: #07080d;
}}
QLabel#Cmd {{
    font-family: 'Cascadia Mono', Consolas, monospace; font-size: 12px;
    background: #07080d; color: {GREEN}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 12px;
}}
QCheckBox {{ spacing: 9px; color: {TEXT}; }}
QCheckBox::indicator {{
    width: 17px; height: 17px; border-radius: 5px;
    border: 1px solid {BORDER}; background: #0b0d15;
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2e3245; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3d4260; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QLabel#Muted {{ color: {MUTED}; font-size: 12px; }}
#Sep {{ background: {BORDER}; max-height: 1px; border: none; }}
"""


# --------------------------------------------------------------------------- #
#  Small widgets
# --------------------------------------------------------------------------- #
def card(title: str | None = None, hint: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("Card")
    v = QVBoxLayout(f)
    v.setContentsMargins(18, 16, 18, 16)
    v.setSpacing(12)
    if title:
        t = QLabel(title)
        t.setObjectName("CardTitle")
        v.addWidget(t)
    if hint:
        h = QLabel(hint)
        h.setObjectName("CardHint")
        h.setWordWrap(True)
        v.addWidget(h)
    return f, v


class StatusDot(QLabel):
    def __init__(self):
        super().__init__()
        self.setFixedSize(10, 10)
        self._c = QColor(RED)

    def set_color(self, c: str) -> None:
        self._c = QColor(c)
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(self._c)
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, 10, 10)


# --------------------------------------------------------------------------- #
#  Main window
# --------------------------------------------------------------------------- #
class Manager(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = VMConfig.load()
        self.proc: QProcess | None = None
        self.install_mode = False
        self.mon = Monitor(self.cfg.monitor_port)
        self.mon.done.connect(self._mon_done)

        self.setWindowTitle("ArchVM Manager")
        self.resize(1120, 780)
        self.setMinimumSize(940, 640)
        self.setStyleSheet(STYLE)
        self._build()
        self._refresh()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(1200)

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # ---------------- sidebar ----------------
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(210)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 18, 14, 14)
        sv.setSpacing(4)

        brand = QLabel("ArchVM")
        brand.setObjectName("Brand")
        sub = QLabel("Arch Linux · Hyprland")
        sub.setObjectName("BrandSub")
        sv.addWidget(brand)
        sv.addWidget(sub)
        sv.addSpacing(18)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        for i, (label, _) in enumerate(
            [("Overview", 0), ("Hardware", 1), ("Guest", 2), ("Tools", 3), ("Logs", 4)]
        ):
            b = QPushButton(label)
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.clicked.connect(lambda _c, idx=i: self.stack.setCurrentIndex(idx))
            self.nav.addButton(b, i)
            sv.addWidget(b)

        sv.addStretch()

        statusrow = QHBoxLayout()
        self.dot = StatusDot()
        self.state_lbl = QLabel("Stopped")
        self.state_lbl.setObjectName("CardHint")
        statusrow.addWidget(self.dot)
        statusrow.addWidget(self.state_lbl)
        statusrow.addStretch()
        sv.addLayout(statusrow)
        h.addWidget(side)

        # ---------------- content ----------------
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_overview())
        self.stack.addWidget(self._page_hardware())
        self.stack.addWidget(self._page_guest())
        self.stack.addWidget(self._page_tools())
        self.stack.addWidget(self._page_logs())
        h.addWidget(self.stack, 1)

    def _scroll(self, inner: QWidget) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        return sa

    def _header(self, lay: QVBoxLayout, title: str, sub: str) -> None:
        t = QLabel(title)
        t.setObjectName("PageTitle")
        s = QLabel(sub)
        s.setObjectName("PageSub")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(6)

    # ------------------------------------------------------------------ #
    def _page_overview(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(16)
        self._header(v, "Overview", "Arch Linux with Hyprland, illogical-impulse and end4-pC")

        # stat row
        c, cv = card()
        row = QHBoxLayout()
        row.setSpacing(28)
        self.stats: dict[str, QLabel] = {}
        for key, label in (("mem", "MEMORY"), ("cpu", "VCPUS"),
                           ("res", "RESOLUTION"), ("disk", "DISK")):
            col = QVBoxLayout()
            big = QLabel("-")
            big.setObjectName("StatBig")
            lab = QLabel(label)
            lab.setObjectName("StatLabel")
            col.addWidget(big)
            col.addWidget(lab)
            row.addLayout(col)
            self.stats[key] = big
        row.addStretch()
        cv.addLayout(row)
        v.addWidget(c)

        # actions
        c2, c2v = card("Power")
        arow = QHBoxLayout()
        arow.setSpacing(10)
        self.btn_install = QPushButton("Install Arch")
        self.btn_install.setObjectName("Primary")
        self.btn_install.clicked.connect(lambda: self._start(True))
        self.btn_start = QPushButton("Start VM")
        self.btn_start.setObjectName("Primary")
        self.btn_start.clicked.connect(lambda: self._start(False))
        self.btn_stop = QPushButton("Force stop")
        self.btn_stop.setObjectName("Danger")
        self.btn_stop.clicked.connect(self._stop)
        for b in (self.btn_start, self.btn_install, self.btn_stop):
            arow.addWidget(b)
        arow.addStretch()
        c2v.addLayout(arow)
        v.addWidget(c2)

        # install banner
        self.cmd_card, ccv = card(
            "Installer waiting for input",
            "The live ISO boots to a root prompt. Run this line there - or just press "
            "\"Type it into the VM\" and the manager will enter it for you.")
        self.cmd_lbl = QLabel(INSTALL_CMD)
        self.cmd_lbl.setObjectName("Cmd")
        self.cmd_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ccv.addWidget(self.cmd_lbl)
        brow = QHBoxLayout()
        b_type = QPushButton("Type it into the VM")
        b_type.setObjectName("Primary")
        b_type.clicked.connect(lambda: self._send_text(INSTALL_CMD + "\n"))
        b_copy = QPushButton("Copy")
        b_copy.clicked.connect(lambda: QApplication.clipboard().setText(INSTALL_CMD))
        brow.addWidget(b_type)
        brow.addWidget(b_copy)
        brow.addStretch()
        ccv.addLayout(brow)
        v.addWidget(self.cmd_card)

        # GPU reality note
        c3, c3v = card(
            "About GPU acceleration",
            "Your RTX 3050 cannot be passed through: Hyper-V DDA is Windows Server only, "
            "QEMU on Windows runs on WHPX which has no VFIO, and the 3050 is a muxless "
            "laptop GPU with no independent display path. The VM uses virtio-gpu with "
            "virgl instead, which is hardware-accelerated OpenGL through the host - "
            "smooth for Hyprland, but not RTX-class. Bare metal is the only route to the "
            "real GPU.")
        v.addWidget(c3)
        v.addStretch()
        return self._scroll(page)

    # ------------------------------------------------------------------ #
    def _page_hardware(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(16)
        self._header(v, "Hardware", "Applied on the next start")

        c, cv = card("Compute")
        f = QFormLayout()
        f.setSpacing(10)
        self.sp_mem = QSpinBox(); self.sp_mem.setRange(2048, 14336)
        self.sp_mem.setSingleStep(1024); self.sp_mem.setSuffix("  MB")
        self.sp_mem.setValue(self.cfg.memory_mb)
        f.addRow("Memory", self.sp_mem)
        self.sp_cpu = QSpinBox(); self.sp_cpu.setRange(1, 16); self.sp_cpu.setValue(self.cfg.cpus)
        f.addRow("vCPUs", self.sp_cpu)
        self.cb_accel = QComboBox(); self.cb_accel.addItems(["whpx", "tcg"])
        self.cb_accel.setCurrentText(self.cfg.accel)
        f.addRow("Accelerator", self.cb_accel)
        cv.addLayout(f)
        v.addWidget(c)

        c2, c2v = card("Display")
        f2 = QFormLayout(); f2.setSpacing(10)
        self.cb_gpu = QComboBox()
        self.cb_gpu.addItems(["virtio-vga-gl", "virtio-vga", "qxl-vga", "VGA"])
        self.cb_gpu.setCurrentText(self.cfg.gpu)
        f2.addRow("GPU device", self.cb_gpu)
        self.cb_disp = QComboBox()
        self.cb_disp.addItems(["gtk,gl=on", "sdl,gl=on", "gtk,gl=off", "sdl"])
        self.cb_disp.setCurrentText(self.cfg.display)
        f2.addRow("Backend", self.cb_disp)
        resw = QWidget(); rl = QHBoxLayout(resw); rl.setContentsMargins(0, 0, 0, 0)
        self.sp_w = QSpinBox(); self.sp_w.setRange(640, 3840); self.sp_w.setValue(self.cfg.width)
        self.sp_h = QSpinBox(); self.sp_h.setRange(480, 2160); self.sp_h.setValue(self.cfg.height)
        bm = QPushButton("Match host"); bm.clicked.connect(self._match_host)
        rl.addWidget(self.sp_w); rl.addWidget(QLabel("x")); rl.addWidget(self.sp_h); rl.addWidget(bm)
        f2.addRow("Resolution", resw)
        self.ck_fs = QCheckBox("Start fullscreen")
        self.ck_fs.setChecked(self.cfg.fullscreen)
        f2.addRow("", self.ck_fs)
        c2v.addLayout(f2)
        hint = QLabel("virtio-gpu resizes the guest to match the window, so fullscreen "
                      "gives a 1:1 unscaled image. GTK releases keyboard grabs more "
                      "reliably than SDL on Windows.")
        hint.setObjectName("CardHint"); hint.setWordWrap(True)
        c2v.addWidget(hint)
        v.addWidget(c2)

        c3, c3v = card("Input and audio")
        f3 = QFormLayout(); f3.setSpacing(10)
        self.cb_kbd = QComboBox()
        self.cb_kbd.addItems(["ps2", "usb"])
        self.cb_kbd.setCurrentText(self.cfg.keyboard)
        f3.addRow("Keyboard", self.cb_kbd)
        self.cb_keymap = QComboBox()
        self.cb_keymap.addItems(["en-us", "en-gb", "de", "fr", "es", "it"])
        self.cb_keymap.setCurrentText(self.cfg.keymap)
        f3.addRow("Keymap", self.cb_keymap)
        self.ck_audio = QCheckBox("Enable sound (Intel HDA via DirectSound)")
        self.ck_audio.setChecked(self.cfg.audio)
        f3.addRow("", self.ck_audio)
        self.sp_ssh = QSpinBox(); self.sp_ssh.setRange(1025, 65535); self.sp_ssh.setValue(self.cfg.ssh_port)
        f3.addRow("SSH port", self.sp_ssh)
        c3v.addLayout(f3)
        hint3 = QLabel("virtio-keyboard is deliberately not offered: it mistranslates "
                       "shifted symbols such as Shift+0 and can leave modifier keys "
                       "stuck on the Windows host after the VM exits.")
        hint3.setObjectName("CardHint"); hint3.setWordWrap(True)
        c3v.addWidget(hint3)
        v.addWidget(c3)
        v.addStretch()
        return self._scroll(page)

    # ------------------------------------------------------------------ #
    def _page_guest(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(16)
        self._header(v, "Guest", "Written into seed.iso and used by the installer")

        vals = self._read_vmconf()
        c, cv = card("Account and locale")
        f = QFormLayout(); f.setSpacing(10)
        self.ed_user = QLineEdit(vals.get("USERNAME", "arch"))
        self.ed_pass = QLineEdit(vals.get("USERPASS", "arch"))
        self.ed_root = QLineEdit(vals.get("ROOTPASS", "arch"))
        self.ed_host = QLineEdit(vals.get("HOSTNAME", "arch-hypr"))
        self.ed_tz = QLineEdit(vals.get("TIMEZONE", "Asia/Kolkata"))
        f.addRow("Username", self.ed_user)
        f.addRow("Password", self.ed_pass)
        f.addRow("Root password", self.ed_root)
        f.addRow("Hostname", self.ed_host)
        f.addRow("Timezone", self.ed_tz)
        cv.addLayout(f)
        warn = QLabel("Stored as plain text inside seed.iso. Fine for a disposable VM; "
                      "change them with passwd if you keep it.")
        warn.setObjectName("CardHint"); warn.setWordWrap(True)
        cv.addWidget(warn)
        row = QHBoxLayout()
        b = QPushButton("Save and rebuild seed.iso"); b.setObjectName("Primary")
        b.clicked.connect(self._rebuild_seed)
        b2 = QPushButton("Open seed folder"); b2.clicked.connect(lambda: os.startfile(SEED_DIR))
        row.addWidget(b); row.addWidget(b2); row.addStretch()
        cv.addLayout(row)
        v.addWidget(c)

        c2, c2v = card("Install pipeline")
        steps = QLabel(
            "1   Live ISO   GPT/UEFI partitioning, pacstrap base, mesa, pipewire,\n"
            "                NetworkManager, openssh, zram\n"
            "2   chroot     locale, keymap, user, sudo, virtio initramfs, systemd-boot\n"
            "3   First login  yay  ->  end-4/dots-hyprland (setup install -f)\n"
            "                ->  pctrade/end4-pc as the default Quickshell config\n"
            "                ->  virtio-gpu tuning, then temporary sudo revoked")
        steps.setObjectName("CardHint")
        steps.setFont(QFont("Cascadia Mono, Consolas", 10))
        c2v.addWidget(steps)
        v.addWidget(c2)
        v.addStretch()
        return self._scroll(page)

    # ------------------------------------------------------------------ #
    def _page_tools(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(16)
        self._header(v, "Tools", "Getting text in, and managing the disk")

        c, cv = card(
            "Send text to the VM",
            "QEMU has no host/guest clipboard, so this types the text in for you over "
            "the QEMU monitor. Click into the VM window first so the guest has keyboard "
            "focus. US-layout characters only.")
        self.ed_send = QTextEdit()
        self.ed_send.setObjectName("Mono")
        self.ed_send.setPlaceholderText("Paste here, then send...")
        self.ed_send.setFixedHeight(110)
        cv.addWidget(self.ed_send)
        r = QHBoxLayout()
        b1 = QPushButton("Send text"); b1.setObjectName("Primary")
        b1.clicked.connect(lambda: self._send_text(self.ed_send.toPlainText()))
        b2 = QPushButton("Send + Enter")
        b2.clicked.connect(lambda: self._send_text(self.ed_send.toPlainText() + "\n"))
        b3 = QPushButton("From clipboard")
        b3.clicked.connect(lambda: self.ed_send.setPlainText(QApplication.clipboard().text()))
        r.addWidget(b1); r.addWidget(b2); r.addWidget(b3); r.addStretch()
        cv.addLayout(r)
        v.addWidget(c)

        c2, c2v = card(
            "SSH into the guest",
            "The better route for real work: a normal Windows terminal with working "
            "copy and paste. Requires the VM running and the install finished.")
        r2 = QHBoxLayout()
        bs = QPushButton("Open SSH session"); bs.setObjectName("Primary")
        bs.clicked.connect(self._open_ssh)
        self.lbl_ssh = QLabel("")
        self.lbl_ssh.setObjectName("CardHint")
        r2.addWidget(bs); r2.addWidget(self.lbl_ssh); r2.addStretch()
        c2v.addLayout(r2)
        v.addWidget(c2)

        c3, c3v = card("Virtual disk")
        self.lbl_dinfo = QLabel("-")
        self.lbl_dinfo.setObjectName("CardHint")
        c3v.addWidget(self.lbl_dinfo)
        r3 = QHBoxLayout()
        for text, fn in (("Refresh", self._disk_info),
                         ("Snapshot", self._snapshot),
                         ("List snapshots", self._snapshot_list),
                         ("Open folder", lambda: os.startfile(BASE))):
            b = QPushButton(text); b.clicked.connect(fn); r3.addWidget(b)
        r3.addStretch()
        c3v.addLayout(r3)
        r4 = QHBoxLayout()
        bd = QPushButton("Reset disk (erases the VM)")
        bd.setObjectName("Danger"); bd.clicked.connect(self._reset_disk)
        r4.addWidget(bd); r4.addStretch()
        c3v.addLayout(r4)
        v.addWidget(c3)
        v.addStretch()
        QTimer.singleShot(300, self._disk_info)
        return self._scroll(page)

    # ------------------------------------------------------------------ #
    def _page_logs(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(16)
        self._header(v, "Logs", "QEMU output and manager events")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(6000)
        v.addWidget(self.log, 1)
        r = QHBoxLayout()
        b1 = QPushButton("Clear"); b1.clicked.connect(self.log.clear)
        b2 = QPushButton("Show launch command"); b2.clicked.connect(self._show_cmd)
        b3 = QPushButton("Copy log")
        b3.clicked.connect(lambda: QApplication.clipboard().setText(self.log.toPlainText()))
        r.addWidget(b1); r.addWidget(b2); r.addWidget(b3); r.addStretch()
        v.addLayout(r)
        return page

    # ------------------------------------------------------------------ #
    #  Behaviour
    # ------------------------------------------------------------------ #
    def _log(self, t: str) -> None:
        if t.strip():
            self.log.appendPlainText(t.rstrip())
            self.log.moveCursor(QTextCursor.End)

    def _read_vmconf(self) -> dict:
        vals: dict[str, str] = {}
        p = SEED_DIR / "vm.conf"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, val = line.partition("=")
                    vals[k.strip()] = val.strip()
        return vals

    def _collect(self) -> None:
        self.cfg.memory_mb = self.sp_mem.value()
        self.cfg.cpus = self.sp_cpu.value()
        self.cfg.accel = self.cb_accel.currentText()
        self.cfg.gpu = self.cb_gpu.currentText()
        self.cfg.display = self.cb_disp.currentText()
        self.cfg.width = self.sp_w.value()
        self.cfg.height = self.sp_h.value()
        self.cfg.fullscreen = self.ck_fs.isChecked()
        self.cfg.keyboard = self.cb_kbd.currentText()
        self.cfg.keymap = self.cb_keymap.currentText()
        self.cfg.audio = self.ck_audio.isChecked()
        self.cfg.ssh_port = self.sp_ssh.value()
        self.cfg.username = self.ed_user.text().strip() or "arch"
        self.cfg.save()

    def _match_host(self) -> None:
        g = QApplication.primaryScreen().geometry()
        self.sp_w.setValue(g.width())
        self.sp_h.setValue(g.height())
        self.ck_fs.setChecked(True)
        self._log(f"[manager] resolution set to {g.width()}x{g.height()}, fullscreen on")

    def _send_text(self, text: str) -> None:
        if not text:
            return
        if not self._running():
            QMessageBox.information(self, "VM not running", "Start the VM first.")
            return
        self._log(f"[manager] typing {len(text)} chars into the guest")
        self.mon.type_text(text)

    def _mon_done(self, msg: str) -> None:
        self._log("[monitor] " + msg)
        if "Could not reach" in msg:
            QMessageBox.warning(self, "Monitor unavailable", msg)

    def _open_ssh(self) -> None:
        user = self.ed_user.text().strip() or "arch"
        port = self.sp_ssh.value()
        cmd = f"ssh -o StrictHostKeyChecking=no -p {port} {user}@127.0.0.1"
        try:
            subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", cmd])
            self._log(f"[manager] {cmd}")
        except Exception as e:
            QMessageBox.critical(self, "SSH failed", str(e))

    def _rebuild_seed(self) -> None:
        vals = self._read_vmconf()
        vals.update({
            "USERNAME": self.ed_user.text().strip() or "arch",
            "USERPASS": self.ed_pass.text() or "arch",
            "ROOTPASS": self.ed_root.text() or "arch",
            "HOSTNAME": self.ed_host.text().strip() or "arch-hypr",
            "TIMEZONE": self.ed_tz.text().strip() or "Asia/Kolkata",
        })
        vals.setdefault("LOCALE", "en_US.UTF-8")
        vals.setdefault("KEYMAP", "us")
        vals.setdefault("FORK_REPO", "https://github.com/pctrade/end4-pc.git")
        vals.setdefault("FORK_NAME", "end4-pC")
        body = "# regenerated by ArchVM Manager\n" + "".join(f"{k}={v}\n" for k, v in vals.items())
        (SEED_DIR / "vm.conf").write_bytes(body.encode("utf-8"))   # LF only
        try:
            out = subprocess.run([sys.executable, str(BASE / "manager" / "build_seed.py")],
                                 capture_output=True, text=True, timeout=90)
            self._log(out.stdout + out.stderr)
            if out.returncode == 0:
                QMessageBox.information(self, "Seed rebuilt", "seed.iso regenerated.")
            else:
                QMessageBox.warning(self, "Build failed", out.stderr or "unknown error")
        except Exception as e:
            QMessageBox.critical(self, "Build failed", str(e))

    def _show_cmd(self) -> None:
        self._collect()
        args = self.cfg.build_args(self.install_mode)
        self._log("[manager] " + str(QEMU) + " " +
                  " ".join(f'"{a}"' if " " in a else a for a in args))

    # ---------------- run control ----------------
    def _running(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.NotRunning

    def _start(self, install: bool) -> None:
        if self._running():
            QMessageBox.information(self, "Already running", "The VM is already running.")
            return
        self._collect()
        self.install_mode = install
        need = [self.cfg.disk] + ([self.cfg.iso, self.cfg.seed_iso] if install else [])
        missing = [p for p in need if not Path(p).exists()]
        if missing:
            QMessageBox.critical(self, "Missing files", "\n".join(missing))
            return
        self.mon.port = self.cfg.monitor_port
        self.proc = QProcess(self)
        self.proc.setProgram(str(QEMU))
        self.proc.setArguments(self.cfg.build_args(install))
        self.proc.readyReadStandardError.connect(
            lambda: self._log(bytes(self.proc.readAllStandardError()).decode("utf-8", "replace")))
        self.proc.readyReadStandardOutput.connect(
            lambda: self._log(bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")))
        self.proc.finished.connect(lambda c, _s: (self._log(f"[manager] VM exited ({c})"),
                                                  self._refresh()))
        self._log(f"[manager] starting VM ({'install' if install else 'normal'})")
        self._show_cmd()
        self.proc.start()
        if not self.proc.waitForStarted(8000):
            QMessageBox.critical(self, "Launch failed", self.proc.errorString())
            return
        self._refresh()

    def _stop(self) -> None:
        if not self._running():
            return
        if QMessageBox.question(self, "Force stop",
                                "Force-stop the VM? This is like pulling the power cable. "
                                "Shut down from inside the guest when you can."
                                ) != QMessageBox.Yes:
            return
        self.proc.kill()
        self._log("[manager] force-stopped")

    def _refresh(self) -> None:
        run = self._running()
        self.dot.set_color(GREEN if run else RED)
        self.state_lbl.setText("Running" if run else "Stopped")
        self.btn_install.setEnabled(not run)
        self.btn_start.setEnabled(not run)
        self.btn_stop.setEnabled(run)
        self.cmd_card.setVisible(run and self.install_mode)
        if hasattr(self, "stats"):
            self.stats["mem"].setText(f"{self.cfg.memory_mb // 1024} GB")
            self.stats["cpu"].setText(str(self.cfg.cpus))
            self.stats["res"].setText(f"{self.cfg.width}x{self.cfg.height}")
        if hasattr(self, "lbl_ssh"):
            self.lbl_ssh.setText(
                f"{self.ed_user.text().strip() or 'arch'}@127.0.0.1 : {self.sp_ssh.value()}")

    # ---------------- disk ----------------
    def _qemu_img(self, *a: str) -> str:
        try:
            r = subprocess.run([str(QEMU_IMG), *a], capture_output=True, text=True, timeout=180)
            return (r.stdout + r.stderr).strip()
        except Exception as e:
            return f"error: {e}"

    def _disk_info(self) -> None:
        p = Path(self.cfg.disk)
        if not p.exists():
            self.lbl_dinfo.setText("disk not found")
            return
        txt = self._qemu_img("info", str(p))
        virt = re.search(r"virtual size: ([^\n(]+)", txt)
        real = re.search(r"disk size: ([^\n(]+)", txt)
        vs = virt.group(1).strip() if virt else "?"
        rs = real.group(1).strip() if real else "?"
        self.lbl_dinfo.setText(f"virtual {vs}   ·   allocated {rs}")
        if hasattr(self, "stats"):
            self.stats["disk"].setText(vs.replace(" GiB", " GB"))

    def _snapshot(self) -> None:
        if self._running():
            QMessageBox.warning(self, "VM running", "Stop the VM first.")
            return
        name, ok = QInputDialog.getText(self, "Snapshot", "Name:")
        if ok and name.strip():
            self._log("[qemu-img] " + self._qemu_img("snapshot", "-c", name.strip(), self.cfg.disk))
            QMessageBox.information(self, "Snapshot", f"Created '{name.strip()}'.")

    def _snapshot_list(self) -> None:
        self._log("[qemu-img] " + self._qemu_img("snapshot", "-l", self.cfg.disk))
        self.stack.setCurrentIndex(4)
        self.nav.button(4).setChecked(True)

    def _reset_disk(self) -> None:
        if self._running():
            QMessageBox.warning(self, "VM running", "Stop the VM first.")
            return
        if QMessageBox.warning(
                self, "Erase VM disk",
                "This permanently deletes the virtual disk and everything installed in "
                "the VM. Your Windows files are untouched.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        p = Path(self.cfg.disk)
        if p.exists():
            p.unlink()
        self._log("[qemu-img] " + self._qemu_img("create", "-f", "qcow2", str(p), "120G"))
        src = QEMU_DIR / "share" / "edk2-i386-vars.fd"
        if src.exists():
            shutil.copyfile(src, self.cfg.ovmf_vars)
        self._disk_info()
        QMessageBox.information(self, "Disk reset", "Fresh disk created.")

    def closeEvent(self, e) -> None:
        if self._running():
            if QMessageBox.question(self, "VM running",
                                    "The VM is still running. Quit and force-stop it?"
                                    ) != QMessageBox.Yes:
                e.ignore()
                return
            self.proc.kill()
            self.proc.waitForFinished(3000)
        self._collect()
        e.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ArchVM Manager")
    ico = BASE / "manager" / "archvm.ico"
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))
    w = Manager()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
