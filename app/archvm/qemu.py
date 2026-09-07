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


# --------------------------------------------------------------------------- #
#  Display validation
# --------------------------------------------------------------------------- #
#  Pairings known to be broken on Windows. virgl needs DMABUF to present its
#  scanout, and no Windows display backend provides it: GTK aborts with
#  "GtkGLArea console lacks DMABUF support", SDL stays up but renders nothing.
BROKEN_PAIRINGS = {
    ("virtio-vga-gl", "gtk"),
    ("virtio-vga-gl", "sdl"),
    ("virtio-gpu-gl", "gtk"),
    ("virtio-gpu-gl", "sdl"),
}

SAFE_GPU = "virtio-vga"
SAFE_DISPLAY = "gtk"


def display_is_supported(gpu: str, display: str) -> tuple[bool, str]:
    """
    Static check of a GPU/display pairing, without launching anything.

    Returns (ok, reason). Only the GL pairings are rejected; everything else is
    assumed fine until probe_display() says otherwise.
    """
    backend = display.split(",")[0].strip()
    gl_on = "gl=on" in display or "gl=es" in display
    gpu_is_gl = gpu.endswith("-gl")

    if gpu_is_gl and (gpu, backend) in BROKEN_PAIRINGS:
        return False, (
            f"{gpu} needs DMABUF to present its display, which the {backend} "
            "backend does not provide on Windows. The window would stay black "
            "or QEMU would exit.")
    if gpu_is_gl and not gl_on:
        return False, (
            f"{gpu} requires a display with gl=on; {backend} was requested "
            "without it, and QEMU refuses to start.")
    if gl_on and not gpu_is_gl:
        return False, (
            f"{display} enables OpenGL but {gpu} cannot use it.")
    return True, ""


def safe_display_for(gpu: str, display: str) -> tuple[str, str, str]:
    """
    Return a pairing that will actually work, plus a note when it was changed.
    """
    ok, why = display_is_supported(gpu, display)
    if ok:
        return gpu, display, ""
    backend = display.split(",")[0].strip()
    if backend not in ("gtk", "sdl"):
        backend = SAFE_DISPLAY
    return SAFE_GPU, backend, why


def probe_display(gpu: str, display: str, timeout: float = 6.0) -> tuple[bool, str]:
    """
    Launch QEMU with the pairing and no guest, and see whether it survives.

    Cheap insurance: a pairing that aborts here would otherwise abort with the
    user's VM attached, which looks like the VM failing rather than the display.
    """
    if not paths.QEMU_BIN.exists():
        return False, "QEMU not found"
    args = [
        str(paths.QEMU_BIN),
        "-machine", "q35,accel=whpx,kernel-irqchip=off",
        "-m", "256", "-nodefaults",
        "-device", gpu,
        "-display", display,
    ]
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            _out, err = proc.communicate(timeout=timeout)
            text = (err or b"").decode("utf-8", "replace").strip()
            first = text.splitlines()[0] if text else f"exited with {proc.returncode}"
            return False, first
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return True, ""
    except Exception as e:
        return False, str(e)


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

        # Check port availability to avoid hard QEMU socket binding crashes
        if is_port_in_use(cfg.monitor_port):
            free_m = find_available_port(cfg.monitor_port + 1)
            self.output.emit(f"[vm] Port {cfg.monitor_port} is busy; allocated monitor port {free_m}")
            cfg.monitor_port = free_m

        if is_port_in_use(cfg.ssh_port):
            free_s = find_available_port(cfg.ssh_port + 1)
            self.output.emit(f"[vm] Port {cfg.ssh_port} is busy; allocated SSH port {free_s}")
            cfg.ssh_port = free_s

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
        elif code != 0 and ran_for < 10:
            self.output.emit(
                f"[vm] QEMU terminated prematurely with exit code {code} "
                f"(0x{code & 0xFFFFFFFF:08X}). Check logs above or host hypervisor/WHPX state."
            )

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


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if (host, port) is already bound or being listened on."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def find_available_port(preferred: int, host: str = "127.0.0.1", max_search: int = 50) -> int:
    """Find the next available port starting from preferred."""
    for p in range(preferred, preferred + max_search):
        if not is_port_in_use(p, host):
            return p
    return preferred
