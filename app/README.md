# ArchVM — application

A compiled Windows desktop app that manages the Arch Linux + Hyprland QEMU VM.
virt-manager is Linux-only, so this fills the gap.

Run the built `ArchVM.exe`, or from source: `python run.py`.

---

## Build

```bash
python build.py            # onedir  (fast start, recommended)
python build.py --onefile  # single .exe (slower start, tidier)
python build.py --clean    # wipe build/ and dist/ first
```

The build regenerates the icon from `archvm/icons.py`, runs PyInstaller, and
repoints the Desktop and Start Menu shortcuts at the new executable.

Output: `dist/ArchVM/ArchVM.exe` (~2.4 MB exe, ~111 MB bundle).

---

## Module layout

| File | Responsibility |
|---|---|
| `archvm/paths.py` | Locations for VM data, QEMU, settings — each with a fallback chain |
| `archvm/config.py` | `VMConfig` + `AppSettings`, atomic saves, type-tolerant loading, QEMU arg construction |
| `archvm/theme.py` | Light/dark/auto palettes, gradient QSS, Windows Mica backdrop, high-contrast detection |
| `archvm/icons.py` | Icon drawn with QPainter at any size; `.ico`/`.png` writers |
| `archvm/qemu.py` | `VMRunner` (process), `MonitorClient` (HMP text injection), disk helpers |
| `archvm/widgets.py` | `Card`, `Stat`, `StatusDot`, `Toast`, accessible `button()` |
| `archvm/window.py` | Main window, six pages, all actions |
| `archvm/splash.py` | Animated startup splash, drawn with QPainter |
| `archvm/hostinfo.py` | Probes the Windows host for sensible VM defaults |
| `archvm/deps.py` | Environment detection and the elevated repair engine |
| `archvm/onboarding.py` | The five-step guided setup wizard |
| `archvm/tray.py` | Tray icon and full right-click menu |
| `archvm/app.py` | Entry point, single-instance guard, tray lifecycle |
| `build.py` | Icon generation + PyInstaller + shortcuts |

Nothing writes into the VM data directory except deliberate actions; user
settings live in `%APPDATA%\ArchVM`.

---

## Setup wizard

Opens automatically on first run, or whenever something essential is missing.
Also available any time from **Settings → Run setup wizard** or the tray menu.

Five steps: **Welcome → System check → Configure → Install → Done.**

### What it detects

| Check | Fix |
|---|---|
| CPU virtualization (VT-x/AMD-V) | manual — tells you to enable it in BIOS |
| Windows Hypervisor Platform | `dism /enable-feature` *(admin)* |
| QEMU | `winget install` *(admin)* |
| virgl 3D support | informational |
| OpenSSH client | `dism /Add-Capability` *(admin)* |
| RAM and CPU count | informational, drives the suggested VM size |
| Disk space | manual if below 60 GB |
| UEFI firmware | copied from the QEMU install |
| Arch Linux ISO | downloaded + **SHA256-verified** against the official mirror |
| seed.iso | rebuilt, and detected as stale when `vm.conf` changes |
| Virtual disk | created with `qemu-img` |

### One UAC prompt, not several

Every fix needing administrator rights is collected into a **single elevated
PowerShell script**, run through `ShellExecuteW(..., "runas", ...)`. The
elevated process writes a result marker the app polls, so the wizard knows
whether it succeeded. Declining is handled gracefully — those items are marked
failed and the rest still runs.

### Confirmation moved into the GUI

`bootstrap.sh` used to stop and ask you to type `YES` before wiping the disk.
The wizard now presents that as an explicit checkbox and passes `AUTO_CONFIRM=yes`
through `vm.conf`, so the confirmation happens once, in a place where it can
actually be read. Without the wizard, the script still prompts as before.

### Finishing

The last step spells out what is left in plain language, and lists the Hyprland
shortcuts that matter — plus the two that will trip you up (`Ctrl+Alt+Delete`
never reaches the guest; `Ctrl+Alt+F` is QEMU's own fullscreen). If a reboot is
required it offers a **Restart Windows now** button. Otherwise it offers to
start the Arch installation immediately: the VM boots and the installer command
is typed in automatically after a 45-second boot delay, with a manual button as
a fallback.

---

## System tray

Closing the window **keeps the app running in the tray** (configurable). The VM
keeps running regardless — QEMU is a separate process.

Right-click the tray icon for:

- VM state readout, Start / Install / Shut down / Force stop
- Quick actions — SSH, send clipboard to VM, type installer command, open folders
- Settings — theme, translucency, gradient, close-to-tray, start-with-Windows, notifications
- About, Quit

The tray icon's pip is grey when stopped and green when running, so state is
readable at 16px without opening anything.

---

## Theme

Three modes — `auto` (follows the Windows app theme), `dark`, `light` — with
seven accents. Surfaces use a diagonal gradient; when translucency is on, the
window requests the Windows 11 **Mica** backdrop through `DwmSetWindowAttribute`
and the surfaces become partly transparent over it.

Fallbacks, all automatic:

- Mica unavailable (older Windows, call rejected) → flat gradient, no error
- OS **high contrast** active → gradients and translucency disabled, borders thickened
- Unknown theme registry key → defaults to dark

---

## Accessibility

- Every interactive control has an accessible name; a post-build sweep
  (`_label_orphans`) derives one from the widget text, its form-row label, or its
  tooltip so nothing is ever unlabelled to a screen reader.
- **Text scaling 80–160%** in Settings, applied across the whole interface.
- **Reduce motion** disables the pulsing status indicator.
- Full keyboard operation: `Ctrl+1`…`6` pages, `Ctrl+R` start, `Ctrl+I` install,
  `Ctrl+L` logs, `F1` about, `Tab` reaches everything, visible focus rings.
- High-contrast mode respected automatically.
- Errors surface as non-modal toasts where possible, so nothing blocks.

---

## Robustness

- **Single instance** via `QSharedMemory` — two copies can't fight over one VM.
  If shared memory is unavailable the app still starts rather than refusing.
- **Atomic config writes** (temp file + replace), so a crash mid-save can't
  corrupt settings.
- **Type-tolerant config loading** — unknown keys ignored, wrong types coerced,
  corrupt JSON falls back to defaults instead of crashing.
- **Path fallbacks** — `ARCHVM_ROOT` / `ARCHVM_QEMU` env vars, then known
  locations, then the executable's directory.
- **Missing QEMU** is reported in a toast, not a crash.
- **No tray available** → close-to-tray disables itself so the app can't become
  unreachable.
- Automatic migration of the old `manager/config.json`.

---

## Notes

`manager/build_seed.py` sits outside the package on purpose: it has no Qt
dependency and runs standalone, so the seed ISO can be rebuilt without the GUI.
The Guest page shells out to it to regenerate `seed.iso` after `vm.conf` changes.
