"""
First-run setup wizard.

Scans the machine, installs or downloads whatever is missing (asking for
administrator rights once, when needed), configures the guest, and finishes
with a plain-language summary of what the user still has to do.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QObject, Signal, QTimer, QSize
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QLineEdit, QSpinBox, QCheckBox, QFormLayout, QProgressBar,
    QPlainTextEdit, QScrollArea, QFrame, QSizePolicy, QApplication, QMessageBox,
)

from . import deps, hostinfo, icons, paths, theme
from .config import AppSettings, VMConfig, INSTALL_CMD
from .deps import Status
from .widgets import Backdrop, Card, Chip, a11y, button, hline

STEPS = ["Welcome", "System check", "Configure", "Install", "Done"]

GLYPH = {
    Status.OK: "✓", Status.MISSING: "•", Status.WARN: "!",
    Status.BLOCKED: "✕", Status.FAILED: "✕", Status.WORKING: "…",
    Status.UNKNOWN: "·",
}


def _colour(pal, st: Status) -> str:
    return {
        Status.OK: pal.green, Status.WARN: pal.amber,
        Status.BLOCKED: pal.red, Status.FAILED: pal.red,
        Status.MISSING: pal.muted, Status.WORKING: pal.accent,
        Status.UNKNOWN: pal.muted,
    }.get(st, pal.muted)


# --------------------------------------------------------------------------- #
class CheckRow(QWidget):
    def __init__(self, check: deps.Check, pal, parent=None):
        super().__init__(parent)
        self.check = check
        self.pal = pal
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 5, 0, 5)
        h.setSpacing(12)

        self.mark = QLabel("·")
        self.mark.setFixedWidth(20)
        self.mark.setAlignment(Qt.AlignCenter)
        f = QFont(); f.setPointSize(12); f.setBold(True)
        self.mark.setFont(f)

        col = QVBoxLayout()
        col.setSpacing(1)
        self.title = QLabel(check.title)
        tf = QFont(); tf.setBold(True)
        self.title.setFont(tf)
        self.detail = QLabel(check.why)
        self.detail.setObjectName("CardHint")
        self.detail.setWordWrap(True)
        col.addWidget(self.title)
        col.addWidget(self.detail)

        self.badge = QLabel("")
        self.badge.setObjectName("CardHint")
        self.badge.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        h.addWidget(self.mark)
        h.addLayout(col, 1)
        h.addWidget(self.badge)
        self.setAccessibleName(check.title)

    def refresh(self) -> None:
        c = self.check
        col = _colour(self.pal, c.status)
        self.mark.setText(GLYPH.get(c.status, "·"))
        self.mark.setStyleSheet(f"color: {col};")
        self.detail.setText(c.detail or c.why)
        label = {
            Status.OK: "Ready", Status.MISSING: "Will install",
            Status.WARN: "Note", Status.BLOCKED: "Needs you",
            Status.FAILED: "Failed", Status.WORKING: "Working…",
            Status.UNKNOWN: "",
        }.get(c.status, "")
        if c.status is Status.MISSING and c.needs_admin:
            label = "Will install (admin)"
        self.badge.setText(label)
        self.badge.setStyleSheet(f"color: {col};")
        self.setAccessibleDescription(f"{c.title}: {label}. {c.detail}")


# --------------------------------------------------------------------------- #
class Worker(QObject):
    """Runs the fixes off the UI thread."""
    log = Signal(str)
    progress = Signal(int, int, str)
    step = Signal(str, str)            # check id, status value
    done = Signal(bool, bool)          # success, reboot_required

    def __init__(self, checks: list[deps.Check], parent=None):
        super().__init__(parent)
        self.checks = checks
        self.cancelled = False

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        rep = deps.Reporter(self.log.emit,
                            lambda c, t, n="": self.progress.emit(c, t, n))
        reboot = False
        ok_all = True

        todo = [c for c in self.checks if c.status is Status.MISSING and c.fixable]
        admin = [c for c in todo if c.admin_script]
        local = [c for c in todo if not c.admin_script]

        if not todo:
            self.log.emit("Everything is already in place — nothing to install.")

        # One elevated batch, so the user sees a single UAC prompt.
        if admin:
            names = ", ".join(c.title for c in admin)
            self.log.emit(f"These need administrator rights: {names}")
            script = "\n".join(c.admin_script for c in admin)
            for c in admin:
                self.step.emit(c.id, Status.WORKING.value)
            if deps.run_elevated(script, rep):
                for c in admin:
                    c.run_detect()
                    self.step.emit(c.id, c.status.value)
                    if c.requires_reboot:
                        reboot = True
            else:
                for c in admin:
                    c.run_detect()
                    if c.status is Status.MISSING:
                        c.status = Status.FAILED
                        c.detail = "Administrator step was declined or failed."
                    self.step.emit(c.id, c.status.value)
                ok_all = False

        for c in local:
            if self.cancelled:
                break
            rep.cancelled = False
            self.log.emit(f"— {c.title}")
            c.status = Status.WORKING
            self.step.emit(c.id, c.status.value)
            try:
                good = bool(c.fix(rep))
            except Exception as e:
                self.log.emit(f"  error: {e}")
                good = False
            c.run_detect()
            if not good and c.status is not Status.OK:
                c.status = Status.FAILED
                ok_all = False
            self.step.emit(c.id, c.status.value)

        self.done.emit(ok_all, reboot)


# --------------------------------------------------------------------------- #
class Onboarding(QDialog):
    finished_setup = Signal()

    def __init__(self, cfg: VMConfig, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.settings = settings
        self.pal = theme.resolve(settings.theme)
        self.checks = deps.build_checks()
        self.rows: dict[str, CheckRow] = {}
        self.worker: Worker | None = None
        self.reboot_required = False

        self.setWindowTitle(f"{paths.APP_NAME} Setup")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(860, 640)
        self.resize(900, 680)
        self._build()
        QTimer.singleShot(120, self._scan)

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        self.backdrop = Backdrop(self.pal, self)
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.addWidget(self.backdrop)

        root = QWidget(self.backdrop)
        root.setObjectName("Root")
        outer = QVBoxLayout(self.backdrop)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # step rail
        rail = QWidget()
        rl = QHBoxLayout(rail)
        rl.setContentsMargins(30, 20, 30, 14)
        rl.setSpacing(10)
        self.step_labels: list[QLabel] = []
        for i, name in enumerate(STEPS):
            lab = QLabel(f"{i + 1}  {name}")
            lab.setObjectName("CardHint")
            self.step_labels.append(lab)
            rl.addWidget(lab)
            if i < len(STEPS) - 1:
                d = QLabel("—")
                d.setObjectName("CardHint")
                rl.addWidget(d)
        rl.addStretch()
        v.addWidget(rail)
        v.addWidget(hline())

        self.stack = QStackedWidget()
        for p in (self._p_welcome(), self._p_check(), self._p_config(),
                  self._p_install(), self._p_done()):
            self.stack.addWidget(p)
        v.addWidget(self.stack, 1)

        v.addWidget(hline())
        nav = QHBoxLayout()
        nav.setContentsMargins(30, 14, 30, 18)
        self.btn_back = button("Back")
        self.btn_back.clicked.connect(self._back)
        self.btn_skip = button("Skip setup", ghost=True)
        self.btn_skip.clicked.connect(self._skip)
        self.btn_next = button("Continue", primary=True)
        self.btn_next.clicked.connect(self._next)
        nav.addWidget(self.btn_back)
        nav.addWidget(self.btn_skip)
        nav.addStretch()
        nav.addWidget(self.btn_next)
        v.addLayout(nav)
        self._sync_rail()

    def _panel(self, title: str, sub: str):
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(30, 24, 30, 20)
        lay.setSpacing(14)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        s = QLabel(sub)
        s.setObjectName("PageSub")
        s.setWordWrap(True)
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(4)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        return sa, lay

    # ------------------------------------------------------------------ #
    def _p_welcome(self) -> QWidget:
        page, v = self._panel(
            "Let's set up Arch Linux",
            "This wizard checks what your PC already has, installs whatever is "
            "missing, and prepares a virtual machine running Arch with the "
            "Hyprland desktop.")
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(QSize(64, 64)))
        head.addWidget(logo)
        head.addSpacing(12)
        txt = QLabel("Nothing is changed on your Windows installation apart from "
                     "installing QEMU and enabling the Windows Hypervisor Platform, "
                     "both of which you will be asked to approve.")
        txt.setWordWrap(True)
        head.addWidget(txt, 1)
        v.addLayout(head)

        c = Card("What this will do")
        for line in (
            "Check virtualization support, QEMU, disk space and memory",
            "Install anything missing — one administrator prompt, not several",
            "Download the Arch Linux ISO and verify it against the official checksum",
            "Create a 120 GB virtual disk that only grows as you use it",
            "Build the automated installer that sets up Hyprland for you",
        ):
            row = QHBoxLayout()
            b = QLabel("•"); b.setFixedWidth(14)
            l = QLabel(line); l.setWordWrap(True)
            row.addWidget(b); row.addWidget(l, 1)
            c.add(row)
        v.addWidget(c)

        c2 = Card("A note about your graphics card",
                  "Your RTX 3050 cannot be passed through to a virtual machine on "
                  "Windows — Hyper-V DDA is Windows Server only, and QEMU's Windows "
                  "accelerator has no PCIe passthrough. The VM uses virgl instead, "
                  "which is GPU-accelerated OpenGL. Hyprland will be smooth, but this "
                  "is not the same as running Arch on the bare metal.")
        v.addWidget(c2)
        v.addStretch()
        return page

    # ------------------------------------------------------------------ #
    def _p_check(self) -> QWidget:
        page, v = self._panel(
            "Checking your PC",
            "Anything marked “Will install” is handled for you on the next step.")
        self.check_card = Card()
        v.addWidget(self.check_card)

        self.check_summary = QLabel("Scanning…")
        self.check_summary.setWordWrap(True)
        v.addWidget(self.check_summary)

        r = QHBoxLayout()
        b = button("Scan again")
        b.clicked.connect(self._scan)
        r.addWidget(b)
        r.addStretch()
        v.addLayout(r)
        v.addStretch()
        return page

    # ------------------------------------------------------------------ #
    def _p_config(self) -> QWidget:
        page, v = self._panel(
            "Set up your Arch account",
            "Everything below was read from your Windows settings. Change anything "
            "you like — these are only starting points.")
        vals = self._read_vmconf()
        self.host = hostinfo.cached()

        det = Card("Detected from Windows",
                   "Used as the defaults for this virtual machine.")
        for note in self.host.detected:
            row = QHBoxLayout()
            tick = QLabel("✓")
            tick.setFixedWidth(16)
            tick.setStyleSheet("color: %s; font-weight: 700;" % self.pal.green)
            lab = QLabel(note)
            lab.setObjectName("CardHint")
            lab.setWordWrap(True)
            row.addWidget(tick)
            row.addWidget(lab, 1)
            det.add(row)
        rr = QHBoxLayout()
        bre = button("Re-detect")
        bre.clicked.connect(self._redetect)
        rr.addWidget(bre)
        rr.addStretch()
        det.add(rr)
        v.addWidget(det)

        c = Card("Account")
        f = QFormLayout(); f.setSpacing(10)
        self.ed_user = QLineEdit(vals.get("USERNAME") or self.host.username)
        self.ed_pass = QLineEdit(vals.get("USERPASS", "arch"))
        self.ed_host = QLineEdit(vals.get("HOSTNAME") or self.host.hostname)
        self.ed_tz = QLineEdit(vals.get("TIMEZONE") or self.host.timezone)
        for w, n in ((self.ed_user, "Username"), (self.ed_pass, "Password"),
                     (self.ed_host, "Computer name"), (self.ed_tz, "Timezone")):
            a11y(w, n)
            f.addRow(n, w)
        c.add(f)
        note = QLabel("Stored in plain text inside the installer image — fine for a "
                      "virtual machine, but do not reuse a password that matters.")
        note.setObjectName("CardHint"); note.setWordWrap(True)
        c.add(note)
        v.addWidget(c)

        h = self.host
        c2 = Card("Virtual hardware",
                  f"Sized from your {h.ram_gb:.0f} GB of RAM and {h.logical_cpus} "
                  "logical CPUs, leaving Windows enough to stay responsive.")
        f2 = QFormLayout(); f2.setSpacing(10)
        self.sp_mem = QSpinBox()
        self.sp_mem.setRange(2048, max(4096, int(h.ram_gb * 1024) - 2048))
        self.sp_mem.setSingleStep(1024); self.sp_mem.setSuffix("  MB")
        self.sp_mem.setValue(h.suggested_memory_mb)
        a11y(self.sp_mem, "Memory")
        f2.addRow("Memory", self.sp_mem)
        self.sp_cpu = QSpinBox(); self.sp_cpu.setRange(1, h.logical_cpus)
        self.sp_cpu.setValue(h.suggested_cpus)
        a11y(self.sp_cpu, "CPU cores")
        f2.addRow("CPU cores", self.sp_cpu)

        resw = QWidget(); rl = QHBoxLayout(resw); rl.setContentsMargins(0, 0, 0, 0)
        self.sp_w = QSpinBox(); self.sp_w.setRange(640, 3840)
        self.sp_w.setValue(h.display.width)
        self.sp_h = QSpinBox(); self.sp_h.setRange(480, 2160)
        self.sp_h.setValue(h.display.height)
        a11y(self.sp_w, "Display width"); a11y(self.sp_h, "Display height")
        rl.addWidget(self.sp_w); rl.addWidget(QLabel("×")); rl.addWidget(self.sp_h)
        rl.addWidget(Chip("matches your screen"))
        f2.addRow("Resolution", resw)
        c2.add(f2)
        note2 = QLabel(
            f"Your display reports {h.display.scale_percent}% scaling. The VM runs at "
            "native pixels and Hyprland does its own scaling, so the guest is set to "
            "the full panel resolution rather than the scaled size.")
        note2.setObjectName("CardHint"); note2.setWordWrap(True)
        c2.add(note2)
        v.addWidget(c2)

        c3 = Card("Ready to install")
        self.ck_confirm = QCheckBox(
            "I understand this creates and erases a virtual disk inside "
            "ArchVM's own folder. My Windows files are not touched.")
        self.ck_confirm.setChecked(False)
        a11y(self.ck_confirm, "Confirm disk creation")
        self.ck_confirm.toggled.connect(lambda _: self._sync_nav())
        c3.add(self.ck_confirm)
        self.ck_autostart_install = QCheckBox(
            "When setup finishes, start the Arch installation automatically")
        self.ck_autostart_install.setChecked(True)
        c3.add(self.ck_autostart_install)
        v.addWidget(c3)
        v.addStretch()
        return page

    # ------------------------------------------------------------------ #
    def _p_install(self) -> QWidget:
        page, v = self._panel(
            "Setting things up",
            "You may see a Windows administrator prompt. Approve it so the missing "
            "components can be installed.")
        self.install_card = Card()
        v.addWidget(self.install_card)

        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        self.bar.setRange(0, 0)
        v.addWidget(self.bar)
        self.bar_note = QLabel("")
        self.bar_note.setObjectName("CardHint")
        v.addWidget(self.bar_note)

        self.install_log = QPlainTextEdit()
        self.install_log.setReadOnly(True)
        self.install_log.setMinimumHeight(190)
        a11y(self.install_log, "Setup progress log")
        v.addWidget(self.install_log, 1)
        return page

    # ------------------------------------------------------------------ #
    def _p_done(self) -> QWidget:
        page, v = self._panel("You're ready", "")
        self.done_sub = QLabel("")
        self.done_sub.setWordWrap(True)
        v.addWidget(self.done_sub)

        self.done_todo = Card("What you need to do")
        v.addWidget(self.done_todo)

        c = Card("The shortcuts that matter",
                 "Press Super + / inside the desktop at any time for the full list.")
        grid = QVBoxLayout()
        for keys, what in (
            ("Super", "App launcher — just tap it"),
            ("Super + Q", "Close the focused window"),
            ("Super + Return", "Terminal"),
            ("Super + E", "File manager"),
            ("Super + W", "Browser"),
            ("Super + Tab", "Workspace overview"),
            ("Super + 1…0", "Switch workspace"),
            ("Super + Alt + 1…0", "Move window to workspace"),
            ("Super + F", "Fullscreen the window"),
            ("Super + A / Super + N", "Left sidebar / notifications"),
            ("Super + /", "Show every keybind"),
            ("Super + Escape", "Settings panel"),
            ("Super + L", "Lock the screen"),
        ):
            row = QHBoxLayout()
            k = QLabel(keys)
            k.setObjectName("Cmd")
            k.setFixedWidth(190)
            k.setAlignment(Qt.AlignCenter)
            d = QLabel(what)
            d.setWordWrap(True)
            row.addWidget(k)
            row.addWidget(d, 1)
            grid.addLayout(row)
        c.add(grid)
        v.addWidget(c)

        c2 = Card("Two things that will trip you up",
                  "Ctrl + Alt + Delete never reaches the guest — Windows takes it "
                  "first; use the power icon in the bar instead. And Ctrl + Alt + F "
                  "is QEMU's own fullscreen toggle, not Hyprland's.")
        v.addWidget(c2)
        v.addStretch()
        return page

    # ------------------------------------------------------------------ #
    #  Flow
    # ------------------------------------------------------------------ #
    def _sync_rail(self) -> None:
        cur = self.stack.currentIndex()
        for i, lab in enumerate(self.step_labels):
            if i < cur:
                lab.setStyleSheet(f"color: {self.pal.green}; font-weight: 600;")
            elif i == cur:
                lab.setStyleSheet(f"color: {self.pal.accent}; font-weight: 700;")
            else:
                lab.setStyleSheet(f"color: {self.pal.muted};")

    def _sync_nav(self) -> None:
        i = self.stack.currentIndex()
        self.btn_back.setEnabled(i in (1, 2))
        self.btn_skip.setVisible(i < 3)
        if i == 2:
            self.btn_next.setEnabled(self.ck_confirm.isChecked())
            self.btn_next.setText("Install")
        elif i == 3:
            self.btn_next.setEnabled(False)
            self.btn_next.setText("Working…")
        elif i == 4:
            self.btn_next.setEnabled(True)
            self.btn_next.setText("Finish")
        else:
            self.btn_next.setEnabled(True)
            self.btn_next.setText("Continue")
        self._sync_rail()

    def _go(self, idx: int) -> None:
        self.stack.setCurrentIndex(idx)
        self._sync_nav()

    def _back(self) -> None:
        self._go(max(0, self.stack.currentIndex() - 1))

    def _skip(self) -> None:
        if QMessageBox.question(
                self, "Skip setup",
                "Skip the guided setup?\n\nYou can run it again later from the tray "
                "menu or the Settings page.") == QMessageBox.Yes:
            self.reject()

    def _next(self) -> None:
        i = self.stack.currentIndex()
        if i == 0:
            self._go(1)
        elif i == 1:
            blocked = [c for c in self.checks if c.status is Status.BLOCKED]
            if blocked:
                QMessageBox.warning(
                    self, "Cannot continue yet",
                    "These need your attention first:\n\n" +
                    "\n\n".join(f"• {c.title}\n  {c.detail}" for c in blocked))
                return
            self._go(2)
        elif i == 2:
            self._save_config()
            self._go(3)
            self._start_install()
        elif i == 4:
            self.finished_setup.emit()
            self.accept()

    # ------------------------------------------------------------------ #
    def _scan(self) -> None:
        lay = self.check_card.body
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.rows.clear()
        for c in self.checks:
            c.run_detect()
            row = CheckRow(c, self.pal)
            row.refresh()
            self.rows[c.id] = row
            self.check_card.add(row)

        missing = [c for c in self.checks if c.status is Status.MISSING]
        blocked = [c for c in self.checks if c.status is Status.BLOCKED]
        if blocked:
            self.check_summary.setText(
                f"{len(blocked)} item(s) need you to act before setup can continue. "
                "See the details above.")
            self.check_summary.setStyleSheet(f"color: {self.pal.red};")
        elif missing:
            admin = sum(1 for c in missing if c.needs_admin)
            extra = " One administrator prompt will appear." if admin else ""
            self.check_summary.setText(
                f"{len(missing)} item(s) will be installed for you.{extra}")
            self.check_summary.setStyleSheet(f"color: {self.pal.text};")
        else:
            self.check_summary.setText("Everything is already in place.")
            self.check_summary.setStyleSheet(f"color: {self.pal.green};")
        self._sync_nav()

    def _redetect(self) -> None:
        self.host = hostinfo.refresh()
        h = self.host
        self.sp_mem.setValue(h.suggested_memory_mb)
        self.sp_cpu.setValue(h.suggested_cpus)
        self.sp_w.setValue(h.display.width)
        self.sp_h.setValue(h.display.height)
        self.ed_tz.setText(h.timezone)
        self.ed_user.setText(h.username)
        self.ed_host.setText(h.hostname)
        QMessageBox.information(self, "Re-detected",
                                "\n".join(h.detected) or "Nothing changed.")

    def _read_vmconf(self) -> dict:
        vals: dict[str, str] = {}
        p = paths.SEED_DIR / "vm.conf"
        try:
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        vals[k.strip()] = v.strip()
        except OSError:
            pass
        return vals

    def _save_config(self) -> None:
        vals = self._read_vmconf()
        vals.update({
            "USERNAME": self.ed_user.text().strip() or "arch",
            "USERPASS": self.ed_pass.text() or "arch",
            "ROOTPASS": self.ed_pass.text() or "arch",
            "HOSTNAME": self.ed_host.text().strip() or "arch-hypr",
            "TIMEZONE": self.ed_tz.text().strip() or "Asia/Kolkata",
            "AUTO_CONFIRM": "yes" if self.ck_confirm.isChecked() else "no",
        })
        vals["LOCALE"] = self.host.locale
        vals["KEYMAP"] = self.host.console_keymap
        vals.setdefault("FORK_REPO", "https://github.com/pctrade/end4-pc.git")
        vals.setdefault("FORK_NAME", "end4-pC")
        body = "# written by ArchVM setup\n" + "".join(f"{k}={v}\n" for k, v in vals.items())
        try:
            paths.SEED_DIR.mkdir(parents=True, exist_ok=True)
            (paths.SEED_DIR / "vm.conf").write_bytes(body.encode("utf-8"))  # LF only
        except OSError:
            pass

        self.cfg.memory_mb = self.sp_mem.value()
        self.cfg.cpus = self.sp_cpu.value()
        self.cfg.width = self.sp_w.value()
        self.cfg.height = self.sp_h.value()
        self.cfg.keymap = self.host.qemu_keymap
        self.cfg.audio = self.host.has_audio
        self.cfg.username = self.ed_user.text().strip() or "arch"
        self.cfg.save()

        # vm.conf changed, so seed.iso must be rebuilt
        seed = next((c for c in self.checks if c.id == "seed"), None)
        if seed:
            seed.status = Status.MISSING
            seed.detail = "vm.conf changed — will rebuild"

    # ------------------------------------------------------------------ #
    def _start_install(self) -> None:
        lay = self.install_card.body
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.irows: dict[str, CheckRow] = {}
        work = [c for c in self.checks if c.status in (Status.MISSING, Status.WORKING)]
        if not work:
            work = [c for c in self.checks if c.status is Status.OK][:1]
        for c in work:
            r = CheckRow(c, self.pal)
            r.refresh()
            self.irows[c.id] = r
            self.install_card.add(r)

        self.worker = Worker(self.checks, self)
        self.worker.log.connect(self._ilog)
        self.worker.progress.connect(self._iprog)
        self.worker.step.connect(self._istep)
        self.worker.done.connect(self._idone)
        self.bar.setRange(0, 0)
        self._ilog("Starting setup…")
        self.worker.start()

    def _ilog(self, msg: str) -> None:
        self.install_log.appendPlainText(msg.rstrip())

    def _iprog(self, cur: int, total: int, note: str) -> None:
        if total:
            self.bar.setRange(0, 100)
            self.bar.setValue(int(cur / total * 100))
        self.bar_note.setText(note)

    def _istep(self, cid: str, status_value: str) -> None:
        row = getattr(self, "irows", {}).get(cid) or self.rows.get(cid)
        if row:
            row.refresh()

    def _idone(self, ok: bool, reboot: bool) -> None:
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.bar_note.setText("")
        self.reboot_required = reboot
        for c in self.checks:
            c.run_detect()
        for cid, row in getattr(self, "irows", {}).items():
            row.refresh()
        self._ilog("")
        self._ilog("Setup finished." if ok else
                   "Setup finished with problems — see the log above.")
        self._fill_done(ok)
        self._go(4)
        if ok and not reboot and self.ck_autostart_install.isChecked():
            QTimer.singleShot(400, self._offer_install)

    # ------------------------------------------------------------------ #
    def _fill_done(self, ok: bool) -> None:
        lay = self.done_todo.body
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        failed = [c for c in self.checks
                  if c.status in (Status.FAILED, Status.BLOCKED)]
        steps: list[str] = []

        if failed:
            self.done_sub.setText(
                "Setup completed, but some items did not finish. The virtual machine "
                "may still work — the details are below.")
            for c in failed:
                steps.append(f"{c.title} — {c.detail}")
        elif self.reboot_required:
            self.done_sub.setText(
                "Almost there. Windows needs to restart to finish enabling the "
                "hypervisor, and then your Arch system is ready to install.")
            steps.append("Restart Windows.")
            steps.append("Open ArchVM again and press Install Arch. Everything after "
                         "that is automatic.")
        else:
            self.done_sub.setText(
                "Your PC is ready. Here is the short version of what is left.")
            steps.append("Press Install Arch. The VM boots and the installer command "
                         "is typed in for you.")
            steps.append("Wait about 15 minutes for the base system, then let it "
                         "reboot.")
            steps.append("The desktop then installs itself on first login — 30 to 60 "
                         "minutes, mostly compiling. You can leave it running.")
            steps.append("After that it boots straight to a graphical login. Pick the "
                         "Hyprland session and sign in.")

        for i, s in enumerate(steps, 1):
            row = QHBoxLayout()
            n = QLabel(f"{i}")
            n.setFixedWidth(22)
            n.setAlignment(Qt.AlignCenter)
            n.setStyleSheet(f"color: {self.pal.accent}; font-weight: 700;")
            t = QLabel(s)
            t.setWordWrap(True)
            row.addWidget(n)
            row.addWidget(t, 1)
            self.done_todo.add(row)

        if self.reboot_required:
            rb = button("Restart Windows now", primary=True)
            rb.clicked.connect(self._reboot)
            self.done_todo.add(rb)

    def _reboot(self) -> None:
        if QMessageBox.question(
                self, "Restart Windows",
                "Restart now?\n\nSave any open work first.") != QMessageBox.Yes:
            return
        import subprocess
        subprocess.Popen(["shutdown", "/r", "/t", "5"],
                         creationflags=deps.NO_WINDOW)

    def _offer_install(self) -> None:
        if QMessageBox.question(
                self, "Start the Arch installation",
                "Start it now?\n\nThe VM will boot and the installer command is "
                "typed in for you. The base install takes about 15 minutes.\n\n"
                "You can also do this later from the Overview page."
        ) == QMessageBox.Yes:
            self.finished_setup.emit()
            self.accept()
            if self.parent() is not None:
                QTimer.singleShot(500, lambda: self.parent()._start_install_flow())
