"""Filesystem locations, with fallbacks so the app works frozen or from source."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ArchVM"
APP_VERSION = "2.3.0"
ORG_NAME = "ArchVM"


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def resource_dir() -> Path:
    """Where bundled assets live (icons, etc)."""
    if is_frozen():
        # PyInstaller unpacks to _MEIPASS for onefile, or sys._MEIPASS == exe dir
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def _first_existing(*candidates: Path) -> Path | None:
    for c in candidates:
        try:
            if c and c.exists():
                return c
        except OSError:
            continue
    return None


def vm_root() -> Path:
    """
    The VM data directory (disks, ISOs, seed scripts).

    Resolution order so the app keeps working if things move:
      1. ARCHVM_ROOT environment variable
      2. a path recorded in the settings file
      3. user data folder in user home directory (archvm_data)
      4. beside the executable (if portable)
      5. repository root (source layout)
    """
    env = os.environ.get("ARCHVM_ROOT")
    if env:
        p = Path(env)
        if p.exists():
            return p

    from_settings = _settings_root_hint()
    if from_settings:
        return from_settings

    user_data = Path.home() / "archvm_data"
    if user_data.exists():
        return user_data

    here = Path(__file__).resolve()
    found = _first_existing(
        Path(sys.executable).parent if is_frozen() else None,
        here.parent.parent.parent,
    )
    return found or user_data


def _settings_root_hint() -> Path | None:
    try:
        import json
        f = config_dir() / "settings.json"
        if f.exists():
            v = json.loads(f.read_text(encoding="utf-8")).get("vm_root")
            if v and Path(v).exists():
                return Path(v)
    except Exception:
        pass
    return None


def config_dir() -> Path:
    """Per-user settings location. Falls back if APPDATA is unavailable."""
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
    d = Path(base) / APP_NAME if base else Path.home() / f".{APP_NAME.lower()}"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = Path.home()
    return d


def qemu_dir() -> Path:
    """Locate the QEMU installation."""
    env = os.environ.get("ARCHVM_QEMU")
    if env and Path(env).exists():
        return Path(env)
    found = _first_existing(
        Path(r"C:\Program Files\qemu"),
        Path(r"C:\Program Files (x86)\qemu"),
    )
    if found:
        return found
    # last resort: whatever is on PATH
    from shutil import which
    exe = which("qemu-system-x86_64")
    return Path(exe).parent if exe else Path(r"C:\Program Files\qemu")


# Convenience -------------------------------------------------------------- #
ROOT = vm_root()
CONFIG_DIR = config_dir()
QEMU_DIR = qemu_dir()

QEMU_BIN = QEMU_DIR / "qemu-system-x86_64.exe"
QEMU_IMG = QEMU_DIR / "qemu-img.exe"

SEED_DIR = ROOT / "seed"
ISO_DIR = ROOT / "iso"
DISK_DIR = ROOT / "disks"
LOG_DIR = ROOT / "logs"

SETTINGS_FILE = CONFIG_DIR / "settings.json"
VM_CONFIG_FILE = CONFIG_DIR / "vm.json"
LEGACY_VM_CONFIG = ROOT / "manager" / "config.json"


SEED_SCRIPTS = ("bootstrap.sh", "chroot-setup.sh", "firstboot.sh", "repair.sh")


def bundled_seed_dir() -> Path | None:
    """
    Where the installer scripts shipped with this build live.

    Frozen: PyInstaller unpacks them to <resource>/seed. From source: the repo
    keeps them one level above the package, at <repo>/seed.
    """
    return _first_existing(
        resource_dir() / "seed",
        resource_dir().parent / "seed",
        Path(__file__).resolve().parent.parent.parent / "seed",
    )


def deploy_seed_scripts() -> list[str]:
    """
    Copy the shipped installer scripts into the VM data folder, replacing any
    older copy.

    The scripts used to live only in the data directory, which meant a packaged
    build had none at all - the app could set everything up and then fail to
    install anything - and an app update never reached the scripts, so fixes to
    the install shipped but never ran. Content is compared rather than mtime,
    because copying does not preserve it.

    Returns the names actually written.
    """
    src = bundled_seed_dir()
    if src is None or not src.is_dir():
        return []
    written: list[str] = []
    try:
        SEED_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return []
    for name in SEED_SCRIPTS + ("vm.conf.example",):
        s = src / name
        if not s.is_file():
            continue
        d = SEED_DIR / name
        try:
            # LF matters: CRLF breaks these inside Linux.
            data = s.read_bytes().replace(b"\r\n", b"\n")
            if d.exists() and d.read_bytes() == data:
                continue
            d.write_bytes(data)
            written.append(name)
        except OSError:
            continue
    return written


def ensure_dirs() -> None:
    for d in (SEED_DIR, ISO_DIR, DISK_DIR, LOG_DIR, CONFIG_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def qemu_available() -> bool:
    return QEMU_BIN.exists()
