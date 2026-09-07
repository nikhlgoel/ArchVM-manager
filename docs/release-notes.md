Run **Arch Linux with Hyprland** in QEMU on Windows. A guided wizard finds what
your PC is missing, installs it behind a single administrator prompt, and the
Arch install then runs start to finish on its own.

`virt-manager` is Linux-only. This fills that gap.

## Download

| File | |
|---|---|
| **`ArchVM-2.1.0-windows-x64.zip`** | **Recommended.** Unzip, run `ArchVM.exe`. |
| `ArchVM-2.1.0-windows-x64-portable.exe` | Single file. Tidier, slower to start. |
| `seed-2.1.0.iso` | Only if rebuilding the seed ISO by hand. The app makes its own. |

Check your download against `SHA256SUMS.txt`:

```powershell
Get-FileHash .\ArchVM-2.1.0-windows-x64.zip -Algorithm SHA256
```

Not code-signed, so SmartScreen warns on first run — *More info → Run anyway*.

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
