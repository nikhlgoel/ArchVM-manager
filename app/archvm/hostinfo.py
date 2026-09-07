"""
Read sensible defaults out of the user's Windows installation.

Everything here is a *suggestion*: the wizard shows what was detected and lets
the user override it. Every probe degrades to a documented fallback rather than
raising, because a wrong default is recoverable but a crash on first launch is
not.
"""
from __future__ import annotations

import ctypes
import locale
import os
import subprocess
from dataclasses import dataclass, field, asdict

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _ps(script: str, timeout: int = 20) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=NO_WINDOW)
        return (r.stdout or "").strip()
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
#  Windows time zone id -> IANA. Covers the common zones; anything unknown
#  falls back to UTC, which is correct-but-boring rather than wrong-and-silent.
# --------------------------------------------------------------------------- #
TZ_MAP = {
    "India Standard Time": "Asia/Kolkata",
    "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Africa/Abidjan",
    "W. Europe Standard Time": "Europe/Berlin",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "Romance Standard Time": "Europe/Paris",
    "E. Europe Standard Time": "Europe/Chisinau",
    "FLE Standard Time": "Europe/Kyiv",
    "Turkey Standard Time": "Europe/Istanbul",
    "Russian Standard Time": "Europe/Moscow",
    "Arabic Standard Time": "Asia/Baghdad",
    "Arab Standard Time": "Asia/Riyadh",
    "Arabian Standard Time": "Asia/Dubai",
    "Iran Standard Time": "Asia/Tehran",
    "Pakistan Standard Time": "Asia/Karachi",
    "Sri Lanka Standard Time": "Asia/Colombo",
    "Bangladesh Standard Time": "Asia/Dhaka",
    "Nepal Standard Time": "Asia/Kathmandu",
    "Myanmar Standard Time": "Asia/Yangon",
    "SE Asia Standard Time": "Asia/Bangkok",
    "Singapore Standard Time": "Asia/Singapore",
    "China Standard Time": "Asia/Shanghai",
    "Taipei Standard Time": "Asia/Taipei",
    "Tokyo Standard Time": "Asia/Tokyo",
    "Korea Standard Time": "Asia/Seoul",
    "W. Australia Standard Time": "Australia/Perth",
    "AUS Central Standard Time": "Australia/Darwin",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "E. Australia Standard Time": "Australia/Brisbane",
    "Tasmania Standard Time": "Australia/Hobart",
    "New Zealand Standard Time": "Pacific/Auckland",
    "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "US Mountain Standard Time": "America/Phoenix",
    "Pacific Standard Time": "America/Los_Angeles",
    "Alaskan Standard Time": "America/Anchorage",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Atlantic Standard Time": "America/Halifax",
    "Newfoundland Standard Time": "America/St_Johns",
    "SA Pacific Standard Time": "America/Bogota",
    "SA Eastern Standard Time": "America/Cayenne",
    "E. South America Standard Time": "America/Sao_Paulo",
    "Argentina Standard Time": "America/Argentina/Buenos_Aires",
    "Pacific SA Standard Time": "America/Santiago",
    "Central Brazilian Standard Time": "America/Cuiaba",
    "Venezuela Standard Time": "America/Caracas",
    "South Africa Standard Time": "Africa/Johannesburg",
    "Egypt Standard Time": "Africa/Cairo",
    "Morocco Standard Time": "Africa/Casablanca",
    "W. Central Africa Standard Time": "Africa/Lagos",
    "E. Africa Standard Time": "Africa/Nairobi",
    "Israel Standard Time": "Asia/Jerusalem",
    "Georgian Standard Time": "Asia/Tbilisi",
    "Azerbaijan Standard Time": "Asia/Baku",
    "West Asia Standard Time": "Asia/Tashkent",
    "Central Asia Standard Time": "Asia/Almaty",
    "N. Central Asia Standard Time": "Asia/Novosibirsk",
    "North Asia Standard Time": "Asia/Krasnoyarsk",
    "UTC": "UTC",
}

