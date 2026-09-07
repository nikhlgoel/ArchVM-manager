#!/usr/bin/env python3
"""
Build ArchVM.exe with PyInstaller.

    python build.py            # onedir (fast start, recommended)
    python build.py --onefile  # single .exe (slower start, tidier)
    python build.py --clean    # wipe build/ and dist/ first

Also (re)generates the application icon and refreshes the Desktop and
Start Menu shortcuts so they point at the built executable.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ASSETS = APP_DIR / "assets"
ICO = ASSETS / "archvm.ico"
PNG = ASSETS / "archvm.png"
DIST = APP_DIR / "dist"
WORK = APP_DIR / "build"
NAME = "ArchVM"


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def make_icon() -> bool:
    """Render the icon via the app's own drawing code (offscreen Qt)."""
    log("generating icon…")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(APP_DIR))
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from archvm import icons
        ok_ico = icons.write_ico(ICO)
        icons.write_png(PNG, 512)
        log(f"icon: {ICO}  ({'ok' if ok_ico else 'FAILED'})")
        return ok_ico
    except Exception as e:
        log(f"icon generation failed: {e}")
        return False


def build(onefile: bool = False, clean: bool = False) -> Path | None:
    if clean:
        for d in (DIST, WORK):
            if d.exists():
                log(f"removing {d}")
                shutil.rmtree(d, ignore_errors=True)

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",                     # no console window
        "--name", NAME,
        "--distpath", str(DIST),
        "--workpath", str(WORK),
        "--specpath", str(APP_DIR),
        "--paths", str(APP_DIR),
        # Qt pulls a lot in; drop what we never touch to keep size sane.
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtQuick3D",
        "--exclude-module", "PySide6.QtCharts",
        "--exclude-module", "PySide6.QtDataVisualization",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "PySide6.QtBluetooth",
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--hidden-import", "archvm",
    ]
    if ICO.exists():
        args += ["--icon", str(ICO)]
    args += ["--onefile"] if onefile else ["--onedir"]
    args += [str(APP_DIR / "run.py")]

    log("running PyInstaller (this takes a minute)…")
    r = subprocess.run(args, cwd=APP_DIR)
    if r.returncode != 0:
        log("PyInstaller FAILED")
        return None

    exe = DIST / (f"{NAME}.exe" if onefile else f"{NAME}/{NAME}.exe")
    if not exe.exists():
        log(f"expected executable missing: {exe}")
        return None
    size = exe.stat().st_size / (1024 * 1024)
    log(f"built {exe}  ({size:.1f} MB)")
    return exe


def make_shortcuts(exe: Path) -> None:
    """Point Desktop + Start Menu at the built exe. Silently skips on failure."""
    ps = f'''
$ws = New-Object -ComObject WScript.Shell
$targets = @(
  (Join-Path ([Environment]::GetFolderPath('Desktop')) 'ArchVM Manager.lnk'),
  (Join-Path $env:APPDATA 'Microsoft\\Windows\\Start Menu\\Programs\\ArchVM Manager.lnk')
)
foreach ($t in $targets) {{
  $sc = $ws.CreateShortcut($t)
  $sc.TargetPath       = '{exe}'
  $sc.WorkingDirectory = '{exe.parent}'
  $sc.IconLocation     = '{ICO if ICO.exists() else exe}'
  $sc.Description      = 'Arch Linux + Hyprland VM (QEMU)'
  $sc.WindowStyle      = 1
  $sc.Save()
  Write-Output "shortcut -> $t"
}}
'''
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=60)
        for line in (r.stdout or "").splitlines():
            log(line)
        if r.returncode != 0:
            log("shortcut update failed: " + (r.stderr or "").strip()[:200])
    except Exception as e:
        log(f"shortcut update skipped: {e}")


def main() -> int:
    onefile = "--onefile" in sys.argv
    clean = "--clean" in sys.argv
    print(f"\nBuilding {NAME} ({'onefile' if onefile else 'onedir'})\n")

    ASSETS.mkdir(parents=True, exist_ok=True)
    make_icon()
    exe = build(onefile=onefile, clean=clean)
    if not exe:
        return 1
    make_shortcuts(exe)
    print(f"\nDone.  {exe}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
