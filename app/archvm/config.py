"""Persisted configuration: VM hardware, and application preferences."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field, fields
from pathlib import Path
from typing import Any

from . import paths

INSTALL_CMD = "mkdir -p /s && mount /dev/sr1 /s && bash /s/bootstrap.sh"


def _load_json(p: Path) -> dict[str, Any]:
    try:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_json(p: Path, data: dict) -> bool:
    """Atomic-ish write so a crash mid-save cannot corrupt the file."""
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception:
        return False


class _Base:
    """Shared load/save that ignores unknown keys instead of crashing."""

    @classmethod
    def _from_dict(cls, data: dict):
        known = {f.name for f in fields(cls)}
        clean = {}
        for k, v in data.items():
            if k not in known:
                continue
            # tolerate type drift from hand-edited files
            expected = next(f.type for f in fields(cls) if f.name == k)
            try:
                if expected is int and not isinstance(v, bool):
                    v = int(v)
                elif expected is bool:
                    v = bool(v)
                elif expected is str:
                    v = str(v)
            except (TypeError, ValueError):
                continue
            clean[k] = v
        return cls(**clean)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
@dataclass
class VMConfig(_Base):
    name: str = "Arch Hyprland"
    memory_mb: int = 8192
    cpus: int = 8
    disk: str = ""
    iso: str = ""
    seed_iso: str = ""
    ovmf_code: str = ""
    ovmf_vars: str = ""
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
    keyboard: str = "ps2"
    keymap: str = "en-us"
    username: str = "arch"

    def __post_init__(self) -> None:
        # Fill path defaults lazily so they follow paths.ROOT
        self.disk = self.disk or str(paths.DISK_DIR / "arch-hyprland.qcow2")
        self.iso = self.iso or str(paths.ISO_DIR / "archlinux-x86_64.iso")
        self.seed_iso = self.seed_iso or str(paths.ISO_DIR / "seed.iso")
        self.ovmf_code = self.ovmf_code or str(paths.DISK_DIR / "OVMF_CODE.fd")
        self.ovmf_vars = self.ovmf_vars or str(paths.DISK_DIR / "OVMF_VARS.fd")

    @classmethod
    def load(cls) -> "VMConfig":
        data = _load_json(paths.VM_CONFIG_FILE)
        if not data:
            # migrate from the old manager location
            data = _load_json(paths.LEGACY_VM_CONFIG)
        return cls._from_dict(data)

    def save(self) -> bool:
        return _save_json(paths.VM_CONFIG_FILE, self.to_dict())

    # -------------------------------------------------------------- #
    def validate(self) -> list[str]:
        """Return a list of human-readable problems, empty when fine."""
        problems: list[str] = []
        if not paths.QEMU_BIN.exists():
            problems.append(f"QEMU not found at {paths.QEMU_BIN}")
        if not Path(self.disk).exists():
            problems.append(f"Virtual disk missing: {self.disk}")
        if self.memory_mb < 2048:
            problems.append("Memory below 2048 MB will not boot the installer.")
        return problems

    def build_args(self, install_mode: bool) -> list[str]:
        a: list[str] = [
            "-name", self.name,
            "-machine", f"q35,accel={self.accel},kernel-irqchip=off",
            "-cpu", self.cpu_model,
            "-smp", str(max(1, self.cpus)),
            "-m", str(max(1024, self.memory_mb)),
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

        # Absolute pointer, no mouse grab.  The keyboard is deliberately NOT
        # virtio: virtio-keyboard mistranslates shifted symbols (Shift+0) and
        # can leave modifiers stuck on the Windows host after the VM exits.
        a += ["-device", "qemu-xhci,id=xhci", "-device", "usb-tablet,bus=xhci.0"]
        if self.keyboard == "usb":
            a += ["-device", "usb-kbd,bus=xhci.0"]

        if self.audio:
            a += ["-audiodev", "dsound,id=snd0",
                  "-device", "ich9-intel-hda",
                  "-device", "hda-duplex,audiodev=snd0"]

        a += ["-monitor", f"tcp:127.0.0.1:{self.monitor_port},server=on,wait=off"]
        return a


# --------------------------------------------------------------------------- #
@dataclass
class AppSettings(_Base):
    theme: str = "auto"              # auto | dark | light
    accent: str = "#4f8cff"
    translucency: bool = True
    gradient: bool = True
    minimise_to_tray: bool = True
    close_to_tray: bool = True
    start_minimised: bool = False
    autostart: bool = False
    notifications: bool = True
    confirm_force_stop: bool = True
    reduce_motion: bool = False
    font_scale: int = 100            # percent, for accessibility
    vm_root: str = ""
    window_w: int = 1180
    window_h: int = 800
    setup_done: bool = False

    @classmethod
    def load(cls) -> "AppSettings":
        return cls._from_dict(_load_json(paths.SETTINGS_FILE))

    def save(self) -> bool:
        return _save_json(paths.SETTINGS_FILE, self.to_dict())