# Windows keyboard layout id (KLID) -> (QEMU -k name, Linux console keymap,
# X11/Wayland XkbLayout)
KLID_MAP = {
    "00000409": ("en-us", "us", "us"),
    "00000809": ("en-gb", "uk", "gb"),
    "00010409": ("en-us", "dvorak", "us"),
    "00000407": ("de", "de-latin1", "de"),
    "0000040c": ("fr", "fr-latin1", "fr"),
    "0000080c": ("fr-be", "be-latin1", "be"),
    "00000410": ("it", "it", "it"),
    "0000040a": ("es", "es", "es"),
    "00000416": ("pt-br", "br-abnt2", "br"),
    "00000816": ("pt", "pt-latin1", "pt"),
    "00000413": ("nl", "nl", "nl"),
    "0000041d": ("sv", "sv-latin1", "se"),
    "00000414": ("no", "no", "no"),
    "00000406": ("da", "dk", "dk"),
    "0000040b": ("fi", "fi", "fi"),
    "00000415": ("pl", "pl", "pl"),
    "00000405": ("cz", "cz", "cz"),
    "0000040e": ("hu", "hu", "hu"),
    "00000419": ("ru", "ru", "ru"),
    "0000041f": ("tr", "trq", "tr"),
    "00000408": ("", "gr", "gr"),
    "00000411": ("ja", "jp106", "jp"),
    "00000412": ("", "us", "kr"),
    "00000804": ("", "us", "cn"),
    "0000041a": ("hr", "croat", "hr"),
    "00000424": ("sl", "slovene", "si"),
    "0000100c": ("fr-ch", "fr_CH", "ch"),
    "00000807": ("de-ch", "de_CH-latin1", "ch"),
    "00001009": ("fr-ca", "cf", "ca"),
}


# --------------------------------------------------------------------------- #
@dataclass
class Display:
    width: int = 1920
    height: int = 1080
    refresh_hz: int = 60
    scale_percent: int = 100
    monitors: int = 1
    primary_name: str = ""

    @property
    def logical_size(self) -> tuple[int, int]:
        """Size in Windows' scaled coordinates - what the user 'sees'."""
        f = max(100, self.scale_percent) / 100.0
        return (int(self.width / f), int(self.height / f))


@dataclass
class HostInfo:
    display: Display = field(default_factory=Display)
    timezone: str = "UTC"
    timezone_windows: str = ""
    locale: str = "en_US.UTF-8"
    qemu_keymap: str = "en-us"
    console_keymap: str = "us"
    xkb_layout: str = "us"
    username: str = "arch"
    hostname: str = "arch-hypr"
    ram_gb: float = 8.0
    logical_cpus: int = 4
    suggested_memory_mb: int = 8192
    suggested_cpus: int = 4
    has_audio: bool = True
    windows_edition: str = ""
    gpu: str = ""
    detected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["display"] = asdict(self.display)
        return d


# --------------------------------------------------------------------------- #
def _detect_display() -> Display:
    d = Display()
    # Physical pixels + refresh via WMI; DPI via the Win32 API.
    out = _ps(
        "$s = Get-CimInstance Win32_VideoController | "
        "Where-Object { $_.CurrentHorizontalResolution -gt 0 } | Select-Object -First 1;"
        "$m = @(Get-CimInstance Win32_DesktopMonitor).Count;"
        "\"$($s.CurrentHorizontalResolution)|$($s.CurrentVerticalResolution)|"
        "$($s.CurrentRefreshRate)|$m|$($s.Name)\"")
    parts = [p.strip() for p in out.splitlines()[-1].split("|")] if out else []
    try:
        if len(parts) >= 3 and parts[0].isdigit():
            d.width = int(parts[0])
            d.height = int(parts[1])
            if parts[2].isdigit():
                d.refresh_hz = int(parts[2])
        if len(parts) >= 4 and parts[3].isdigit():
            d.monitors = max(1, int(parts[3]))
        if len(parts) >= 5:
            d.primary_name = parts[4]
    except (ValueError, IndexError):
        pass

    # DPI scaling. 96 dpi == 100%.
    try:
        user32 = ctypes.windll.user32
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
        hdc = user32.GetDC(0)
        LOGPIXELSX = 88
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX)
        user32.ReleaseDC(0, hdc)
        if dpi:
            d.scale_percent = int(round(dpi / 96.0 * 100))
    except Exception:
        pass

    # Fall back to the virtual screen metrics if WMI gave nothing useful.
    if d.width < 640:
        try:
            d.width = ctypes.windll.user32.GetSystemMetrics(0) or 1920
            d.height = ctypes.windll.user32.GetSystemMetrics(1) or 1080
        except Exception:
            pass
    return d


