**ArchVM Manager** installs and runs Arch Linux with the Hyprland desktop inside
QEMU on Windows, and sets up everything it needs to do so along the way.

`virt-manager` is Linux-only, so managing plain QEMU on Windows has meant
hand-written command lines. This is the first public release of the tool that
fills that gap.

---

## Download

| File | Use it when |
|---|---|
| **`ArchVM-2.1.0-windows-x64.zip`** | **Recommended.** Unzip anywhere, run `ArchVM.exe`. Starts fast. |
| `ArchVM-2.1.0-windows-x64-portable.exe` | A single self-contained file. Tidier, a few seconds slower to start. |
| `seed-2.1.0.iso` | Only if you are rebuilding the seed ISO by hand. The app generates its own. |

Verify what you downloaded against `SHA256SUMS.txt`:

```powershell
Get-FileHash .\ArchVM-2.1.0-windows-x64.zip -Algorithm SHA256
```

**These builds are not code-signed**, so SmartScreen will warn the first time you
run one — choose *More info → Run anyway*. `docs/code-signing.md` explains why
and what it would take to change.

---

## What it does

**Guided setup.** A five-step wizard scans your PC for CPU virtualization
support, the Windows Hypervisor Platform, QEMU, virgl, the OpenSSH client, RAM,
disk space and UEFI firmware — then fixes what is missing. Every fix that needs
administrator rights is collected into **one** elevated script, so you approve a
single UAC prompt rather than five. Declining is handled gracefully.

**It reads your machine for defaults.** Display size, refresh rate, DPI scaling,
time zone, locale, keyboard layout, account name, RAM and CPU count are detected
and turned into sensible VM settings. The wizard shows you what it found and lets
you override any of it.

**Fully automated Arch install.** Three staged scripts partition the disk,
`pacstrap` the base system, and build the desktop on first login — finishing at a
graphical SDDM login with no manual steps in between. The Arch ISO is downloaded
from the official mirrors and **SHA256-verified** before use.

**Hyprland, properly configured.** [end-4/dots-hyprland](https://github.com/end-4/dots-hyprland)
(illogical-impulse) with the [pctrade/end4-pc](https://github.com/pctrade/end4-pc)
Quickshell fork layered on top.

**Text into the guest.** QEMU has no host↔guest clipboard, so the app types text
in over the QEMU monitor — including your Windows clipboard, in one click.

**Runs in the tray.** Closing the window keeps the app alive with a full
right-click menu; the icon's pip is grey when the VM is stopped and green when it
is running, readable at 16 px.

**Themed and accessible.** Light, dark and auto, seven accents, a painted
textured backdrop and Windows 11 Mica translucency — with automatic fallbacks
when Mica is unavailable or high contrast is on. Every control has an accessible
name, text scales 80–160%, motion can be reduced, and the whole interface is
keyboard-operable.

---

## Requirements

| | |
|---|---|
| OS | Windows 10/11 (x64) |
| CPU | VT-x / AMD-V enabled in firmware |
| RAM | 8 GB minimum, 16 GB comfortable |
| Disk | 60 GB free minimum, 140 GB recommended |
| Software | QEMU — the wizard installs it via `winget` if absent |

Enabling the Windows Hypervisor Platform requires a reboot. The wizard tells you
when, and offers to do it.

---

## Two things to know before you start

**There is no GPU passthrough, and there cannot be.** Not in this app and not in
any other, on a Windows host: Hyper-V DDA is Windows Server only, QEMU's Windows
accelerator (WHPX) has no VFIO support, and laptop dGPUs are usually muxless. The
VM uses `virtio-vga-gl` (virgl) for hardware-accelerated OpenGL instead —
Hyprland's compositing, blur and animations are smooth, but it is not bare metal.
If you want the real GPU, dual-boot.

**This is Windows-only by design.** The app is built on `winget`, `dism`, the
Windows registry and Win32 APIs, and exists precisely because `virt-manager` does
not run on Windows. On Linux, use `virt-manager`. There is no macOS build.

---

## Known limitations

- Builds are unsigned; SmartScreen warns on first run.
- `seed/vm.conf` stores the guest password in plain text — it is a local VM
  credential file and is git-ignored, but do not reuse a password that matters.
- `Ctrl+Alt+Delete` never reaches the guest, and `Ctrl+Alt+F` is QEMU's own
  fullscreen rather than Hyprland's. Both are called out in the wizard.

---

## Documentation

- [Install walkthrough, keyboard notes, troubleshooting and Hyprland keybinds](https://github.com/nikhlgoel/ArchVM-manager/blob/main/docs/vm-guide.md)
- [Application internals](https://github.com/nikhlgoel/ArchVM-manager/blob/main/app/README.md)
- [Full changelog](https://github.com/nikhlgoel/ArchVM-manager/blob/main/CHANGELOG.md)

Found a problem? [Open an issue](https://github.com/nikhlgoel/ArchVM-manager/issues/new/choose)
with your Windows edition and the contents of the Logs page.

---

MIT licensed. The desktop configuration belongs to its authors:
[end-4/dots-hyprland](https://github.com/end-4/dots-hyprland) and
[pctrade/end4-pc](https://github.com/pctrade/end4-pc).
