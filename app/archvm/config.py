"""Persisted configuration: VM hardware, and application preferences."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, fields
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


# The display path that always works. virgl (virtio-vga-gl) is the fast path
# but it crashes QEMU outright on some Windows builds - the GTK GL area has no
# DMABUF support there, and the fallback blit dereferences a null texture - so
# the app has to be able to retreat to this.
SAFE_DISPLAY = "gtk"
SAFE_GPU = "virtio-vga"

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
    display: str = "gtk"
    gpu: str = "virtio-vga"
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

    def migrate(self) -> str:
        """
        Repair settings saved by older versions.

        Early builds defaulted to virtio-vga-gl with an OpenGL display, which
        does not work on Windows - GTK aborts and SDL renders nothing. Anyone
        upgrading still has that in their config, so correct it here rather
        than letting them hit a black screen again.
        """
        from .qemu import safe_display_for
        gpu, display, why = safe_display_for(self.gpu, self.display)
        if (gpu, display) == (self.gpu, self.display):
            return ""
        old = f"{self.gpu} + {self.display}"
        self.gpu, self.display = gpu, display
        self.save()
        return f"Display changed from {old} to {gpu} + {display}. {why}"

    def __post_init__(self) -> None:
        # QEMU's SDL backend services its window on the emulation thread here,
        # so the window stops answering Windows under any real load and is
        # declared "not responding" - measured hung for 77% of samples with GL
        # and 64% without. GTK does not do this. Migrate saved configs across;
        # unlike the GL crash there is no exit code to react to, because a
        # stalled window never exits.
        if self.display.startswith("sdl"):
            self.display = "gtk" + self.display[3:]

        # Fill path defaults lazily so they follow paths.ROOT
        self.disk = self.disk or str(paths.DISK_DIR / "arch-hyprland.qcow2")
        self.iso = self.iso or str(paths.ISO_DIR / "archlinux-x86_64.iso")
        self.seed_iso = self.seed_iso or str(paths.ISO_DIR / "seed.iso")
        self.ovmf_code = self.ovmf_code or str(paths.DISK_DIR / "OVMF_CODE.fd")
        self.ovmf_vars = self.ovmf_vars or str(paths.DISK_DIR / "OVMF_VARS.fd")

    @classmethod
    def load(cls, apply_host_defaults: bool = True) -> "VMConfig":
        data = _load_json(paths.VM_CONFIG_FILE)
        fresh = not data
        if fresh:
            # migrate from the old manager location before giving up
            data = _load_json(paths.LEGACY_VM_CONFIG)
            fresh = not data
        cfg = cls._from_dict(data)
        if fresh and apply_host_defaults:
            cfg.apply_host_defaults()
        cfg.migration_note = cfg.migrate()
        return cfg

    def apply_host_defaults(self) -> list[str]:
        """
        Seed the configuration from the user's Windows setup: display size,
        keyboard layout, and a memory/CPU split that leaves Windows usable.
        Returns the human-readable notes so the UI can show what it picked.
        """
        try:
            from . import hostinfo
            h = hostinfo.cached()
        except Exception:
            return []
        self.width = h.display.width
        self.height = h.display.height
        self.memory_mb = h.suggested_memory_mb
        self.cpus = h.suggested_cpus
        self.keymap = h.qemu_keymap
        self.username = h.username
        self.audio = h.has_audio
        return list(h.detected)

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

    def uses_gl(self) -> bool:
        """True when this configuration asks QEMU for host OpenGL."""
        return "gl=on" in self.display or "gl=es" in self.display or self.gpu.endswith("-gl")

    def fall_back_to_software(self) -> bool:
        """
        Drop to the display path that cannot crash. Returns True if anything
        changed, so the caller knows whether to tell the user.
        """
        if self.display == SAFE_DISPLAY and self.gpu == SAFE_GPU:
            return False
        self.display, self.gpu = SAFE_DISPLAY, SAFE_GPU
        return True

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

        # Disk I/O runs on its own thread. Without this every read and write is
        # serviced by QEMU's main loop - the same loop that pumps the window's
        # messages - so a burst of I/O (pacstrap, the first desktop build) stops
        # the window answering Windows and it is declared "not responding".
        a += [
            "-object", "iothread,id=io0",
            "-drive", f"id=hd0,if=none,file={self.disk},format=qcow2,"
                      f"cache=writeback,aio=threads,discard=unmap",
            "-device", f"virtio-blk-pci,drive=hd0,iothread=io0,"
                       f"bootindex={2 if install_mode else 1}",
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
            "-netdev", f"user,id=n0,hostfwd=tcp:127.0.0.1:{self.ssh_port}-:22",
            "-device", "virtio-net-pci,netdev=n0",
            # Bidirectional clipboard sharing between Windows host and guest
            "-device", "virtio-serial-pci",
            "-chardev", "qemu-vdagent,id=vdagent,name=vdagent,clipboard=on",
            "-device", "virtserialport,chardev=vdagent,name=com.redhat.spice.0",
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
    theme: str = "light"             # light | dark | auto
    accent: str = "#3b74e8"
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
    gl_unusable: bool = False        # set once QEMU has crashed in its GL path
    follow_windows_accent: bool = False

    @classmethod
    def load(cls) -> "AppSettings":
        return cls._from_dict(_load_json(paths.SETTINGS_FILE))

    def save(self) -> bool:
        return _save_json(paths.SETTINGS_FILE, self.to_dict())