def _detect_timezone() -> tuple[str, str]:
    win = _ps("(Get-TimeZone).Id")
    win = win.splitlines()[-1].strip() if win else ""
    if not win:
        try:
            r = subprocess.run(["tzutil", "/g"], capture_output=True, text=True,
                               timeout=10, creationflags=NO_WINDOW)
            win = (r.stdout or "").strip()
        except Exception:
            win = ""
    return TZ_MAP.get(win, "UTC"), win


def _detect_locale() -> str:
    tag = _ps("(Get-Culture).Name")
    tag = tag.splitlines()[-1].strip() if tag else ""
    if not tag:
        try:
            tag = (locale.getdefaultlocale()[0] or "en_US").replace("_", "-")
        except Exception:
            tag = "en-US"
    tag = tag.replace("-", "_")
    if "_" not in tag:
        tag = f"{tag}_{tag.upper()}"
    return f"{tag}.UTF-8"


def _detect_keyboard() -> tuple[str, str, str]:
    klid = _ps(
        "$l = Get-WinUserLanguageList | Select-Object -First 1;"
        "if ($l.InputMethodTips.Count -gt 0) { $l.InputMethodTips[0] } else { '' }")
    klid = klid.splitlines()[-1].strip() if klid else ""
    # Format is "LANGID:KLID"; we want the KLID half.
    if ":" in klid:
        klid = klid.split(":")[-1]
    klid = klid.strip().lower()
    if klid in KLID_MAP:
        q, c, x = KLID_MAP[klid]
        return (q or "en-us", c, x)

    # Fall back to the keyboard layout of the current thread.
    try:
        hkl = ctypes.windll.user32.GetKeyboardLayout(0)
        langid = hkl & 0xFFFF
        key = f"{langid:08x}"
        if key in KLID_MAP:
            q, c, x = KLID_MAP[key]
            return (q or "en-us", c, x)
    except Exception:
        pass
    return ("en-us", "us", "us")


def _sanitise_username(raw: str) -> str:
    """Linux usernames: lowercase, start with a letter, [a-z0-9_-]."""
    s = "".join(ch for ch in raw.lower() if ch.isalnum() or ch in "_-")
    s = s.lstrip("0123456789-_")
    if not s or not s[0].isalpha():
        s = "arch" + (s or "")
    return s[:31] or "arch"


def _detect_identity() -> tuple[str, str]:
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "arch"
    name = _sanitise_username(user)

    host = (os.environ.get("COMPUTERNAME") or "").strip()
    clean = "".join(ch if (ch.isalnum() or ch == "-") else "-"
                    for ch in host.lower()).strip("-")
    # Very short or empty machine names (a bare "W" is a real case) make a
    # useless hostname, so fall back to something descriptive instead.
    if len(clean) < 3:
        hostname = "arch-hypr"
    else:
        hostname = f"{clean[:24].rstrip('-')}-arch"
    return name, hostname


