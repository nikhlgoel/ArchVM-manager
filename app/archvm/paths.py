"""Filesystem locations, with fallbacks so the app works frozen or from source."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ArchVM"
APP_VERSION = "2.1.1"
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
      3. D:\\ArchVM  (the original install)
      4. two levels up from this file (source layout: D:\\ArchVM\\app\\archvm)
      5. beside the executable
    """
    env = os.environ.get("ARCHVM_ROOT")
    if env:
        p = Path(env)
        if p.exists():
            return p

    from_settings = _settings_root_hint()
    if from_settings:
        return from_settings

    here = Path(__file__).resolve()
    found = _first_existing(
        Path(r"D:\ArchVM"),
        here.parent.parent.parent,                       # ...\ArchVM\app\archvm -> ArchVM
        Path(sys.executable).parent if is_frozen() else None,
    )
    return found or Path.home() / "ArchVM"


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


def ensure_dirs() -> None:
    for d in (SEED_DIR, ISO_DIR, DISK_DIR, LOG_DIR, CONFIG_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def qemu_available() -> bool:
    return QEMU_BIN.exists()
