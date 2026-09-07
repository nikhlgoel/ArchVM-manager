"""
Environment detection and repair.

Every requirement is a `Check`. A check knows how to detect itself and, where
possible, how to fix itself. Fixes that need administrator rights are collected
and run together in a single elevated PowerShell script, so the user sees one
UAC prompt rather than several.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from . import paths

ISO_URL = "https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso"
SUMS_URL = "https://geo.mirror.pkgbuild.com/iso/latest/sha256sums.txt"

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

MIN_DISK_GB = 60
REC_DISK_GB = 140
MIN_RAM_GB = 8


class Status(Enum):
    UNKNOWN = "unknown"
    OK = "ok"
    MISSING = "missing"      # fixable
    WARN = "warn"            # usable, not ideal
    BLOCKED = "blocked"      # needs the user to act outside the app
    WORKING = "working"
    FAILED = "failed"


@dataclass
class Check:
    id: str
    title: str
    why: str
    detect: Callable[[], tuple[Status, str]]
    fix: Callable[["Reporter"], bool] | None = None
    needs_admin: bool = False
    admin_script: str = ""            # PowerShell, run in the elevated batch
    status: Status = Status.UNKNOWN
    detail: str = ""
    requires_reboot: bool = False

    @property
    def fixable(self) -> bool:
        return self.fix is not None or bool(self.admin_script)

    def run_detect(self) -> None:
        try:
            self.status, self.detail = self.detect()
        except Exception as e:
            self.status, self.detail = Status.FAILED, f"check failed: {e}"


class Reporter:
    """Progress sink passed into fixes. Set by the wizard."""

    def __init__(self, log=None, progress=None):
        self._log = log or (lambda s: None)
        self._progress = progress or (lambda cur, total, note="": None)
        self.cancelled = False

    def log(self, msg: str) -> None:
        self._log(msg)

    def progress(self, cur: int, total: int, note: str = "") -> None:
        self._progress(cur, total, note)


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, creationflags=NO_WINDOW)
        return r.returncode, (r.stdout + r.stderr)
    except Exception as e:
        return 1, str(e)


def _ps(script: str, timeout: int = 300) -> tuple[int, str]:
    return _run(["powershell", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command", script], timeout)


def free_gb(path: Path) -> float:
    try:
        drive = str(Path(path).anchor or "C:\\")
        total, used, free = shutil.disk_usage(drive)
        return free / (1024 ** 3)
    except Exception:
        return 0.0


def total_ram_gb() -> float:
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MEMORYSTATUSEX()
        m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullTotalPhys / (1024 ** 3)
    except Exception:
        return 0.0


def cpu_count() -> int:
    return os.cpu_count() or 4


# --------------------------------------------------------------------------- #
#  Elevation
# --------------------------------------------------------------------------- #
def run_elevated(script: str, reporter: Reporter) -> bool:
    """
    Run a PowerShell script as administrator. Triggers the normal Windows UAC
    prompt. Returns True when the script reports success.
    """
    marker = paths.CONFIG_DIR / "elevated-result.txt"
    try:
        if marker.exists():
            marker.unlink()
    except OSError:
        pass

    full = (
        "$ErrorActionPreference='Continue'\n"
        "$ok=$true\n"
        f"{script}\n"
        f"if ($ok) {{ 'OK' }} else {{ 'FAIL' }} | "
        f"Out-File -FilePath '{marker}' -Encoding ascii\n"
    )
    sf = paths.CONFIG_DIR / "elevated-task.ps1"
    try:
        sf.write_text(full, encoding="utf-8")
    except OSError as e:
        reporter.log(f"Could not write the elevation script: {e}")
        return False

    reporter.log("Requesting administrator permission…")
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe",
            f'-NoProfile -ExecutionPolicy Bypass -File "{sf}"',
            None, 1)
        if rc <= 32:
            reporter.log("Administrator permission was declined.")
            return False
    except Exception as e:
        reporter.log(f"Elevation failed: {e}")
        return False

    # Wait for the elevated process to drop its result file.
    import time
    for _ in range(600):                       # up to ~5 minutes
        if marker.exists():
            try:
                res = marker.read_text(encoding="ascii", errors="replace").strip()
            except OSError:
                res = ""
            ok = res.startswith("OK")
            reporter.log("Administrator task finished." if ok
                         else "Administrator task reported a failure.")
            return ok
        time.sleep(0.5)
    reporter.log("Timed out waiting for the administrator task.")
    return False


# --------------------------------------------------------------------------- #
#  Individual detections
# --------------------------------------------------------------------------- #
def _d_cpu_virt() -> tuple[Status, str]:
    code, out = _ps(
        "$c=Get-CimInstance Win32_ComputerSystem;"
        "$p=Get-CimInstance Win32_Processor | Select-Object -First 1;"
        "\"$($c.HypervisorPresent)|$($p.VirtualizationFirmwareEnabled)|$($p.Name)\"")
    txt = out.strip().splitlines()[-1] if out.strip() else ""
    parts = txt.split("|")
    hv = parts[0].strip().lower() == "true" if parts else False
    fw = parts[1].strip().lower() == "true" if len(parts) > 1 else False
    name = parts[2].strip() if len(parts) > 2 else "CPU"
    if hv or fw:
        return Status.OK, f"{name} — virtualization enabled"
    return Status.BLOCKED, (
        "Virtualization is disabled in firmware. Reboot into BIOS/UEFI and "
        "enable Intel VT-x (or AMD-V), then run this setup again.")


def _d_hyperv_platform() -> tuple[Status, str]:
    code, out = _ps(
        "try { (Get-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform"
        " -ErrorAction Stop).State } catch { 'Unknown' }")
    state = out.strip().splitlines()[-1].strip() if out.strip() else "Unknown"
    if state.lower().startswith("enabled"):
        return Status.OK, "Windows Hypervisor Platform enabled"
    if state.lower() == "unknown":
        # Not queryable without admin; infer from whether WHPX actually works.
        if paths.QEMU_BIN.exists():
            code2, out2 = _run([str(paths.QEMU_BIN), "-accel", "help"], timeout=30)
            if "whpx" in out2.lower():
                return Status.OK, "WHPX accelerator available"
        return Status.WARN, "Could not query (needs admin); will verify at first boot"
    return Status.MISSING, "Windows Hypervisor Platform is disabled — QEMU would be very slow"


def _d_qemu() -> tuple[Status, str]:
    if paths.QEMU_BIN.exists():
        code, out = _run([str(paths.QEMU_BIN), "--version"], timeout=30)
        ver = out.strip().splitlines()[0] if out.strip() else "installed"
        return Status.OK, ver
    return Status.MISSING, "QEMU is not installed"


def _d_virgl() -> tuple[Status, str]:
    if not paths.QEMU_BIN.exists():
        return Status.UNKNOWN, "needs QEMU"
    code, out = _run([str(paths.QEMU_BIN), "-device", "help"], timeout=40)
    if "virtio-vga-gl" in out:
        return Status.OK, "virtio-vga-gl present — 3D acceleration available"
    return Status.WARN, "No virgl in this QEMU build; Hyprland would software-render"


def _d_disk() -> tuple[Status, str]:
    gb = free_gb(paths.ROOT)
    if gb >= REC_DISK_GB:
        return Status.OK, f"{gb:.0f} GB free on {Path(paths.ROOT).anchor}"
    if gb >= MIN_DISK_GB:
        return Status.WARN, f"{gb:.0f} GB free — enough to start, {REC_DISK_GB} GB recommended"
    return Status.BLOCKED, f"Only {gb:.0f} GB free; at least {MIN_DISK_GB} GB is needed"


def _d_ram() -> tuple[Status, str]:
    gb = total_ram_gb()
    if gb >= MIN_RAM_GB:
        return Status.OK, f"{gb:.1f} GB RAM, {cpu_count()} logical CPUs"
    return Status.WARN, f"{gb:.1f} GB RAM — the VM will be tight"


def _d_firmware() -> tuple[Status, str]:
    code = Path(paths.DISK_DIR / "OVMF_CODE.fd")
    vars_ = Path(paths.DISK_DIR / "OVMF_VARS.fd")
    if code.exists() and vars_.exists():
        return Status.OK, "UEFI firmware ready"
    src = paths.QEMU_DIR / "share" / "edk2-x86_64-code.fd"
    if not src.exists():
        return Status.WARN, "UEFI firmware not found in the QEMU install"
    return Status.MISSING, "UEFI firmware not yet copied"


def _d_iso() -> tuple[Status, str]:
    p = Path(paths.ISO_DIR / "archlinux-x86_64.iso")
    if p.exists():
        gb = p.stat().st_size / (1024 ** 3)
        if gb > 0.5:
            return Status.OK, f"Arch ISO present ({gb:.2f} GB)"
        return Status.MISSING, "Arch ISO looks truncated"
    return Status.MISSING, "Arch Linux ISO not downloaded (~1.5 GB)"


def _d_seed() -> tuple[Status, str]:
    p = Path(paths.ISO_DIR / "seed.iso")
    scripts = [paths.SEED_DIR / n for n in
               ("bootstrap.sh", "chroot-setup.sh", "firstboot.sh", "vm.conf")]
    if not all(s.exists() for s in scripts):
        return Status.BLOCKED, "Installer scripts are missing from the seed folder"
    if p.exists():
        if p.stat().st_mtime >= max(s.stat().st_mtime for s in scripts):
            return Status.OK, "seed.iso is up to date"
        return Status.MISSING, "seed.iso is older than the scripts"
    return Status.MISSING, "seed.iso not built yet"


def _d_disk_image() -> tuple[Status, str]:
    p = Path(paths.DISK_DIR / "arch-hyprland.qcow2")
    if p.exists():
        code, out = _run([str(paths.QEMU_IMG), "info", str(p)], timeout=60) \
            if paths.QEMU_IMG.exists() else (1, "")
        import re
        m = re.search(r"disk size: ([^\n(]+)", out)
        used = m.group(1).strip() if m else "?"
        return Status.OK, f"120 GB virtual disk ({used} used)"
    return Status.MISSING, "Virtual disk not created"


def _d_ssh() -> tuple[Status, str]:
    if shutil.which("ssh"):
        return Status.OK, "OpenSSH client available"
    return Status.MISSING, "OpenSSH client not installed (used for guest access)"


# --------------------------------------------------------------------------- #
#  Fixes
# --------------------------------------------------------------------------- #
def _f_firmware(rep: Reporter) -> bool:
    try:
        paths.DISK_DIR.mkdir(parents=True, exist_ok=True)
        src_code = paths.QEMU_DIR / "share" / "edk2-x86_64-code.fd"
        src_vars = paths.QEMU_DIR / "share" / "edk2-i386-vars.fd"
        if not src_code.exists():
            rep.log("UEFI firmware not present in the QEMU installation.")
            return False
        shutil.copyfile(src_code, paths.DISK_DIR / "OVMF_CODE.fd")
        if src_vars.exists():
            shutil.copyfile(src_vars, paths.DISK_DIR / "OVMF_VARS.fd")
        rep.log("Copied UEFI firmware.")
        return True
    except Exception as e:
        rep.log(f"Firmware copy failed: {e}")
        return False


def _expected_sha256(rep: Reporter) -> str | None:
    try:
        with urllib.request.urlopen(SUMS_URL, timeout=30) as r:
            for line in r.read().decode("utf-8", "replace").splitlines():
                if "archlinux-x86_64.iso" in line:
                    return line.split()[0].strip().lower()
    except Exception as e:
        rep.log(f"Could not fetch the checksum list: {e}")
    return None


def _f_iso(rep: Reporter) -> bool:
    paths.ISO_DIR.mkdir(parents=True, exist_ok=True)
    dest = paths.ISO_DIR / "archlinux-x86_64.iso"
    tmp = dest.with_suffix(".part")
    rep.log("Downloading the Arch Linux ISO (about 1.5 GB)…")
    try:
        req = urllib.request.Request(ISO_URL, headers={"User-Agent": "ArchVM"})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            h = hashlib.sha256()
            while True:
                if rep.cancelled:
                    rep.log("Download cancelled.")
                    return False
                chunk = r.read(1024 * 512)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if total:
                    rep.progress(done, total,
                                 f"{done / 1048576:.0f} / {total / 1048576:.0f} MB")
        digest = h.hexdigest()
    except Exception as e:
        rep.log(f"Download failed: {e}")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False

    expected = _expected_sha256(rep)
    if expected and digest != expected:
        rep.log("Checksum MISMATCH — the download is corrupt and was discarded.")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    rep.log("Checksum verified against the official mirror." if expected
            else "Downloaded (checksum list unavailable, skipped verification).")
    try:
        tmp.replace(dest)
    except OSError as e:
        rep.log(f"Could not finalise the download: {e}")
        return False
    return True


def _f_seed(rep: Reporter) -> bool:
    builder = paths.ROOT / "manager" / "build_seed.py"
    if not builder.exists():
        rep.log(f"Seed builder missing: {builder}")
        return False
    exe = sys.executable
    if paths.is_frozen():
        exe = shutil.which("python") or shutil.which("py") or ""
        if not exe:
            rep.log("Python is needed to rebuild seed.iso but was not found.")
            return False
    code, out = _run([exe, str(builder)], timeout=180)
    rep.log(out.strip() or "seed.iso rebuilt.")
    return code == 0


def _f_disk_image(rep: Reporter) -> bool:
    if not paths.QEMU_IMG.exists():
        rep.log("qemu-img not found.")
        return False
    paths.DISK_DIR.mkdir(parents=True, exist_ok=True)
    dest = paths.DISK_DIR / "arch-hyprland.qcow2"
    rep.log("Creating the 120 GB virtual disk (sparse — grows as used)…")
    code, out = _run([str(paths.QEMU_IMG), "create", "-f", "qcow2",
                      str(dest), "120G"], timeout=300)
    rep.log(out.strip())
    return code == 0 and dest.exists()


# --------------------------------------------------------------------------- #
def build_checks() -> list[Check]:
    return [
        Check("cpu", "CPU virtualization",
              "QEMU needs VT-x/AMD-V to run at native speed.",
              _d_cpu_virt),
        Check("whpx", "Windows Hypervisor Platform",
              "Provides the WHPX accelerator QEMU uses on Windows.",
              _d_hyperv_platform,
              needs_admin=True, requires_reboot=True,
              admin_script=(
                  "Write-Output 'Enabling Windows Hypervisor Platform...'\n"
                  "$r = dism.exe /online /enable-feature "
                  "/featurename:HypervisorPlatform /all /norestart\n"
                  "if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 3010) { $ok=$false }\n")),
        Check("qemu", "QEMU",
              "The hypervisor that runs the virtual machine.",
              _d_qemu,
              needs_admin=True,
              admin_script=(
                  "Write-Output 'Installing QEMU via winget...'\n"
                  "winget install --id SoftwareFreedomConservancy.QEMU -e "
                  "--accept-source-agreements --accept-package-agreements "
                  "--disable-interactivity\n"
                  "if ($LASTEXITCODE -ne 0) { $ok=$false }\n")),
        Check("virgl", "3D acceleration (virgl)",
              "Lets Hyprland composite on the GPU instead of the CPU.",
              _d_virgl),
        Check("ssh", "OpenSSH client",
              "Used to open a terminal into the guest with working copy/paste.",
              _d_ssh,
              needs_admin=True,
              admin_script=(
                  "Write-Output 'Adding the OpenSSH client...'\n"
                  "dism.exe /online /Add-Capability "
                  "/CapabilityName:OpenSSH.Client~~~~0.0.1.0\n")),
        Check("ram", "Memory and CPU",
              "The VM needs a reasonable share of both.",
              _d_ram),
        Check("disk", "Disk space",
              "The virtual disk grows to whatever the guest actually uses.",
              _d_disk),
        Check("firmware", "UEFI firmware",
              "Boots the guest in UEFI mode with systemd-boot.",
              _d_firmware, fix=_f_firmware),
        Check("iso", "Arch Linux ISO",
              "The installer image, verified against the official checksum.",
              _d_iso, fix=_f_iso),
        Check("seed", "Installer scripts (seed.iso)",
              "Carries the automated install into the VM.",
              _d_seed, fix=_f_seed),
        Check("vmdisk", "Virtual disk",
              "Where Arch Linux will be installed.",
              _d_disk_image, fix=_f_disk_image),
    ]


def setup_complete(checks: list[Check]) -> bool:
    """True when nothing essential is missing."""
    blocking = {Status.MISSING, Status.BLOCKED, Status.FAILED}
    return not any(c.status in blocking for c in checks)