def _detect_memory_cpu() -> tuple[float, int, int, int]:
    from . import deps
    ram = deps.total_ram_gb()
    cpus = deps.cpu_count()
    # Half the RAM, rounded down to a whole GB, clamped so Windows keeps enough.
    mem_mb = int(ram * 1024 * 0.5) // 1024 * 1024
    mem_mb = max(4096, min(mem_mb, 16384))
    if ram - (mem_mb / 1024) < 4:
        mem_mb = max(2048, int((ram - 4) * 1024) // 1024 * 1024)
    vcpu = max(2, min(cpus // 2, 12))
    return ram, cpus, mem_mb, vcpu


def _detect_gpu() -> str:
    """
    Name of the most capable graphics adapter, preferring a discrete one.

    Only used to make the passthrough explanation concrete ("your RTX 4060"
    rather than "your graphics card"), so an empty string is a fine answer.
    """
    out = _ps("(Get-CimInstance Win32_VideoController).Name -join '|'")
    names = [n.strip() for n in (out.splitlines()[-1] if out else "").split("|")]
    names = [n for n in names if n and "basic display" not in n.lower()]
    if not names:
        return ""
    discrete = ("nvidia", "geforce", "rtx", "gtx", "quadro", "radeon", "arc ")
    for n in names:
        if any(k in n.lower() for k in discrete):
            return n
    return names[0]


def _detect_audio() -> bool:
    out = _ps("@(Get-CimInstance Win32_SoundDevice | "
              "Where-Object { $_.Status -eq 'OK' }).Count")
    try:
        return int(out.splitlines()[-1].strip()) > 0
    except (ValueError, IndexError):
        return True


def _detect_edition() -> str:
    out = _ps("(Get-CimInstance Win32_OperatingSystem).Caption")
    return out.splitlines()[-1].strip() if out else ""


# --------------------------------------------------------------------------- #
def detect() -> HostInfo:
    """Probe everything. Never raises; each field falls back independently."""
    info = HostInfo()
    notes = info.detected

    try:
        info.display = _detect_display()
        d = info.display
        notes.append(f"Display {d.width}x{d.height} @ {d.refresh_hz} Hz, "
                     f"{d.scale_percent}% scaling"
                     + (f", {d.monitors} monitors" if d.monitors > 1 else ""))
    except Exception:
        notes.append("Display: using 1920x1080 default")

    try:
        info.timezone, info.timezone_windows = _detect_timezone()
        notes.append(f"Time zone {info.timezone}"
                     + (f" (from \"{info.timezone_windows}\")"
                        if info.timezone_windows else ""))
    except Exception:
        notes.append("Time zone: using UTC default")

    try:
        info.locale = _detect_locale()
        notes.append(f"Locale {info.locale}")
    except Exception:
        pass

    try:
        info.qemu_keymap, info.console_keymap, info.xkb_layout = _detect_keyboard()
        notes.append(f"Keyboard {info.xkb_layout} ({info.qemu_keymap})")
    except Exception:
        pass

    try:
        info.username, info.hostname = _detect_identity()
        notes.append(f"Account {info.username}, host name {info.hostname}")
    except Exception:
        pass

    try:
        (info.ram_gb, info.logical_cpus,
         info.suggested_memory_mb, info.suggested_cpus) = _detect_memory_cpu()
        notes.append(f"{info.ram_gb:.0f} GB RAM and {info.logical_cpus} CPUs "
                     f"-> {info.suggested_memory_mb // 1024} GB and "
                     f"{info.suggested_cpus} vCPUs for the VM")
    except Exception:
        pass

    try:
        info.has_audio = _detect_audio()
    except Exception:
        pass

    try:
        info.gpu = _detect_gpu()
        if info.gpu:
            notes.append(f"Graphics {info.gpu}")
    except Exception:
        pass

    try:
        info.windows_edition = _detect_edition()
    except Exception:
        pass

    return info


_cache: HostInfo | None = None


def cached() -> HostInfo:
    global _cache
    if _cache is None:
        _cache = detect()
    return _cache


def refresh() -> HostInfo:
    global _cache
    _cache = detect()
    return _cache
