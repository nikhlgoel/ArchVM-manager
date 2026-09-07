"""QEMU process control, HMP monitor, and disk helpers."""
from __future__ import annotations

import re
import socket
import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

from . import paths
from .config import VMConfig

# --------------------------------------------------------------------------- #
#  Host -> guest text injection.  QEMU has no clipboard channel, so we type.
# --------------------------------------------------------------------------- #
#: A QEMU that dies inside this many seconds of starting did not "shut down".
GL_CRASH_WINDOW_S = 180

#: Windows structured-exception codes that mean QEMU crashed rather than exited.
_CRASH_CODES = {
    0xC0000005,   # access violation - the virgl/DMABUF path
    0xC0000094,   # integer divide by zero
    0xC00000FD,   # stack overflow
    0xC000001D,   # illegal instruction
    0x40000015,   # fatal app exit
}


def _is_crash(code: int) -> bool:
    return (code & 0xFFFFFFFF) in _CRASH_CODES


KEYMAP: dict[str, str] = {
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


def unsupported_chars(text: str) -> list[str]:
    return sorted({c for c in text if char_to_key(c) is None})


class MonitorClient(QObject):
    """Speaks HMP over TCP.  All work happens off the UI thread."""

    progress = Signal(int, int)
    finished = Signal(bool, str)

    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self.port = port
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    # -------------------------------------------------------------- #
    def command(self, cmd: str, timeout: float = 4.0) -> tuple[bool, str]:
        """Run one HMP command synchronously.  Returns (ok, output)."""
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=timeout) as s:
                s.settimeout(2.0)
                try:
                    s.recv(8192)
                except socket.timeout:
                    pass
                s.sendall((cmd + "\n").encode())
                time.sleep(0.35)
                try:
                    return True, s.recv(65536).decode("utf-8", "replace")
                except socket.timeout:
                    return True, ""
        except OSError as e:
            return False, str(e)

    def type_text(self, text: str, delay_ms: int = 12) -> None:
        if self._busy:
            self.finished.emit(False, "Still sending the previous text.")
            return
        threading.Thread(target=self._type_worker,
                         args=(text, delay_ms), daemon=True).start()

    def _type_worker(self, text: str, delay_ms: int) -> None:
        self._busy = True
        try:
            keys, skipped = [], 0
            for ch in text:
                k = char_to_key(ch)
                if k:
                    keys.append(k)
                else:
                    skipped += 1
            if not keys:
                self.finished.emit(False, "Nothing typeable in that text.")
                return
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=5) as s:
                    s.settimeout(2.0)
                    try:
                        s.recv(8192)
                    except socket.timeout:
                        pass
                    total = len(keys)
                    for i, k in enumerate(keys):
                        s.sendall(f"sendkey {k}\n".encode())
                        time.sleep(max(0.004, delay_ms / 1000.0))
                        if i % 12 == 0:
                            self.progress.emit(i, total)
                    self.progress.emit(total, total)
                    time.sleep(0.2)
                msg = f"Typed {len(keys)} characters."
                if skipped:
                    msg += f" Skipped {skipped} unsupported character(s)."
                self.finished.emit(True, msg)
            except OSError as e:
                self.finished.emit(
                    False, f"Could not reach the QEMU monitor on port {self.port}. "
                           f"Is the VM running?  ({e})")
        finally:
            self._busy = False


