# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] — 2026-09-07

First public release.

### Added

- **Guided setup wizard** — five steps (Welcome → System check → Configure →
  Install → Done) that scan for virtualization support, the Windows Hypervisor
  Platform, QEMU, virgl, OpenSSH, RAM, disk space, UEFI firmware and the Arch
  ISO, then fix what is missing behind a **single** administrator prompt.
- **Host detection** — display size, refresh rate and DPI, time zone, locale,
  keyboard layout, account name, RAM and CPU count are read from Windows and used
  as the VM's defaults, with every value overridable in the wizard.
- **Automated Arch install** — three staged scripts partition the disk,
  `pacstrap` the base system, and build the Hyprland desktop on first login,
  finishing at a graphical SDDM login.
- **Host → guest text injection** over the QEMU monitor, since QEMU has no
  clipboard channel.
- **System tray** with a full right-click menu; closing the window keeps the app
  running.
- **Light/dark theming** with seven accents, a painted textured backdrop and
  Windows 11 Mica translucency, with automatic fallbacks when Mica is
  unavailable or high contrast is active.
- **Animated startup splash** built around the application mark.
- **Accessibility throughout** — accessible names on every control, 80–160% text
  scaling, reduce-motion, full keyboard operation and high-contrast support.
- **Windows installer** (Inno Setup) with a Start Menu entry, optional desktop
  shortcut and an uninstaller in Add/Remove Programs. Installs per-user
  without a UAC prompt, or system-wide on request. Uninstalling never
  touches VM disks and asks before removing settings.
- **PyInstaller packaging** with generated icons, portable zip and single-file
  builds, and optional Authenticode signing via `build.py --sign`.
- Documentation: VM guide, application reference and a code-signing guide.

### Fixed

- The setup wizard named a hard-coded graphics card rather than the one actually
  installed.
- Locale generation for locales whose name omits the codeset.
- A failed build could leave a half-deleted bundle behind in `dist/`.

### Known limitations

- **Windows only.** The app is built on winget, dism, the Windows registry and
  Win32 APIs. Linux users are better served by `virt-manager`.
- **No GPU passthrough**, and it is not possible on a Windows host — see the
  README. The VM uses virgl for hardware-accelerated OpenGL instead.
- Releases are unsigned, so SmartScreen warns on first run.

[2.1.0]: https://github.com/nikhlgoel/ArchVM-manager/releases/tag/v2.1.0
