Run **Arch Linux with Hyprland** in QEMU on Windows. A guided wizard finds what
your PC is missing, installs it behind a single administrator prompt, and the
Arch install then runs start to finish on its own.

`virt-manager` is Linux-only. This fills that gap.

## Download

| File | |
|---|---|
| **`ArchVM-2.2.0-windows-x64-setup.exe`** | **Recommended.** Proper installer — Start Menu entry, optional desktop shortcut, and an uninstaller in Add/Remove Programs. Installs per-user with no UAC prompt, or system-wide if you choose. |
| `ArchVM-2.2.0-windows-x64.zip` | Portable. Unzip anywhere and run `ArchVM.exe`. Nothing is written to the registry. |
| `ArchVM-2.2.0-windows-x64-portable.exe` | Portable, single file. Tidiest, a few seconds slower to start. |
| `seed-2.2.0.iso` | Only if rebuilding the seed ISO by hand. The app makes its own. |

Uninstalling never touches your VM disks or ISOs, and asks before removing your
settings.

Check your download against `SHA256SUMS.txt`:

```powershell
Get-FileHash .\ArchVM-2.2.0-windows-x64.zip -Algorithm SHA256
```

Not code-signed, so SmartScreen warns on first run — *More info → Run anyway*.

## New in 2.2.0

**The install is now hands-off.** Press **Install Arch** and walk away — the
base system installs, the VM restarts itself, the Hyprland desktop builds, and
it reboots into the graphical login. Previously it stopped three times: to type
`umount -R /mnt && reboot`, to log in at a bare console so the desktop build
would start, and to reboot again at the end.

**QEMU no longer freezes.** The "QEMU is not responding" dialog during install
and first boot was disk I/O blocking QEMU's main loop — the same loop that
answers Windows. Block I/O now runs on its own thread.

**Choose where VM files live.** Settings → Locations → Change, with a
free-space check. Existing files are left in place rather than silently copied.

## Highlights

- **Guided setup** — checks virtualization, Hypervisor Platform, QEMU, virgl,
  OpenSSH, RAM, disk and firmware, then fixes what's missing in **one** UAC prompt.
- **Reads your machine** for VM defaults: display, DPI, time zone, locale,
  keyboard, RAM and CPU count. All overridable.
- **Automated Arch install** — partition, `pacstrap`, then the Hyprland desktop
  on first login, ending at a graphical SDDM login. The ISO is SHA256-verified.
- **Text into the guest** over the QEMU monitor, since QEMU has no clipboard.
- **System tray** — closing the window keeps it running.
- **Light/dark theming** with Mica translucency, and full keyboard/screen-reader
  accessibility.

## Requirements

Windows 10/11 x64 · VT-x or AMD-V enabled in firmware · 8 GB RAM (16 comfortable)
· 60 GB free disk (140 recommended). The wizard installs QEMU via `winget`.

## Two things to know

**No GPU passthrough, and there cannot be** — on a Windows host Hyper-V DDA is
Server-only and QEMU's WHPX accelerator has no VFIO. The VM uses virgl for
accelerated OpenGL instead: smooth, but not bare metal.

**Windows only by design.** Built on `winget`, `dism` and Win32 APIs. On Linux,
use `virt-manager`.

## Links

[Install guide & troubleshooting](https://github.com/nikhlgoel/ArchVM-manager/blob/main/docs/vm-guide.md)
· [Changelog](https://github.com/nikhlgoel/ArchVM-manager/blob/main/CHANGELOG.md)
· [Report a bug](https://github.com/nikhlgoel/ArchVM-manager/issues/new/choose)

MIT. Desktop config belongs to [end-4/dots-hyprland](https://github.com/end-4/dots-hyprland)
and [pctrade/end4-pc](https://github.com/pctrade/end4-pc).