# --------------------------------------------------------------------------- #
class VMRunner(QObject):
    """Owns the QEMU child process and surfaces its state."""

    state_changed = Signal(str)          # stopped | running
    output = Signal(str)
    failed = Signal(str)
    gl_crashed = Signal(float)           # seconds survived before the crash

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc: QProcess | None = None
        self.install_mode = False
        self._last_args: list[str] = []
        self._started_at: float | None = None
        self._gl_requested = False

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.NotRunning

    def last_command(self) -> str:
        if not self._last_args:
            return ""
        return str(paths.QEMU_BIN) + " " + " ".join(
            f'"{a}"' if " " in a else a for a in self._last_args)

    # -------------------------------------------------------------- #
    def start(self, cfg: VMConfig, install: bool) -> bool:
        if self.is_running():
            self.failed.emit("The VM is already running.")
            return False
        if not paths.QEMU_BIN.exists():
            self.failed.emit(f"QEMU not found at {paths.QEMU_BIN}")
            return False

        need = [cfg.disk] + ([cfg.iso, cfg.seed_iso] if install else [])
        missing = [p for p in need if not Path(p).exists()]
        if missing:
            self.failed.emit("Missing required file(s):\n" + "\n".join(missing))
            return False

        self.install_mode = install
        self._gl_requested = cfg.uses_gl()
        self._started_at = time.monotonic()
        self._last_args = cfg.build_args(install)

        self.proc = QProcess(self)
        self.proc.setProgram(str(paths.QEMU_BIN))
        self.proc.setArguments(self._last_args)
        self.proc.readyReadStandardError.connect(self._drain_err)
        self.proc.readyReadStandardOutput.connect(self._drain_out)
        self.proc.finished.connect(self._on_finished)
        self.proc.errorOccurred.connect(self._on_error)

        self.proc.start()
        if not self.proc.waitForStarted(10000):
            self.failed.emit(f"QEMU did not start: {self.proc.errorString()}")
            self.proc = None
            return False
        self.state_changed.emit("running")
        return True

    def stop(self) -> None:
        """Graceful ACPI shutdown request via the monitor is preferred."""
        if self.is_running():
            self.proc.kill()

    def shutdown_acpi(self, monitor: MonitorClient) -> bool:
        ok, _ = monitor.command("system_powerdown")
        return ok

    # -------------------------------------------------------------- #
    def _drain_err(self) -> None:
        if self.proc:
            self.output.emit(bytes(self.proc.readAllStandardError())
                             .decode("utf-8", "replace"))

    def _drain_out(self) -> None:
        if self.proc:
            self.output.emit(bytes(self.proc.readAllStandardOutput())
                             .decode("utf-8", "replace"))

    def _on_finished(self, code: int, _status) -> None:
        ran_for = time.monotonic() - (self._started_at or time.monotonic())
        self.output.emit(f"[vm] QEMU exited with code {code} after {ran_for:.0f}s")

        # 0xC0000005 is a Windows access violation. QEMU takes one inside the
        # GL path on builds whose GTK console has no DMABUF support: it warns
        # "GtkGLArea console lacks DMABUF support" and then dies a few seconds
        # in, as soon as the guest driver submits real work. Nothing in the
        # configuration is wrong and no pre-flight check catches it, because it
        # needs a guest actively driving the GPU to happen at all.
        if self._gl_requested and _is_crash(code) and ran_for < GL_CRASH_WINDOW_S:
            self.output.emit("[vm] that is the virgl crash signature "
                             "(0x%08X) - 3D acceleration is not usable here"
                             % (code & 0xFFFFFFFF))
            self.gl_crashed.emit(ran_for)

        self.state_changed.emit("stopped")

    def _on_error(self, err) -> None:
        if err == QProcess.FailedToStart:
            self.failed.emit("QEMU failed to start. Check the path and permissions.")


# --------------------------------------------------------------------------- #
def qemu_img(*args: str, timeout: int = 240) -> str:
    if not paths.QEMU_IMG.exists():
        return f"qemu-img not found at {paths.QEMU_IMG}"
    try:
        r = subprocess.run([str(paths.QEMU_IMG), *args],
                           capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return f"error: {e}"


def disk_summary(disk: str) -> tuple[str, str]:
    """Return (virtual size, allocated size) as display strings."""
    if not Path(disk).exists():
        return ("-", "disk not found")
    txt = qemu_img("info", disk)
    v = re.search(r"virtual size: ([^\n(]+)", txt)
    a = re.search(r"disk size: ([^\n(]+)", txt)
    return (v.group(1).strip() if v else "?", a.group(1).strip() if a else "?")


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.35):
            return True
    except OSError:
        return False
