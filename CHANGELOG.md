# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.1] — 2026-09-07

First public release. (2.1.0 was built but never published.)

### Added

- **Guided setup wizard** — five steps (Welcome → System check → Configure →
  Install → Done) that scan for virtualization support, the Windows Hypervisor
  Platform, QEMU, virgl, OpenSSH, RAM, disk space, UEFI firmware and the Arch
  ISO, then fix what is missing behind a **single** administrator prompt.
- **Host detection** — display size, refresh rate and DPI, time zone, locale,
  keyboard layout, account name, RAM, CPU count and graphics adapter are read
  from Windows and used as the VM's defaults, all overridable in the wizard.
- **Automated Arch install** — three staged scripts partition the disk,
  `pacstrap` the base system, and build the Hyprland desktop on first login,
  finishing at a graphical SDDM login. The ISO is SHA256-verified.
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
  shortcut and an uninstaller in Add/Remove Programs. Installs per-user without
  a UAC prompt, or system-wide on request; `/CURRENTUSER` and `/ALLUSERS` work
  from the command line for scripted deployment. Uninstalling never touches VM
  disks or ISOs and asks before removing settings.
- **Portable builds** — a zip and a single-file executable — plus SHA256
  checksums, all built in CI on a clean runner.
- Documentation: VM guide, application reference and a code-signing guide.

### Fixed

- The startup splash was effectively invisible: host probing ran on the GUI
  thread and froze it for its entire visible life, and on a warm start the whole
  thing was over in under 300 ms. Probing now runs off-thread with the event
  loop pumped, and the splash guarantees a minimum visible time and eases its
  progress bar rather than snapping between fixed stops.
- The taskbar showed the Python interpreter's icon when running from source, as
  no AppUserModelID was set.
- The setup wizard named a hard-coded graphics card rather than the one actually
  installed.
- Locale generation for locales whose name omits the codeset.
- A failed build could leave a half-deleted bundle behind in `dist/`.
- `SHA256SUMS.txt` used CRLF endings, breaking `sha256sum -c` on Linux and WSL.

### Known limitations

- **Windows only.** The app is built on winget, dism, the Windows registry and
  Win32 APIs. Linux users are better served by `virt-manager`.
- **No GPU passthrough**, and it is not possible on a Windows host — see the
  README. The VM uses virgl for hardware-accelerated OpenGL instead.
- Releases are unsigned, so SmartScreen warns on first run.

[2.1.1]: https://github.com/nikhlgoel/ArchVM-manager/releases/tag/v2.1.1
