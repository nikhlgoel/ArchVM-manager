# Security policy

## Supported versions

Only the latest release receives fixes.

| Version | Supported |
|---|---|
| 2.1.x | yes |
| < 2.1 | no |

## Reporting a vulnerability

Please report privately through
[GitHub Security Advisories](https://github.com/nikhlgoel/ArchVM-manager/security/advisories/new)
rather than opening a public issue. Expect an initial response within a week.

## What this application does that is worth knowing

Being honest about the surface area, because some of it looks alarming and is
intentional:

- **It requests administrator rights.** The setup wizard collects every fix
  needing elevation into one PowerShell script and runs it through
  `ShellExecuteW(..., "runas", ...)`. The script is written to a temporary file
  you can read before approving the UAC prompt. It enables the Windows
  Hypervisor Platform, installs QEMU via `winget`, and adds the OpenSSH client.
- **It downloads the Arch Linux ISO** from the official mirror list and verifies
  it against the published **SHA256** checksum before use. A mismatch aborts.
- **`seed/vm.conf` stores the guest username and passwords in plain text.** This
  is a local VM credential file consumed by the installer scripts inside the
  guest; it is git-ignored and never leaves your machine. Do not reuse a password
  that matters.
- **The QEMU monitor socket** is how text is typed into the guest, since QEMU has
  no clipboard channel. It listens on localhost only.
- **Releases are currently unsigned.** SmartScreen will warn on first run. See
  [`docs/code-signing.md`](docs/code-signing.md) for the state of that work.
  Verify downloads against the SHA256 checksums published with each release.

## Out of scope

- The guest operating system and the Hyprland desktop configuration, which are
  fetched from [end-4/dots-hyprland](https://github.com/end-4/dots-hyprland) and
  [pctrade/end4-pc](https://github.com/pctrade/end4-pc) and belong to their
  authors.
- QEMU itself.
- Anything requiring an attacker to already have administrator access to the
  host.
