"""Main window: sidebar navigation, pages, and all VM actions."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QSize, QProcess
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QLineEdit, QPlainTextEdit, QTextEdit, QCheckBox,
    QFormLayout, QMessageBox, QStackedWidget, QButtonGroup, QScrollArea,
    QInputDialog, QApplication, QProgressBar, QFileDialog, QSlider, QFrame,
    QDialog, QTableWidget, QTableWidgetItem, QHeaderView,
)

from . import icons, paths, qemu, theme
from .config import AppSettings, VMConfig, INSTALL_CMD
from .widgets import (AlertBar, Backdrop, Card, Chip, CommandSnippet, MeterBar,
                      Stat, StatusBadge, StatusDot, Toast, a11y, button, elevate)

def _within(path: Path, root: Path) -> bool:
    """True when `path` sits inside `root`. Never raises on odd drives."""
    try:
        path.relative_to(root)
        return True
    except (ValueError, OSError):
        return False


NAV_SECTIONS = [
    ("MACHINE", [("Overview", "✦"), ("Hardware", "⚡")]),
    ("SETUP", [("Guest", "⚙"), ("Tools", "🔧")]),
    ("SYSTEM", [("Settings", "⛯"), ("Logs", "📄")]),
]
PAGES = [name for _section, items in NAV_SECTIONS for name, _glyph in items]


class MainWindow(QMainWindow):
    request_quit = Signal()

    def __init__(self, cfg: VMConfig, settings: AppSettings):
        super().__init__()
        self.cfg = cfg
        self.settings = settings
        self.runner = qemu.VMRunner(self)
        self.monitor = qemu.MonitorClient(cfg.monitor_port, self)
        # True between starting a guided install and the VM powering off
        # at the end of it, so the installed system can be booted for you.
        self._await_first_boot = False
        self._force_quit = False
        self._vm_started_at: float | None = None
        self._installed_cache = False
        self._tick = 0

        self.setWindowTitle(f"{paths.APP_NAME} — Arch Linux + Hyprland")
        self.setWindowIcon(icons.app_icon())
        self.resize(settings.window_w, settings.window_h)
        self.setMinimumSize(920, 620)

        self._build()
        self._wire()
        self._label_orphans()
        self.apply_theme()
        self._refresh()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1200)

        note = getattr(cfg, "migration_note", "")
        if note:
            QTimer.singleShot(700, lambda: self.alert.show_alert(
                note, kind="warn", action="Hardware", on_action=lambda: self._go(1)))
            QTimer.singleShot(750, lambda: self._log("[config] " + note))

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        pal = theme.resolve(self.settings.theme)
        self.backdrop = Backdrop(pal)
        self.setCentralWidget(self.backdrop)

        root = QWidget(self.backdrop)
        root.setObjectName("Root")
        outer = QVBoxLayout(self.backdrop)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._sidebar())

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        self.alert = AlertBar()
        rv.addWidget(self.alert)

        self.toast = Toast()
        tw = QWidget()
        tl = QVBoxLayout(tw)
        tl.setContentsMargins(24, 14, 24, 0)
        tl.addWidget(self.toast)
        rv.addWidget(tw)

        self.stack = QStackedWidget()
        for maker in (self._page_overview, self._page_hardware, self._page_guest,
                      self._page_tools, self._page_settings, self._page_logs):
            self.stack.addWidget(maker())
        rv.addWidget(self.stack, 1)
        h.addWidget(right, 1)

        # Keyboard shortcuts
        for i in range(len(PAGES)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self,
                      activated=lambda idx=i: self._go(idx))
        QShortcut(QKeySequence("Ctrl+R"), self, activated=lambda: self._start(False))
        QShortcut(QKeySequence("Ctrl+I"), self, activated=lambda: self._start(True))
        QShortcut(QKeySequence("Ctrl+L"), self, activated=lambda: self._go(5))
        QShortcut(QKeySequence("F1"), self, activated=self._about)

    def _label_orphans(self) -> None:
        """
        Catch-all so no interactive control is invisible to a screen reader.
        Derives a name from the widget's own text, its form-row label, or its
        tooltip - whichever exists first.
        """
        from PySide6.QtWidgets import (QAbstractButton, QComboBox, QLineEdit,
                                       QSlider, QAbstractSpinBox)
        types = (QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit, QSlider)
        for w in self.findChildren(QWidget):
            if not isinstance(w, types) or w.accessibleName():
                continue
            name = ""
            if hasattr(w, "text") and callable(w.text):
                try:
                    name = w.text() or ""
                except TypeError:
                    name = ""
            if not name:
                name = w.toolTip() or self._form_label_for(w) or w.objectName()
            if name:
                w.setAccessibleName(name.strip())

    def _form_label_for(self, w: QWidget) -> str:
        """Find the QFormLayout row label belonging to a widget, if any."""
        parent = w.parentWidget()
        while parent is not None:
            lay = parent.layout()
            if isinstance(lay, QFormLayout):
                for row in range(lay.rowCount()):
                    item = lay.itemAt(row, QFormLayout.FieldRole)
                    if item and item.widget() is w:
                        lab = lay.itemAt(row, QFormLayout.LabelRole)
                        if lab and lab.widget():
                            return lab.widget().text()
            parent = parent.parentWidget()
        return ""

    def _toggle_echo(self, edit: QLineEdit, btn: QPushButton) -> None:
        if edit.echoMode() == QLineEdit.Password:
            edit.setEchoMode(QLineEdit.Normal)
            btn.setText("Hide")
        else:
            edit.setEchoMode(QLineEdit.Password)
            btn.setText("Show")

    def _sidebar(self) -> QWidget:
        """
        Navigation rail: mark, grouped sections, then a help affordance and the
        product name pinned to the bottom.
        """
        w = QWidget()
        w.setObjectName("Sidebar")
        w.setFixedWidth(206)
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 16, 12, 14)
        v.setSpacing(3)

        head = QHBoxLayout()
        head.setSpacing(9)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(QSize(32, 32)))
        txt = QVBoxLayout()
        txt.setSpacing(1)
        brow = QHBoxLayout()
        brow.setSpacing(6)
        b = QLabel(paths.APP_NAME)
        b.setObjectName("Brand")
        ver = QLabel(f"v{paths.APP_VERSION}")
        ver.setObjectName("BrandVersion")
        brow.addWidget(b)
        brow.addWidget(ver)
        brow.addStretch()
        sub = QLabel("Arch \u00b7 Hyprland")
        sub.setObjectName("BrandSub")
        txt.addLayout(brow)
        txt.addWidget(sub)
        head.addWidget(logo)
        head.addLayout(txt)
        head.addStretch()
        v.addLayout(head)
        v.addSpacing(16)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        idx = 0
        for section, items in NAV_SECTIONS:
            lab = QLabel(section)
            lab.setObjectName("SectionLabel")
            v.addWidget(lab)
            v.addSpacing(2)
            for name, glyph in items:
                btn = QPushButton(f"{glyph}  {name}")
                btn.setObjectName("Nav")
                btn.setCheckable(True)
                btn.setChecked(idx == 0)
                btn.setCursor(Qt.PointingHandCursor)
                a11y(btn, name, f"Go to {name} (Ctrl+{idx + 1})")
                btn.clicked.connect(lambda _c, i=idx: self._go(i))
                self.nav.addButton(btn, idx)
                v.addWidget(btn)
                idx += 1
            v.addSpacing(12)

        v.addStretch()

        helprow = QHBoxLayout()
        helprow.addStretch()
        hb = QPushButton("?")
        hb.setObjectName("Help")
        hb.setFixedSize(38, 38)
        hb.setCursor(Qt.PointingHandCursor)
        a11y(hb, "Help", "Documentation and keyboard shortcuts (F1)")
        hb.clicked.connect(self._about)
        helprow.addWidget(hb)
        helprow.addStretch()
        v.addLayout(helprow)
        hint = QLabel("Need help")
        hint.setObjectName("RailFoot")
        hint.setAlignment(Qt.AlignCenter)
        v.addWidget(hint)
        v.addSpacing(12)

        rule = QFrame()
        rule.setObjectName("RailRule")
        rule.setFrameShape(QFrame.HLine)
        v.addWidget(rule)
        v.addSpacing(9)

        status_card = QFrame()
        status_card.setObjectName("RailStatusCard")
        statusrow = QHBoxLayout(status_card)
        statusrow.setContentsMargins(10, 7, 10, 7)
        statusrow.setSpacing(8)
        self.dot = StatusDot()
        self.state_lbl = QLabel("Stopped")
        self.state_lbl.setObjectName("RailFoot")
        statusrow.addWidget(self.dot)
        statusrow.addWidget(self.state_lbl)
        statusrow.addStretch()
        v.addWidget(status_card)
        return w

    def _page(self, title: str, sub: str) -> tuple[QScrollArea, QVBoxLayout]:
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(24, 18, 24, 24)
        v.setSpacing(15)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        st = QLabel(sub)
        st.setObjectName("PageSub")
        st.setWordWrap(True)
        v.addWidget(t)
        v.addWidget(st)
        v.addSpacing(4)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        sa.setFocusPolicy(Qt.StrongFocus)
        return sa, v

    # ------------------------------------------------------------------ #
    def _page_overview(self) -> QWidget:
        page, v = self._page(
            "Overview",
            "Arch Linux with Hyprland, illogical-impulse and the end4-pC shell")

        # ---- hero: the single next action, whatever that currently is ----
        self.hero = Card()
        self.hero.setObjectName("Hero")
        hrow = QHBoxLayout()
        hcol = QVBoxLayout()
        hcol.setSpacing(6)
        self.hero_title = QLabel("Ready to install")
        self.hero_title.setObjectName("CardTitle")
        f = QFont(); f.setPointSize(15); f.setBold(True)
        self.hero_title.setFont(f)
        self.hero_body = QLabel("")
        self.hero_body.setObjectName("CardHint")
        self.hero_body.setWordWrap(True)
        hcol.addWidget(self.hero_title)
        hcol.addWidget(self.hero_body)

        self.hero_progress = QProgressBar()
        self.hero_progress.setObjectName("HeroProgress")
        self.hero_progress.setRange(0, 0)
        self.hero_progress.setTextVisible(False)
        self.hero_progress.setVisible(False)
        hcol.addWidget(self.hero_progress)

        hrow.addLayout(hcol, 1)
        self.hero_chip = StatusBadge("NOT INSTALLED", "stopped")
        hrow.addWidget(self.hero_chip, 0, Qt.AlignTop)
        self.hero.add(hrow)

        arow = QHBoxLayout()
        arow.setSpacing(9)
        self.btn_primary = button("Install Arch", primary=True,
                                  tip="Boot the installer and set everything up (Ctrl+I)")
        self.btn_primary.clicked.connect(self._primary_action)
        self.btn_start = button("Start VM", tip="Boot from the virtual disk (Ctrl+R)")
        self.btn_start.clicked.connect(lambda: self._start(False))
        self.btn_install = button("Reinstall…", tip="Boot the Arch installer again")
        self.btn_install.clicked.connect(lambda: self._start(True))
        self.btn_hero_ssh = button("Open SSH", tip="Launch SSH terminal session into the VM")
        self.btn_hero_ssh.clicked.connect(self._open_ssh)
        self.btn_shutdown = button("Shut down", tip="Ask the guest to power off cleanly")
        self.btn_shutdown.clicked.connect(self._shutdown)
        self.btn_stop = button("Force stop", danger=True, tip="Kill QEMU immediately")
        self.btn_stop.clicked.connect(self._force_stop)
        for b in (self.btn_primary, self.btn_start, self.btn_install,
                  self.btn_hero_ssh, self.btn_shutdown, self.btn_stop):
            arow.addWidget(b)
        arow.addStretch()
        self.hero.add(arow)
        v.addWidget(self.hero)

        # ---- stats dashboard grid ----
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self.stats = {
            "mem": Stat("Memory", f"{self.cfg.memory_mb // 1024} GB", icon="💾", sub="Allocated RAM"),
            "cpu": Stat("vCPUs", str(self.cfg.cpus), icon="⚡", sub="Host Cores"),
            "res": Stat("Resolution", f"{self.cfg.width}×{self.cfg.height}", icon="🖥", sub="virtio-vga 3D"),
            "disk": Stat("Disk Usage", "—", icon="💿", sub="Allocated"),
            "uptime": Stat("VM Uptime", "—", icon="⏱", sub="Session Active"),
        }
        for st in self.stats.values():
            stats_row.addWidget(st, 1)
        v.addLayout(stats_row)

        # ---- host load, so it is obvious what the VM costs Windows ----
        pal = theme.resolve(self.settings.theme)
        cm = Card("Host Resource Load", "Real-time host impact of the virtualized environment.")
        self.meters = {
            "ram": MeterBar("System Memory", pal, icon="🧠"),
            "disk": MeterBar("VM Drive Free Space", pal, icon="💽"),
        }
        for m in self.meters.values():
            cm.add(m)
        v.addWidget(cm)

        # ---- installer helper ----
        self.cmd_card = Card(
            "Live Installer Automation",
            "The live ISO boots to a root prompt. The app types the setup command for you automatically.")
        self.snippet = CommandSnippet(INSTALL_CMD, title="bash / live-iso installer")
        self.cmd_card.add(self.snippet)
        rr = QHBoxLayout()
        bt = button("Type into VM Console", primary=True, tip="Send keystrokes via QEMU monitor")
        bt.clicked.connect(self._send_install_cmd)
        rr.addWidget(bt); rr.addStretch()
        self.cmd_card.add(rr)
        v.addWidget(self.cmd_card)

        v.addWidget(Card(
            "About GPU acceleration",
            "A discrete GPU cannot be passed through on a Windows host: Hyper-V DDA "
            "is Windows Server only, QEMU on Windows runs on WHPX which has no VFIO, "
            "and laptop dGPUs are muxless with no independent display path. The VM "
            "uses virtio-gpu with virgl — hardware-accelerated OpenGL through the "
            "host. Smooth for Hyprland, but not the same as bare metal."))
        v.addStretch()
        return page

    # ------------------------------------------------------------------ #
    def _guest_installed(self) -> bool:
        """
        Heuristic: a fresh qcow2 is a few MB. Anything past a gigabyte means a
        real system was written, which is enough to decide what to offer.
        """
        try:
            import re
            txt = qemu.qemu_img("info", self.cfg.disk)
            m = re.search(r"disk size: ([\d.]+) ([KMGT])iB", txt)
            if not m:
                return False
            val, unit = float(m.group(1)), m.group(2)
            gb = val * {"K": 1 / 1048576, "M": 1 / 1024, "G": 1, "T": 1024}[unit]
            return gb > 1.5
        except Exception:
            return False

    def _primary_action(self) -> None:
        if self._guest_installed():
            self._start(False)
        else:
            self._start_install_flow()

    def _refresh_hero(self) -> None:
        running = self.runner.is_running()
        installed = self._installed_cache
        if running and self.runner.install_mode:
            self.hero_title.setText("Installing Arch Linux")
            self.hero_body.setText(
                "The automated base install is in progress. When it finishes, the VM "
                "powers off and reboots from disk to finish desktop configuration.")
            self.hero_chip.set_status("installing", "INSTALLING")
            if hasattr(self, "hero_progress"):
                self.hero_progress.setVisible(True)
            self.btn_primary.setVisible(False)
            self.btn_start.setVisible(False)
            self.btn_install.setVisible(False)
            if hasattr(self, "btn_hero_ssh"):
                self.btn_hero_ssh.setVisible(False)
            self.btn_shutdown.setVisible(True)
            self.btn_stop.setVisible(True)
        elif running:
            self.hero_title.setText("Arch Linux is running")
            self.hero_body.setText(
                "Press Super to open the launcher, Super + / for keybindings. "
                "Open SSH to connect directly from Windows Terminal.")
            self.hero_chip.set_status("running", "RUNNING")
            if hasattr(self, "hero_progress"):
                self.hero_progress.setVisible(False)
            self.btn_primary.setVisible(False)
            self.btn_start.setVisible(False)
            self.btn_install.setVisible(False)
            if hasattr(self, "btn_hero_ssh"):
                self.btn_hero_ssh.setVisible(True)
            self.btn_shutdown.setVisible(True)
            self.btn_stop.setVisible(True)
        elif installed:
            self.hero_title.setText("Arch Linux is ready")
            self.hero_body.setText(
                "Desktop environment is installed. Start the VM to boot into Hyprland "
                "with the end4-pC Quickshell interface.")
            self.hero_chip.set_status("ready", "READY")
            if hasattr(self, "hero_progress"):
                self.hero_progress.setVisible(False)
            self.btn_primary.setText("Start VM")
            self.btn_primary.setVisible(True)
            self.btn_start.setVisible(False)
            self.btn_install.setVisible(True)
            if hasattr(self, "btn_hero_ssh"):
                self.btn_hero_ssh.setVisible(False)
            self.btn_shutdown.setVisible(False)
            self.btn_stop.setVisible(False)
        else:
            self.hero_title.setText("Ready to install")
            self.hero_body.setText(
                "Press Install Arch. The VM boots and the installer command is typed "
                "in for you — automated install takes ~15 minutes.")
            self.hero_chip.set_status("stopped", "NOT INSTALLED")
            if hasattr(self, "hero_progress"):
                self.hero_progress.setVisible(False)
            self.btn_primary.setText("Install Arch")
            self.btn_primary.setVisible(True)
            self.btn_start.setVisible(False)
            self.btn_install.setVisible(False)
            if hasattr(self, "btn_hero_ssh"):
                self.btn_hero_ssh.setVisible(False)
            self.btn_shutdown.setVisible(False)
            self.btn_stop.setVisible(False)

    # ------------------------------------------------------------------ #
    def _page_hardware(self) -> QWidget:
        page, v = self._page("Hardware", "Changes apply the next time the VM starts")

        c = Card("Compute")
        f = QFormLayout()
        f.setSpacing(10)
        self.sp_mem = QSpinBox(); self.sp_mem.setRange(2048, 14336)
        self.sp_mem.setSingleStep(1024); self.sp_mem.setSuffix("  MB")
        self.sp_mem.setValue(self.cfg.memory_mb)
        a11y(self.sp_mem, "Memory", "RAM given to the VM in megabytes")
        f.addRow("Memory", self.sp_mem)
        self.sp_cpu = QSpinBox(); self.sp_cpu.setRange(1, 32); self.sp_cpu.setValue(self.cfg.cpus)
        a11y(self.sp_cpu, "vCPUs", "Virtual CPU cores")
        f.addRow("vCPUs", self.sp_cpu)
        self.cb_accel = QComboBox(); self.cb_accel.addItems(["whpx", "tcg"])
        self.cb_accel.setCurrentText(self.cfg.accel)
        a11y(self.cb_accel, "Accelerator", "whpx is hardware accelerated; tcg is slow emulation")
        f.addRow("Accelerator", self.cb_accel)
        c.add(f)
        v.addWidget(c)

        c2 = Card("Display")
        f2 = QFormLayout(); f2.setSpacing(10)
        self.cb_gpu = QComboBox()
        self.cb_gpu.addItems(["virtio-vga", "qxl-vga", "VGA"])
        if self.cfg.gpu not in ("virtio-vga", "qxl-vga", "VGA"):
            self.cb_gpu.addItem(self.cfg.gpu)
        self.cb_gpu.setCurrentText(self.cfg.gpu)
        a11y(self.cb_gpu, "GPU device",
             "virtio-vga is the fastest option that renders on Windows")
        f2.addRow("GPU device", self.cb_gpu)
        self.cb_disp = QComboBox()
        self.cb_disp.addItems(["gtk", "sdl"])
        self.cb_disp.setCurrentText(self.cfg.display.split(",")[0])
        a11y(self.cb_disp, "Display backend",
             "GTK releases keyboard grabs more reliably on Windows")
        f2.addRow("Backend", self.cb_disp)
        rw = QWidget(); rl = QHBoxLayout(rw); rl.setContentsMargins(0, 0, 0, 0)
        self.sp_w = QSpinBox(); self.sp_w.setRange(640, 3840); self.sp_w.setValue(self.cfg.width)
        self.sp_h = QSpinBox(); self.sp_h.setRange(480, 2160); self.sp_h.setValue(self.cfg.height)
        bm = button("Match host"); bm.clicked.connect(self._match_host)
        rl.addWidget(self.sp_w); rl.addWidget(QLabel("×")); rl.addWidget(self.sp_h); rl.addWidget(bm)
        f2.addRow("Resolution", rw)
        self.ck_fs = QCheckBox("Start fullscreen")
        self.ck_fs.setChecked(self.cfg.fullscreen)
        f2.addRow("", self.ck_fs)
        c2.add(f2)
        h = QLabel("virtio-gpu resizes the guest to match the window, so fullscreen "
                   "gives a 1:1 unscaled image.")
        h.setObjectName("CardHint"); h.setWordWrap(True)
        c2.add(h)
        v.addWidget(c2)

        c3 = Card("Input and audio")
        f3 = QFormLayout(); f3.setSpacing(10)
        self.cb_kbd = QComboBox(); self.cb_kbd.addItems(["ps2", "usb"])
        self.cb_kbd.setCurrentText(self.cfg.keyboard)
        a11y(self.cb_kbd, "Keyboard model", "PS/2 is the most compatible")
        f3.addRow("Keyboard", self.cb_kbd)
        self.cb_keymap = QComboBox()
        self.cb_keymap.addItems(["en-us", "en-gb", "de", "fr", "es", "it", "pt-br", "ru"])
        self.cb_keymap.setCurrentText(self.cfg.keymap)
        f3.addRow("Keymap", self.cb_keymap)
        self.ck_audio = QCheckBox("Enable sound (Intel HDA via DirectSound)")
        self.ck_audio.setChecked(self.cfg.audio)
        f3.addRow("", self.ck_audio)
        self.sp_ssh = QSpinBox(); self.sp_ssh.setRange(1025, 65535); self.sp_ssh.setValue(self.cfg.ssh_port)
        f3.addRow("SSH port", self.sp_ssh)
        c3.add(f3)
        h3 = QLabel("virtio-keyboard is intentionally not offered: it mistranslates "
                    "shifted symbols such as Shift+0 and can leave modifier keys stuck "
                    "on the Windows host after the VM exits.")
        h3.setObjectName("CardHint"); h3.setWordWrap(True)
        c3.add(h3)
        v.addWidget(c3)
        v.addStretch()
        return page

    # ------------------------------------------------------------------ #
    def _page_guest(self) -> QWidget:
        page, v = self._page("Guest", "Written into seed.iso and consumed by the installer")
        vals = self._read_vmconf()

        c = Card("Account and locale")
        f = QFormLayout(); f.setSpacing(10)
        self.ed_user = QLineEdit(vals.get("USERNAME", "arch"))

        pw_box1 = QWidget()
        pw_lay1 = QHBoxLayout(pw_box1)
        pw_lay1.setContentsMargins(0, 0, 0, 0)
        pw_lay1.setSpacing(6)
        self.ed_pass = QLineEdit(vals.get("USERPASS", "arch"))
        self.ed_pass.setEchoMode(QLineEdit.Password)
        b_pass_show = button("Show", ghost=True)
        b_pass_show.setFixedWidth(60)
        b_pass_show.clicked.connect(lambda: self._toggle_echo(self.ed_pass, b_pass_show))
        pw_lay1.addWidget(self.ed_pass, 1)
        pw_lay1.addWidget(b_pass_show)

        pw_box2 = QWidget()
        pw_lay2 = QHBoxLayout(pw_box2)
        pw_lay2.setContentsMargins(0, 0, 0, 0)
        pw_lay2.setSpacing(6)
        self.ed_root = QLineEdit(vals.get("ROOTPASS", "arch"))
        self.ed_root.setEchoMode(QLineEdit.Password)
        b_root_show = button("Show", ghost=True)
        b_root_show.setFixedWidth(60)
        b_root_show.clicked.connect(lambda: self._toggle_echo(self.ed_root, b_root_show))
        pw_lay2.addWidget(self.ed_root, 1)
        pw_lay2.addWidget(b_root_show)

        self.ed_host = QLineEdit(vals.get("HOSTNAME", "arch-hypr"))
        self.ed_tz = QLineEdit(vals.get("TIMEZONE", "Asia/Kolkata"))
        a11y(self.ed_user, "Username")
        f.addRow("Username", self.ed_user)
        a11y(self.ed_pass, "User password")
        f.addRow("User password", pw_box1)
        a11y(self.ed_root, "Root password")
        f.addRow("Root password", pw_box2)
        a11y(self.ed_host, "Hostname")
        f.addRow("Hostname", self.ed_host)
        a11y(self.ed_tz, "Timezone")
        f.addRow("Timezone", self.ed_tz)
        c.add(f)
        warn = QLabel("Stored as plain text inside seed.iso. Fine for a disposable VM; "
                      "change them with passwd if you keep it.")
        warn.setObjectName("CardHint"); warn.setWordWrap(True)
        c.add(warn)
        r = QHBoxLayout()
        b = button("Save and rebuild seed.iso", primary=True)
        b.clicked.connect(self._rebuild_seed)
        b2 = button("Open seed folder")
        b2.clicked.connect(lambda: self._open(paths.SEED_DIR))
        r.addWidget(b); r.addWidget(b2); r.addStretch()
        c.add(r)
        v.addWidget(c)

        c2 = Card("Install pipeline")
        steps = QLabel(
            "1   Live ISO    GPT/UEFI partitioning, pacstrap base, mesa, pipewire,\n"
            "                NetworkManager, openssh, zram\n"
            "2   chroot      locale, keymap, user, sudo, virtio initramfs, systemd-boot\n"
            "3   First login yay → end-4/dots-hyprland (setup install -f)\n"
            "                → pctrade/end4-pc as default Quickshell config\n"
            "                → SDDM graphical login enabled, temp sudo revoked")
        steps.setObjectName("CardHint")
        steps.setFont(QFont("Cascadia Mono", 9))
        c2.add(steps)
        v.addWidget(c2)
        v.addStretch()
        return page

    # ------------------------------------------------------------------ #
    def _page_tools(self) -> QWidget:
        page, v = self._page("Tools", "Getting text in, and managing the disk")

        c = Card("Send text to the VM",
                 "Direct text typing into the VM console via QEMU monitor. "
                 "Useful during the live ISO installer before guest clipboard agents start.")
        self.ed_send = QTextEdit()
        self.ed_send.setObjectName("Mono")
        self.ed_send.setPlaceholderText("Paste text here, then send…")
        self.ed_send.setFixedHeight(112)
        a11y(self.ed_send, "Text to send", "Text that will be typed into the guest")
        c.add(self.ed_send)
        self.send_bar = QProgressBar()
        self.send_bar.setVisible(False)
        self.send_bar.setTextVisible(False)
        c.add(self.send_bar)
        r = QHBoxLayout()
        b1 = button("Send", primary=True); b1.clicked.connect(lambda: self._send(self.ed_send.toPlainText()))
        b2 = button("Send + Enter"); b2.clicked.connect(lambda: self._send(self.ed_send.toPlainText() + "\n"))
        b3 = button("From clipboard")
        b3.clicked.connect(lambda: self.ed_send.setPlainText(QApplication.clipboard().text()))
        for b in (b1, b2, b3):
            r.addWidget(b)
        r.addStretch()
        c.add(r)
        v.addWidget(c)

        c2 = Card("SSH into the guest",
                  "The better route for real work: a normal Windows terminal with "
                  "working copy and paste. Needs the install finished and sshd running.")
        r2 = QHBoxLayout()
        bs = button("Open SSH session", primary=True); bs.clicked.connect(self._open_ssh)
        self.lbl_ssh = QLabel(""); self.lbl_ssh.setObjectName("CardHint")
        r2.addWidget(bs); r2.addWidget(self.lbl_ssh); r2.addStretch()
        c2.add(r2)
        v.addWidget(c2)

        c3 = Card("Virtual disk")
        self.lbl_disk = QLabel("—"); self.lbl_disk.setObjectName("CardHint")
        c3.add(self.lbl_disk)
        r3 = QHBoxLayout()
        b_snap_mgr = button("Manage snapshots…", primary=True)
        b_snap_mgr.clicked.connect(self._manage_snapshots)
        b_quick_snap = button("Quick snapshot")
        b_quick_snap.clicked.connect(self._snapshot)
        b_open_vm = button("Open VM folder")
        b_open_vm.clicked.connect(lambda: self._open(paths.ROOT))
        b_disk_ref = button("Refresh")
        b_disk_ref.clicked.connect(self._disk_info)
        for b in (b_snap_mgr, b_quick_snap, b_open_vm, b_disk_ref):
            r3.addWidget(b)
        r3.addStretch()
        c3.add(r3)
        r4 = QHBoxLayout()
        bd = button("Reset disk (erases the VM)", danger=True)
        bd.clicked.connect(self._reset_disk)
        r4.addWidget(bd); r4.addStretch()
        c3.add(r4)
        v.addWidget(c3)
        v.addStretch()
        QTimer.singleShot(400, self._disk_info)
        return page

    # ------------------------------------------------------------------ #
    def _page_settings(self) -> QWidget:
        page, v = self._page("Settings", "Appearance, behaviour and accessibility")

        c = Card("Appearance")
        f = QFormLayout(); f.setSpacing(10)
        self.cb_theme = QComboBox()
        self.cb_theme.addItems(["auto", "dark", "light"])
        self.cb_theme.setCurrentText(self.settings.theme)
        a11y(self.cb_theme, "Theme", "Auto follows the Windows app theme")
        f.addRow("Theme", self.cb_theme)
        self.cb_accent = QComboBox()
        self._accents = {
            "Blue": "#4f8cff", "Violet": "#8b5cf6", "Teal": "#14b8a6",
            "Emerald": "#10b981", "Amber": "#f59e0b", "Rose": "#f43f5e",
            "Arch blue": "#1793d1",
        }
        self.cb_accent.addItems(list(self._accents))
        for k, hexv in self._accents.items():
            if hexv.lower() == self.settings.accent.lower():
                self.cb_accent.setCurrentText(k)
        f.addRow("Accent", self.cb_accent)
        self.ck_translucent = QCheckBox("Translucent window backdrop (Mica)")
        self.ck_translucent.setChecked(self.settings.translucency)
        f.addRow("", self.ck_translucent)
        self.ck_gradient = QCheckBox("Gradient surfaces")
        self.ck_gradient.setChecked(self.settings.gradient)
        f.addRow("", self.ck_gradient)
        c.add(f)
        hint = QLabel("Translucency uses the Windows Mica backdrop and is ignored "
                      "automatically if the OS does not support it or high contrast "
                      "mode is active.")
        hint.setObjectName("CardHint"); hint.setWordWrap(True)
        c.add(hint)
        v.addWidget(c)

        ca = Card("Accessibility")
        fa = QFormLayout(); fa.setSpacing(10)
        sw = QWidget(); sl = QHBoxLayout(sw); sl.setContentsMargins(0, 0, 0, 0)
        self.sl_font = QSlider(Qt.Horizontal)
        self.sl_font.setRange(80, 160)
        self.sl_font.setSingleStep(5)
        self.sl_font.setPageStep(10)
        self.sl_font.setValue(self.settings.font_scale)
        a11y(self.sl_font, "Text size", "Scales all interface text between 80 and 160 percent")
        self.lbl_font = QLabel(f"{self.settings.font_scale}%")
        self.lbl_font.setFixedWidth(48)
        sl.addWidget(self.sl_font, 1); sl.addWidget(self.lbl_font)
        fa.addRow("Text size", sw)
        self.ck_motion = QCheckBox("Reduce motion (disable pulsing indicators)")
        self.ck_motion.setChecked(self.settings.reduce_motion)
        fa.addRow("", self.ck_motion)
        ca.add(fa)
        ka = QLabel("Keyboard: Ctrl+1…6 switch pages · Ctrl+R start · Ctrl+I install · "
                    "Ctrl+L logs · F1 about. Every control is reachable with Tab and "
                    "exposed to screen readers.")
        ka.setObjectName("CardHint"); ka.setWordWrap(True)
        ca.add(ka)
        v.addWidget(ca)

        cb_ = Card("Behaviour")
        fb = QFormLayout(); fb.setSpacing(10)
        self.ck_close_tray = QCheckBox("Closing the window keeps the app in the system tray")
        self.ck_close_tray.setChecked(self.settings.close_to_tray)
        fb.addRow("", self.ck_close_tray)
        self.ck_min_tray = QCheckBox("Minimise to tray instead of the taskbar")
        self.ck_min_tray.setChecked(self.settings.minimise_to_tray)
        fb.addRow("", self.ck_min_tray)
        self.ck_start_min = QCheckBox("Start minimised to tray")
        self.ck_start_min.setChecked(self.settings.start_minimised)
        fb.addRow("", self.ck_start_min)
        self.ck_autostart = QCheckBox("Start automatically when I sign in to Windows")
        self.ck_autostart.setChecked(self.settings.autostart)
        fb.addRow("", self.ck_autostart)
        self.ck_notify = QCheckBox("Show tray notifications")
        self.ck_notify.setChecked(self.settings.notifications)
        fb.addRow("", self.ck_notify)
        self.ck_confirm = QCheckBox("Confirm before force-stopping the VM")
        self.ck_confirm.setChecked(self.settings.confirm_force_stop)
        fb.addRow("", self.ck_confirm)
        cb_.add(fb)
        v.addWidget(cb_)

        cl = Card("Locations",
                  "Disks and ISOs are large. Put them on a drive with room.")
        fl = QFormLayout(); fl.setSpacing(10)

        rootrow = QHBoxLayout(); rootrow.setSpacing(8)
        self.lbl_root = QLabel(str(paths.ROOT)); self.lbl_root.setObjectName("CardHint")
        self.lbl_root.setWordWrap(True)
        b_open_root = button("Open folder")
        b_open_root.setToolTip("Open the VM data folder in Windows Explorer")
        b_open_root.clicked.connect(lambda: self._open(paths.ROOT))
        b_root = button("Change…")
        b_root.setToolTip("Choose where virtual disks, ISOs and seed files are kept")
        b_root.clicked.connect(self._choose_vm_root)
        rootrow.addWidget(self.lbl_root, 1); rootrow.addWidget(b_open_root); rootrow.addWidget(b_root)
        fl.addRow("VM data", rootrow)
        lq = QLabel(str(paths.QEMU_DIR) + ("" if paths.qemu_available() else "   (NOT FOUND)"))
        lq.setObjectName("CardHint"); lq.setWordWrap(True)
        fl.addRow("QEMU", lq)
        lc = QLabel(str(paths.CONFIG_DIR)); lc.setObjectName("CardHint"); lc.setWordWrap(True)
        fl.addRow("Settings", lc)
        cl.add(fl)
        rl = QHBoxLayout()
        b0 = button("Run setup wizard", primary=True)
        b0.clicked.connect(self.run_setup_wizard)
        b1 = button("Open settings folder"); b1.clicked.connect(lambda: self._open(paths.CONFIG_DIR))
        b2 = button("About"); b2.clicked.connect(self._about)
        rl.addWidget(b0); rl.addWidget(b1); rl.addWidget(b2); rl.addStretch()
        cl.add(rl)
        v.addWidget(cl)
        v.addStretch()
        return page

    # ------------------------------------------------------------------ #
    def _page_logs(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 18, 24, 24)
        v.setSpacing(14)
        t = QLabel("Logs"); t.setObjectName("PageTitle")
        s = QLabel("QEMU output and application events"); s.setObjectName("PageSub")
        v.addWidget(t); v.addWidget(s)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(8000)
        a11y(self.log, "Log output")
        v.addWidget(self.log, 1)
        r = QHBoxLayout()
        b1 = button("Clear"); b1.clicked.connect(self.log.clear)
        b2 = button("Show launch command"); b2.clicked.connect(
            lambda: self._log(self.runner.last_command() or "[no command yet]"))
        b3 = button("Copy all"); b3.clicked.connect(lambda: self._copy(self.log.toPlainText()))
        b4 = button("Save to file"); b4.clicked.connect(self._save_log)
        for b in (b1, b2, b3, b4):
            r.addWidget(b)
        r.addStretch()
        v.addLayout(r)
        return page

    # ------------------------------------------------------------------ #
    #  Wiring
    # ------------------------------------------------------------------ #
    def _wire(self) -> None:
        self.runner.output.connect(self._log)
        self.runner.failed.connect(self._error)
        self.runner.state_changed.connect(self._on_vm_state)
        self.runner.gl_crashed.connect(self._on_gl_crashed)

        self.monitor.finished.connect(self._send_done)
        self.monitor.progress.connect(self._send_progress)

        for w in (self.cb_theme, self.cb_accent):
            w.currentTextChanged.connect(self._settings_changed)
        for w in (self.ck_translucent, self.ck_gradient, self.ck_motion,
                  self.ck_close_tray, self.ck_min_tray, self.ck_start_min,
                  self.ck_autostart, self.ck_notify, self.ck_confirm):
            w.toggled.connect(self._settings_changed)
        self.sl_font.valueChanged.connect(self._font_changed)

    def _go(self, idx: int) -> None:
        self.stack.setCurrentIndex(idx)
        b = self.nav.button(idx)
        if b:
            b.setChecked(True)

    # ------------------------------------------------------------------ #
    #  Theme + settings
    # ------------------------------------------------------------------ #
    def apply_theme(self) -> None:
        pal = theme.resolve(self.settings.theme)
        app = QApplication.instance()
        app.setPalette(theme.qpalette(pal))
        app.setStyleSheet(theme.stylesheet(
            pal,
            gradient=self.settings.gradient,
            translucent=self.settings.translucency,
            font_scale=self.settings.font_scale,
            accent=self.settings.accent,
        ))
        theme.apply_backdrop(self, pal.name == "dark",
                             self.settings.translucency and self.settings.gradient)
        if hasattr(self, "backdrop"):
            self.backdrop.set_palette_(
                pal,
                depth=self.settings.gradient and not theme.high_contrast_active(),
                grain=self.settings.gradient and not self.settings.reduce_motion,
            )
        elevated_types = (Card, Stat, CommandSnippet)
        for widget in self.findChildren(QWidget):
            if isinstance(widget, elevated_types):
                elevate(widget, pal, enabled=self.settings.gradient
                        and not theme.high_contrast_active())
        if hasattr(self, "meters"):
            for m in self.meters.values():
                m.set_palette_(pal)
        self._palette = pal

    def _settings_changed(self) -> None:
        self.settings.theme = self.cb_theme.currentText()
        self.settings.accent = self._accents.get(self.cb_accent.currentText(), "#4f8cff")
        self.settings.translucency = self.ck_translucent.isChecked()
        self.settings.gradient = self.ck_gradient.isChecked()
        self.settings.reduce_motion = self.ck_motion.isChecked()
        self.settings.close_to_tray = self.ck_close_tray.isChecked()
        self.settings.minimise_to_tray = self.ck_min_tray.isChecked()
        self.settings.start_minimised = self.ck_start_min.isChecked()
        self.settings.notifications = self.ck_notify.isChecked()
        self.settings.confirm_force_stop = self.ck_confirm.isChecked()
        want_auto = self.ck_autostart.isChecked()
        if want_auto != self.settings.autostart:
            if self._set_autostart(want_auto):
                self.settings.autostart = want_auto
            else:
                self.toast.show_message("Could not change the Windows startup entry.")
                self.ck_autostart.setChecked(self.settings.autostart)
        self.settings.save()
        self.apply_theme()

    def _font_changed(self, val: int) -> None:
        self.lbl_font.setText(f"{val}%")
        self.settings.font_scale = val
        self.settings.save()
        self.apply_theme()

    def _set_autostart(self, enable: bool) -> bool:
        """Register in HKCU Run. Never touches machine-wide keys."""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            if enable:
                if paths.is_frozen():
                    cmd = f'"{sys.executable}" --tray'
                else:
                    pyw = Path(sys.executable).with_name("pythonw.exe")
                    launcher = pyw if pyw.exists() else Path(sys.executable)
                    cmd = f'"{launcher}" "{Path(__file__).parent.parent / "run.py"}" --tray'
                winreg.SetValueEx(key, paths.APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, paths.APP_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    #  Actions
    # ------------------------------------------------------------------ #
    def _collect(self) -> None:
        self.cfg.memory_mb = self.sp_mem.value()
        self.cfg.cpus = self.sp_cpu.value()
        self.cfg.accel = self.cb_accel.currentText()
        self.cfg.gpu = self.cb_gpu.currentText()
        self.cfg.display = self.cb_disp.currentText()
        # Never let a stale or hand-edited pairing reach QEMU.
        self.cfg.gpu, self.cfg.display, _why = qemu.safe_display_for(
            self.cfg.gpu, self.cfg.display)
        self.cfg.width = self.sp_w.value()
        self.cfg.height = self.sp_h.value()
        self.cfg.fullscreen = self.ck_fs.isChecked()
        self.cfg.keyboard = self.cb_kbd.currentText()
        self.cfg.keymap = self.cb_keymap.currentText()
        self.cfg.audio = self.ck_audio.isChecked()
        self.cfg.ssh_port = self.sp_ssh.value()
        self.cfg.username = self.ed_user.text().strip() or "arch"
        self.cfg.save()

    def _start(self, install: bool) -> None:
        if self.runner.is_running():
            self.toast.show_message("The VM is already running.")
            return
        self._collect()
        problems = self.cfg.validate()
        blocking = [p for p in problems if "QEMU not found" in p or "disk missing" in p.lower()]
        if blocking and install is False:
            self._error("\n".join(problems))
            return
        self.monitor.port = self.cfg.monitor_port
        self._log(f"[app] starting VM ({'install' if install else 'normal'} mode)")
        if self.runner.start(self.cfg, install):
            self.monitor.port = self.cfg.monitor_port
            self._log("[app] " + self.runner.last_command())
        self._refresh()

    def _on_gl_crashed(self, ran_for: float) -> None:
        """
        QEMU crashed inside its OpenGL path. Retreat to the display combination
        that cannot crash, once, and say so plainly.

        This is not something the setup wizard can pre-empt: the crash needs a
        guest actively submitting virgl commands, so a probe that merely starts
        QEMU and stops it passes every time.
        """
        if not self.cfg.fall_back_to_software():
            self._error(
                "QEMU crashed even without 3D acceleration. This is a problem "
                "with the QEMU build rather than the VM configuration - see the "
                "Logs page for the exit code.")
            return

        self.cfg.save()
        self.settings.gl_unusable = True      # so the wizard stops promising 3D
        self.settings.save()
        if hasattr(self, "cb_disp"):
            self.cb_disp.setCurrentText(self.cfg.display)
        if hasattr(self, "cb_gpu"):
            self.cb_gpu.setCurrentText(self.cfg.gpu)

        self._log("[app] switched to %s + %s after the GL crash"
                  % (self.cfg.display, self.cfg.gpu))
        self._await_first_boot = False

        QMessageBox.warning(
            self, "3D acceleration is not usable on this PC",
            "QEMU crashed %.0f seconds after starting, inside its OpenGL "
            "path.\n\n"
            "This QEMU build cannot share the rendered image with its own "
            "window on your system, and it crashes instead of falling back. "
            "Nothing is wrong with your PC or your VM.\n\n"
            "Graphics have been switched to %s + %s, which is stable. The "
            "desktop will run, drawn on the CPU rather than the GPU - so "
            "animations and blur will be slower.\n\n"
            "You can try 3D again from the Hardware page after updating QEMU."
            % (ran_for, self.cfg.display, self.cfg.gpu))

        if QMessageBox.question(
                self, paths.APP_NAME, "Start the VM again now?",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            QTimer.singleShot(600, lambda: self._start(False))

    def _on_vm_state(self, state: str) -> None:
        """
        React to the VM starting or stopping.

        bootstrap.sh powers the machine off rather than rebooting, because in
        install mode the ISO still holds bootindex=1 and a reboot would land
        back in the live environment. So a clean stop straight after an install
        run means the base system is on disk and wants booting from it - do
        that automatically rather than making the user work out why the VM
        vanished.
        """
        self._refresh()
        if state != "stopped" or not self._await_first_boot:
            return
        self._await_first_boot = False
        self._log("[app] install run finished; booting the installed system")
        self.toast.show_message(
            "Base install finished. Starting the VM from the disk - the "
            "desktop installs itself on this boot, then reboots into the "
            "login screen.", 0)
        QTimer.singleShot(2500, lambda: self._start(False))

    def _choose_vm_root(self) -> None:
        """
        Move where disks, ISOs and seed files live.

        The paths in vm.json are absolute, so they do not follow the root on
        their own - anything that pointed inside the old location is repointed
        here. Existing files are deliberately NOT moved: a virtual disk can be
        a hundred gigabytes, and silently copying that in the background is
        worse than telling you plainly where it still is.
        """
        old = Path(paths.ROOT)
        picked = QFileDialog.getExistingDirectory(
            self, "Choose where to keep VM disks and ISOs", str(old))
        if not picked:
            return
        new = Path(picked)
        if new == old:
            return

        try:
            new.mkdir(parents=True, exist_ok=True)
            probe = new / ".archvm-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as e:
            self._error("That folder is not writable:\n%s" % e)
            return

        from . import deps
        free = deps.free_gb(new)
        stays = [Path(p) for p in (self.cfg.disk, self.cfg.iso, self.cfg.seed_iso,
                                   self.cfg.ovmf_code, self.cfg.ovmf_vars)
                 if p and Path(p).exists() and _within(Path(p), old)]

        lines = ["Use this folder for VM data?", "", str(new), "",
                 "Free space: %.0f GB%s" % (
                     free, "" if free >= 60 else "   - below the 60 GB minimum")]
        if stays:
            lines += ["",
                      "%d existing file(s) stay in %s." % (len(stays), old),
                      "They are not copied. Move them across yourself to keep "
                      "them, or the setup wizard will create new ones here."]
        lines += ["", "ArchVM restarts to apply this."]

        if QMessageBox.question(
                self, "Change VM data location", "\n".join(lines),
                QMessageBox.Yes | QMessageBox.Cancel) != QMessageBox.Yes:
            return

        # Repoint anything that lived under the old root.
        for attr in ("disk", "iso", "seed_iso", "ovmf_code", "ovmf_vars"):
            cur = getattr(self.cfg, attr, "")
            if cur and _within(Path(cur), old):
                setattr(self.cfg, attr, str(new / Path(cur).relative_to(old)))
        self.cfg.save()

        self.settings.vm_root = str(new)
        self.settings.save()
        self.lbl_root.setText(str(new))

        if self.runner.is_running():
            self.toast.show_message(
                "Saved. Shut the VM down and restart ArchVM to use the new "
                "location.", 0)
            return
        self._restart_app()

    def _restart_app(self) -> None:
        """Relaunch, because paths are resolved once at import time."""
        if QMessageBox.question(
                self, paths.APP_NAME, "Restart ArchVM now?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            self.toast.show_message(
                "The new location applies next time you start ArchVM.", 0)
            return
        try:
            if paths.is_frozen():
                QProcess.startDetached(sys.executable, [])
            else:
                launcher = Path(__file__).resolve().parent.parent / "run.py"
                QProcess.startDetached(sys.executable, [str(launcher)])
        except Exception:
            pass
        self._force_quit = True
        QApplication.instance().quit()

    def _start_install_flow(self) -> None:
        """
        Boot the installer and type the install command once the live ISO has
        reached its root prompt. The delay is a fixed estimate - QEMU's monitor
        answers as soon as the process starts, not when the guest is ready - so
        the Overview page keeps a manual button as a fallback.
        """
        if self.runner.is_running():
            self.toast.show_message("The VM is already running.")
            return
        self._start(True)
        if not self.runner.is_running():
            return
        # bootstrap.sh powers off when it is done; _on_vm_state picks it up
        self._await_first_boot = True
        self._go(0)
        self._boot_wait = 45
        self.toast.show_message(
            "Booting the Arch installer. The command will be typed in "
            f"automatically in {self._boot_wait} seconds.", 0)

        def tick():
            self._boot_wait -= 1
            if not self.runner.is_running():
                self._boot_timer.stop()
                self.toast.show_message("The VM stopped before the installer ran.")
                return
            if self._boot_wait <= 0:
                self._boot_timer.stop()
                self._log("[app] typing the installer command")
                self._send(INSTALL_CMD + "\n")
                self.toast.show_message(
                    "Installer command sent. If nothing happened, click into the VM "
                    "window and press “Type it into the VM”.")
            else:
                self.toast.show_message(
                    "Booting the Arch installer. Typing the command in "
                    f"{self._boot_wait} seconds…", 0)

        self._boot_timer = QTimer(self)
        self._boot_timer.timeout.connect(tick)
        self._boot_timer.start(1000)

    def _send_install_cmd(self) -> None:
        if hasattr(self, "_boot_timer") and self._boot_timer.isActive():
            self._boot_timer.stop()
            self.toast.show_message("Installer command sent.")
        self._send(INSTALL_CMD + "\n")

    def run_setup_wizard(self) -> None:
        from .onboarding import Onboarding
        w = Onboarding(self.cfg, self.settings, self)
        w.finished_setup.connect(lambda: self.toast.show_message("Setup finished."))
        w.exec()
        self._disk_info()
        self._refresh()

    def _shutdown(self) -> None:
        if not self.runner.is_running():
            return
        self.btn_shutdown.setEnabled(False)
        ok, _ = self.monitor.command("system_powerdown")
        if ok:
            self.toast.show_message("Shutdown requested. Guest is powering down…", 8000)
            self.state_lbl.setText("Shutting down…")
            self._log("[app] system_powerdown sent")
        else:
            self.btn_shutdown.setEnabled(True)
            self.toast.show_message("Could not reach the monitor; use Force stop.")

    def _force_stop(self) -> None:
        if not self.runner.is_running():
            return
        if self.settings.confirm_force_stop:
            if QMessageBox.question(
                self, "Force stop",
                "Force-stop the VM?\n\nThis is like pulling the power cable and can "
                "leave the guest filesystem dirty. Prefer Shut down when the guest "
                "is responsive.") != QMessageBox.Yes:
                return
        self.runner.stop()
        self._log("[app] force-stopped")

    def _send(self, text: str) -> None:
        if not text:
            return
        if not self.runner.is_running():
            self.toast.show_message("Start the VM before sending text.")
            return
        bad = qemu.unsupported_chars(text)
        if bad:
            self._log("[app] characters that cannot be typed: " + " ".join(bad))
        self.send_bar.setVisible(True)
        self.send_bar.setRange(0, 100)
        self.monitor.type_text(text)

    def _send_progress(self, done: int, total: int) -> None:
        if total:
            self.send_bar.setValue(int(done / total * 100))

    def _send_done(self, ok: bool, msg: str) -> None:
        self.send_bar.setVisible(False)
        self._log("[monitor] " + msg)
        self.toast.show_message(msg)

    def _open_ssh(self) -> None:
        if not self.runner.is_running():
            self.toast.show_message("Start the VM before opening an SSH session.")
            return
        user = self.ed_user.text().strip() or "arch"
        port = self.sp_ssh.value()
        cmd = f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL -o LogLevel=ERROR -p {port} {user}@127.0.0.1"
        if not shutil.which("ssh"):
            self._error("The Windows OpenSSH client is not installed.\n\n"
                        "Add it from Settings > System > Optional features.")
            return
        try:
            if shutil.which("wt"):
                subprocess.Popen(["wt", "-w", "0", "nt", "--title", "ArchVM SSH",
                                  "cmd", "/k", cmd])
            else:
                subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", cmd])
            self._log(f"[app] {cmd}")
        except Exception as e:
            self._error(f"Could not open a terminal: {e}")

    def _match_host(self) -> None:
        g = QApplication.primaryScreen().geometry()
        self.sp_w.setValue(g.width())
        self.sp_h.setValue(g.height())
        self.ck_fs.setChecked(True)
        self.toast.show_message(f"Set to {g.width()}×{g.height()} with fullscreen on.")

    # ------------------------------------------------------------------ #
    def _read_vmconf(self) -> dict:
        vals: dict[str, str] = {}
        p = paths.SEED_DIR / "vm.conf"
        try:
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, val = line.partition("=")
                        vals[k.strip()] = val.strip()
        except OSError:
            pass
        return vals

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
        vals.setdefault("AUTO_REBOOT", "yes")
        body = "# regenerated by ArchVM\n" + "".join(f"{k}={v}\n" for k, v in vals.items())
        try:
            (paths.SEED_DIR / "vm.conf").write_bytes(body.encode("utf-8"))  # LF only
        except OSError as e:
            self._error(f"Could not write vm.conf: {e}")
            return

        # In-process: a frozen build has no build_seed.py, and sys.executable
        # is ArchVM.exe there, so shelling out relaunched the app instead.
        from . import seedbuild
        paths.deploy_seed_scripts()
        ok, msg = seedbuild.build()
        self._log("[seed] " + msg)
        if ok:
            self.toast.show_message("seed.iso rebuilt with your settings.")
        else:
            self._error(msg)

    def _disk_info(self) -> None:
        virt, alloc = qemu.disk_summary(self.cfg.disk)
        self.lbl_disk.setText(f"virtual {virt}   ·   allocated {alloc}")
        if "disk" in self.stats:
            self.stats["disk"].set(virt.replace(" GiB", " GB"))

    def _snapshot(self) -> None:
        if self.runner.is_running():
            self.toast.show_message("Stop the VM before snapshotting.")
            return
        default_name = f"snap-{time.strftime('%Y%m%d-%H%M')}"
        name, ok = QInputDialog.getText(self, "Create snapshot", "Snapshot name:", text=default_name)
        if ok and name.strip():
            clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip())
            self._log("[qemu-img] " + qemu.qemu_img("snapshot", "-c", clean_name, self.cfg.disk))
            self.toast.show_message(f"Snapshot '{clean_name}' created.")
            self._disk_info()

    def _snapshot_list(self) -> None:
        self._manage_snapshots()

    def _manage_snapshots(self) -> None:
        if not Path(self.cfg.disk).exists():
            self.toast.show_message("Virtual disk not found.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("VM Snapshots")
        dlg.setModal(True)
        dlg.setStyleSheet(self.styleSheet())
        dlg.setMinimumSize(580, 400)
        v = QVBoxLayout(dlg)
        v.setSpacing(12)

        lbl = QLabel(f"Snapshots for {Path(self.cfg.disk).name}")
        lbl.setObjectName("CardTitle")
        v.addWidget(lbl)

        hint = QLabel("Snapshots capture disk state. Stop the VM before restoring or deleting snapshots.")
        hint.setObjectName("CardHint")
        v.addWidget(hint)

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Name / Tag", "Created Date", "Size"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        v.addWidget(table, 1)

        def reload_table():
            table.setRowCount(0)
            out = qemu.qemu_img("snapshot", "-l", self.cfg.disk)
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            header_passed = False
            for line in lines:
                if line.startswith("ID") and "TAG" in line:
                    header_passed = True
                    continue
                if not header_passed:
                    continue
                parts = line.split()
                if len(parts) >= 5:
                    tag = parts[1]
                    size = f"{parts[2]} {parts[3]}"
                    date = f"{parts[4]} {parts[5]}" if len(parts) >= 6 else parts[4]
                    row = table.rowCount()
                    table.insertRow(row)
                    table.setItem(row, 0, QTableWidgetItem(tag))
                    table.setItem(row, 1, QTableWidgetItem(date))
                    table.setItem(row, 2, QTableWidgetItem(size))

        reload_table()

        btn_row = QHBoxLayout()
        b_create = button("New snapshot…")
        b_restore = button("Restore selected", primary=True)
        b_delete = button("Delete selected", danger=True)
        b_close = button("Close")

        def create_snap():
            if self.runner.is_running():
                self.toast.show_message("Stop the VM before creating a snapshot.")
                return
            default_name = f"snap-{time.strftime('%Y%m%d-%H%M')}"
            name, ok = QInputDialog.getText(dlg, "Create snapshot", "Snapshot name:", text=default_name)
            if ok and name.strip():
                clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip())
                self._log("[qemu-img] " + qemu.qemu_img("snapshot", "-c", clean_name, self.cfg.disk))
                reload_table()
                self._disk_info()
                self.toast.show_message(f"Snapshot '{clean_name}' created.")

        def restore_snap():
            if self.runner.is_running():
                QMessageBox.warning(dlg, "VM Running", "Stop the VM before restoring a snapshot.")
                return
            sel = table.selectedItems()
            if not sel:
                QMessageBox.information(dlg, "Select Snapshot", "Please select a snapshot to restore.")
                return
            tag = table.item(table.currentRow(), 0).text()
            if QMessageBox.question(
                    dlg, "Restore Snapshot",
                    f"Restore virtual disk to snapshot '{tag}'?\n\n"
                    "All changes made since this snapshot was created will be lost.",
                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
            out = qemu.qemu_img("snapshot", "-a", tag, self.cfg.disk)
            self._log(f"[qemu-img snapshot -a] {out}")
            self.toast.show_message(f"Restored snapshot '{tag}'.")
            self._disk_info()
            dlg.accept()

        def delete_snap():
            if self.runner.is_running():
                QMessageBox.warning(dlg, "VM Running", "Stop the VM before deleting a snapshot.")
                return
            sel = table.selectedItems()
            if not sel:
                QMessageBox.information(dlg, "Select Snapshot", "Please select a snapshot to delete.")
                return
            tag = table.item(table.currentRow(), 0).text()
            if QMessageBox.question(
                    dlg, "Delete Snapshot",
                    f"Permanently delete snapshot '{tag}'?",
                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
            out = qemu.qemu_img("snapshot", "-d", tag, self.cfg.disk)
            self._log(f"[qemu-img snapshot -d] {out}")
            reload_table()
            self._disk_info()
            self.toast.show_message(f"Deleted snapshot '{tag}'.")

        b_create.clicked.connect(create_snap)
        b_restore.clicked.connect(restore_snap)
        b_delete.clicked.connect(delete_snap)
        b_close.clicked.connect(dlg.reject)

        btn_row.addWidget(b_create)
        btn_row.addWidget(b_restore)
        btn_row.addWidget(b_delete)
        btn_row.addStretch()
        btn_row.addWidget(b_close)
        v.addLayout(btn_row)

        dlg.exec()

    def _reset_disk(self) -> None:
        if self.runner.is_running():
            self.toast.show_message("Stop the VM first.")
            return
        if QMessageBox.warning(
                self, "Erase VM disk",
                "This permanently deletes the virtual disk and everything installed "
                "in the VM.\n\nYour Windows files are not affected.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        p = Path(self.cfg.disk)
        try:
            if p.exists():
                p.unlink()
        except OSError as e:
            self._error(f"Could not delete the disk: {e}")
            return
        self._log("[qemu-img] " + qemu.qemu_img("create", "-f", "qcow2", str(p), "120G"))
        src = paths.QEMU_DIR / "share" / "edk2-i386-vars.fd"
        try:
            if src.exists():
                shutil.copyfile(src, self.cfg.ovmf_vars)
        except OSError:
            pass
        self._disk_info()
        self.toast.show_message("Fresh disk created. Run the installer again.")

    def _save_log(self) -> None:
        fn, _ = QFileDialog.getSaveFileName(
            self, "Save log", str(paths.LOG_DIR / "archvm.log"), "Log files (*.log *.txt)")
        if fn:
            try:
                Path(fn).write_text(self.log.toPlainText(), encoding="utf-8")
                self.toast.show_message(f"Saved to {fn}")
            except OSError as e:
                self._error(str(e))

    def _about(self) -> None:
        QMessageBox.about(
            self, f"About {paths.APP_NAME}",
            f"<b>{paths.APP_NAME}</b> {paths.APP_VERSION}<br><br>"
            "A QEMU control panel for running Arch Linux with Hyprland on Windows, "
            "since virt-manager is Linux-only.<br><br>"
            f"VM data: {paths.ROOT}<br>"
            f"QEMU: {paths.QEMU_DIR}<br>"
            f"Settings: {paths.CONFIG_DIR}<br><br>"
            "Desktop: end-4/dots-hyprland (illogical-impulse) with the "
            "pctrade/end4-pc Quickshell fork.")

    # ------------------------------------------------------------------ #
    def _log(self, text: str) -> None:
        if text and text.strip():
            self.log.appendPlainText(text.rstrip())
            self.log.moveCursor(QTextCursor.End)

    def _error(self, msg: str) -> None:
        self._log("[error] " + msg)
        first = msg.strip().splitlines()[0] if msg.strip() else "Something went wrong"
        self.alert.show_alert(first, kind="error",
                              action="Details", on_action=lambda: self._go(5))
        QMessageBox.critical(self, "Problem", msg)

    def _copy(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.toast.show_message("Copied to clipboard.")

    def _open(self, path: Path) -> None:
        try:
            os.startfile(str(path))
        except Exception as e:
            self._error(f"Could not open {path}: {e}")

    def _refresh(self) -> None:
        run = self.runner.is_running()
        pal = getattr(self, "_palette", theme.LIGHT)

        if run and self._vm_started_at is None:
            self._vm_started_at = time.time()
        elif not run:
            self._vm_started_at = None

        self.dot.set_state(pal.green if run else pal.muted,
                           "VM running" if run else "VM stopped",
                           pulse=run and not self.settings.reduce_motion)
        self.state_lbl.setText("Running" if run else "Stopped")

        self.btn_start.setEnabled(not run)
        self.btn_install.setEnabled(not run)
        self.btn_primary.setEnabled(not run)
        self.btn_stop.setEnabled(run)
        self.btn_shutdown.setEnabled(run)
        if hasattr(self, "btn_hero_ssh"):
            self.btn_hero_ssh.setEnabled(run)
        self.cmd_card.setVisible(run and self.runner.install_mode)

        if hasattr(self, "sp_mem"):
            for w in (self.sp_mem, self.sp_cpu, self.cb_accel, self.cb_gpu, self.cb_disp, self.sp_w, self.sp_h, self.sp_ssh):
                w.setEnabled(not run)

        # Re-probe the guest occasionally rather than every tick - qemu-img
        # spawns a process and this runs on a timer.
        self._tick = getattr(self, "_tick", 0) + 1
        if self._tick % 12 == 1 and not run:
            self._installed_cache = self._guest_installed()
        self._refresh_hero()

        if hasattr(self, "stats"):
            self.stats["mem"].set(f"{self.cfg.memory_mb // 1024} GB", "Allocated RAM")
            self.stats["cpu"].set(str(self.cfg.cpus), "Host Cores")
            self.stats["res"].set(f"{self.cfg.width}×{self.cfg.height}", self.cfg.gpu)
            if self._tick % 12 == 1 or self.stats["disk"].value.text() in ("-", "", "—"):
                _v, alloc = qemu.disk_summary(self.cfg.disk)
                disp_alloc = alloc if alloc not in ("-", "disk not found") else "0 GB"
                self.stats["disk"].set(disp_alloc, "Virtual Disk")
            if self._vm_started_at:
                secs = int(time.time() - self._vm_started_at)
                h, m = divmod(secs // 60, 60)
                self.stats["uptime"].set(f"{h}:{m:02d}" if h else f"{secs // 60}m", "Session Active")
            else:
                self.stats["uptime"].set("—", "VM Stopped")

        if hasattr(self, "meters") and self._tick % 3 == 1:
            self._refresh_meters()

        if hasattr(self, "lbl_ssh"):
            u = self.ed_user.text().strip() or "arch"
            self.lbl_ssh.setText(f"{u}@127.0.0.1 : {self.sp_ssh.value()}")

    def _refresh_meters(self) -> None:
        try:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            used = m.ullTotalPhys - m.ullAvailPhys
            self.meters["ram"].set_value(
                m.dwMemoryLoad / 100.0,
                f"{used / 1073741824:.1f} / {m.ullTotalPhys / 1073741824:.1f} GB")
        except Exception:
            self.meters["ram"].set_value(0, "unavailable")

        try:
            total, _used, free = shutil.disk_usage(Path(self.cfg.disk).anchor)
            self.meters["disk"].set_value(
                1 - (free / total),
                f"{free / 1073741824:.0f} GB free of {total / 1073741824:.0f} GB")
        except Exception:
            self.meters["disk"].set_value(0, "unavailable")

    # ------------------------------------------------------------------ #
    def force_quit(self) -> None:
        self._force_quit = True
        self.close()

    def changeEvent(self, e) -> None:
        if (e.type() == e.Type.WindowStateChange
                and self.isMinimized() and self.settings.minimise_to_tray):
            QTimer.singleShot(0, self.hide)
        super().changeEvent(e)

    def closeEvent(self, e) -> None:
        self._collect()
        self.settings.window_w = self.width()
        self.settings.window_h = self.height()
        self.settings.save()

        if not self._force_quit and self.settings.close_to_tray:
            e.ignore()
            self.hide()
            self.request_quit.emit()      # tray shows a hint
            return

        if self.runner.is_running():
            if QMessageBox.question(
                    self, "VM still running",
                    "The VM is still running. Quit anyway and force-stop it?"
            ) != QMessageBox.Yes:
                e.ignore()
                self._force_quit = False
                return
            self.runner.stop()
        e.accept()
