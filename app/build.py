#!/usr/bin/env python3
"""
Build ArchVM.exe with PyInstaller.

    python build.py                    # onedir (fast start, recommended)
    python build.py --onefile          # single .exe (slower start, tidier)
    python build.py --clean            # wipe build/ and dist/ first
    python build.py --sign "Subject"   # Authenticode-sign the result
    python build.py --no-shortcuts     # skip the Desktop/Start Menu step (CI)

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
        QApplication.instance() or QApplication([])
        from archvm import icons
        ok_ico = icons.write_ico(ICO)
        icons.write_png(PNG, 512)
        log(f"icon: {ICO}  ({'ok' if ok_ico else 'FAILED'})")
        return ok_ico
    except Exception as e:
        log(f"icon generation failed: {e}")
        return False


def running_instances() -> list[int]:
    """PIDs of any running ArchVM.exe. They hold locks on the bundle."""
    try:
        r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {NAME}.exe",
                            "/FO", "CSV", "/NH"],
                           capture_output=True, text=True, timeout=20)
        pids = []
        for line in (r.stdout or "").splitlines():
            parts = [x.strip('"') for x in line.split('","')]
            if len(parts) > 1 and parts[0].lower() == f"{NAME.lower()}.exe":
                try:
                    pids.append(int(parts[1]))
                except ValueError:
                    pass
        return pids
    except Exception:
        return []


def stop_instances() -> bool:
    """
    Close running copies before touching dist/.

    A half-deleted bundle is worse than no bundle: the launcher still exists,
    the interpreter does not, and the user gets "Failed to start embedded
    python interpreter". Refusing to build is the safer failure.
    """
    pids = running_instances()
    if not pids:
        return True
    log(f"{NAME} is running (pid {', '.join(map(str, pids))}) and holds the bundle open.")
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, text=True)
    import time
    for _ in range(20):
        if not running_instances():
            log("closed running instances")
            return True
        time.sleep(0.25)
    log("could not close them - close the app and try again")
    return False


def verify(exe: Path) -> bool:
    """Confirm the bundle actually holds an interpreter before declaring success."""
    if not exe.exists():
        log(f"missing executable: {exe}")
        return False
    internal = exe.parent / "_internal"
    if internal.exists():
        needed = ["base_library.zip"]
        missing = [n for n in needed if not (internal / n).exists()]
        if not list(internal.glob("python3*.dll")):
            missing.append("python3*.dll")
        if not (internal / "PySide6" / "plugins" / "platforms" / "qwindows.dll").exists():
            missing.append("qwindows.dll")
        if missing:
            log("bundle is INCOMPLETE, missing: " + ", ".join(missing))
            return False
    log("bundle verified")
    return True


def build(onefile: bool = False, clean: bool = False) -> Path | None:
    if not stop_instances():
        return None

    if clean:
        for d in (DIST, WORK):
            if not d.exists():
                continue
            log(f"removing {d}")
            shutil.rmtree(d, ignore_errors=True)
            if d.exists():
                # A partial delete leaves a bundle that launches but cannot
                # start - do not hand that to the user.
                log(f"could not fully remove {d}; close anything using it")
                return None

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

    # The installer scripts have to travel with the executable. Without
    # them the app can detect QEMU, download the ISO and create a disk,
    # and then cannot install anything - which is exactly what a user
    # who installed from the .exe rather than the repo would hit.
    seed = APP_DIR.parent / "seed"
    for f in sorted(seed.glob("*.sh")) + [seed / "vm.conf.example"]:
        if f.exists():
            args += ["--add-data", f"{f}{os.pathsep}seed"]
            log(f"bundling seed/{f.name}")

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
    if not verify(exe):
        return None
    size = exe.stat().st_size / (1024 * 1024)
    log(f"built {exe}  ({size:.1f} MB)")
    return exe


def find_signtool() -> Path | None:
    """Locate signtool.exe from the Windows SDK. Newest version wins."""
    from shutil import which
    found = which("signtool")
    if found:
        return Path(found)
    for base in (Path(r"C:\Program Files (x86)\Windows Kits\10\bin"),
                 Path(r"C:\Program Files\Windows Kits\10\bin")):
        if not base.exists():
            continue
        cands = sorted(base.glob("*/x64/signtool.exe"), reverse=True)
        if cands:
            return cands[0]
    return None


def sign(exe: Path, subject: str) -> bool:
    """
    Authenticode-sign the executable. Always timestamps: without one the
    signature stops validating the day the certificate expires.
    """
    tool = find_signtool()
    if not tool:
        log("signtool not found - install the Windows SDK. Skipping signing.")
        return False
    cmd = [str(tool), "sign", "/fd", "SHA256",
           "/tr", "http://timestamp.digicert.com", "/td", "SHA256",
           "/n", subject, str(exe)]
    log(f"signing with \"{subject}\"...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log("signing FAILED: " + (r.stdout + r.stderr).strip()[:400])
        log("See docs/code-signing.md for how to obtain a certificate.")
        return False
    v = subprocess.run([str(tool), "verify", "/pa", str(exe)],
                       capture_output=True, text=True)
    log("signed and verified" if v.returncode == 0
        else "signed, but verification failed")
    return True


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


def find_iscc() -> Path | None:
    from shutil import which
    found = which("iscc")
    if found:
        return Path(found)
    for c in [
        Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]:
        if c.exists():
            return c
    return None


def build_installer(version: str = "2.3.0") -> Path | None:
    """Compile the official Windows installer into installables/setup."""
    iscc = find_iscc()
    if not iscc:
        log("Inno Setup (ISCC.exe) not found; skipping installer build.")
        return None
    iss = APP_DIR / "installer" / "archvm.iss"
    if not iss.exists():
        log(f"installer script missing: {iss}")
        return None
    out_dir = APP_DIR.parent / "installables" / "setup"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"ArchVM-Installer-{version}"
    cmd = [
        str(iscc),
        f"/DAppVersion={version}",
        f"/O{out_dir}",
        f"/F{out_name}",
        str(iss)
    ]
    log(f"compiling Inno Setup installer -> {out_name}.exe…")
    r = subprocess.run(cmd, cwd=APP_DIR, capture_output=True, text=True)
    target = out_dir / f"{out_name}.exe"
    if r.returncode == 0 and target.exists():
        sz = target.stat().st_size / (1024 * 1024)
        log(f"built installer: {target} ({sz:.1f} MB)")
        return target
    log("Inno Setup compile failed: " + (r.stderr or r.stdout or "")[:300])
    return None


def sync_installables(exe: Path, onefile: bool) -> None:
    """Keep the installables/ folder synchronized with the latest built binaries."""
    root_install = APP_DIR.parent / "installables"
    try:
        if onefile:
            dest = root_install / "portable" / f"{NAME}.exe"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(exe, dest)
            log(f"synced -> {dest}")
        else:
            dest_dir = root_install / "onedir"
            dest_dir.mkdir(parents=True, exist_ok=True)
            src_dir = exe.parent
            for item in src_dir.iterdir():
                d = dest_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, d)
            log(f"synced -> {dest_dir / exe.name}")
    except Exception as e:
        log(f"could not sync to installables/: {e}")


def main() -> int:
    onefile = "--onefile" in sys.argv
    clean = "--clean" in sys.argv
    with_installer = "--installer" in sys.argv or "-i" in sys.argv
    print(f"\nBuilding {NAME} ({'onefile' if onefile else 'onedir'})\n")

    ASSETS.mkdir(parents=True, exist_ok=True)
    make_icon()
    exe = build(onefile=onefile, clean=clean)
    if not exe:
        return 1

    sync_installables(exe, onefile)

    if "--sign" in sys.argv:
        i = sys.argv.index("--sign")
        subject = sys.argv[i + 1] if len(sys.argv) > i + 1 else ""
        if subject:
            sign(exe, subject)
        else:
            log("--sign needs a certificate subject name; skipping.")

    if "--no-shortcuts" in sys.argv:
        log("shortcuts skipped (--no-shortcuts)")
    else:
        make_shortcuts(exe)

    if with_installer and not onefile:
        from archvm.paths import APP_VERSION
        build_installer(APP_VERSION)

    print(f"\nDone.  {exe}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
