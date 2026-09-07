# Arch Linux + Hyprland VM

Automated QEMU setup running **illogical-impulse** (end-4/dots-hyprland) with the
**end4-pC** Quickshell fork layered on top.

Launch **ArchVM Manager** from the Desktop or Start Menu.

---

## About your graphics card

The VM **cannot** use your discrete GPU, and no software on a Windows host can
change that:

- **Hyper-V DDA** (real PCIe passthrough on Windows) requires Windows **Server**.
  Home and Pro are both excluded.
- **QEMU on Windows** runs on **WHPX**, which has no VFIO/PCIe passthrough. VFIO
  needs a **Linux host**.
- Most **laptop dGPUs are muxless** — they render into the integrated GPU's
  framebuffer and have no independent display path for a guest to drive.

The VM uses **`virtio-vga-gl` (virgl)** instead: real GPU-backed OpenGL through
the host driver. Good enough for Hyprland's compositing, blur and animations;
not the same as bare metal. Dual-booting is the only route to the actual GPU.

The setup wizard names the card it found on your machine, so the note you see
there is about your hardware specifically.

---

## Getting text into the VM

QEMU has **no host↔guest clipboard**. Two ways in, both built into the manager:

1. **Tools → Send text to the VM.** Types the text through the QEMU monitor.
   Click into the VM window first so the guest has keyboard focus.
2. **Tools → Open SSH session.** Opens a Windows terminal on `localhost:2222`
   with normal copy/paste. Better for real work. Requires the install finished.

---

## First run

1. Open **ArchVM Manager**.
2. *(optional)* **Guest** tab → set username, password, timezone → **Save and
   rebuild seed.iso**.
3. **Overview → Install Arch.**
4. At the installer's root prompt, click **"Type it into the VM"** on the
   Overview page. It enters this for you:

   ```
   mkdir -p /s && mount /dev/sr1 /s && bash /s/bootstrap.sh
   ```
5. Confirm the disk wipe with `YES`. Base install runs unattended (~15 min).
6. `umount -R /mnt`, then **Force stop** and **Start VM** — so it boots from
   disk instead of the ISO.
7. Log in. The desktop install (yay → dots-hyprland → end4-pC) runs
   automatically and takes **30–60 min**. Log: `~/hypr-install.log`.
8. Start the desktop with `Hyprland`.

---

## Keyboard notes

The keyboard is **PS/2** (QEMU's built-in i8042), not virtio, deliberately:

> `virtio-keyboard-pci` mistranslates shifted symbols — `Shift`+`0` producing
> nothing instead of `)` — and can leave modifier keys **stuck on the Windows
> host** after the VM exits.

The display backend defaults to **GTK**, which releases keyboard grabs more
reliably than SDL on Windows.

**If keys ever stick on the Windows side:** tap and release each of `Ctrl`,
`Alt`, `Shift` and `Win` once. That clears the stuck modifier state. No reboot
needed.

**QEMU reserves some combinations** — they never reach the guest:

| Combination | Effect |
|---|---|
| `Ctrl`+`Alt`+`F` | QEMU fullscreen toggle |
| `Ctrl`+`Alt`+`G` | Release input grab |
| `Ctrl`+`Alt`+`1`/`2` | Switch QEMU console |
| `Ctrl`+`Alt`+`Delete` | Intercepted by **Windows**, never reaches the guest |

For the session menu inside Hyprland, use the power icon in the bar.

---

## Manager

| Page | What's there |
|---|---|
| **Overview** | Status, specs at a glance, power controls, installer helper |
| **Hardware** | Memory, vCPUs, accelerator, GPU device, display backend, resolution, fullscreen, keyboard, keymap, audio, SSH port |
| **Guest** | Account + locale → regenerates `seed.iso`; install pipeline summary |
| **Tools** | Send text to VM, SSH session, disk info, snapshots, reset |
| **Logs** | Live QEMU output, launch command, copy to clipboard |

---

## VM defaults

| | |
|---|---|
| Memory | 8192 MB (of 16 GB) |
| vCPUs | 8 (of 16 threads) |
| Disk | 120 GB qcow2, sparse |
| Firmware | UEFI (systemd-boot) |
| Graphics | `virtio-vga-gl` + `gtk,gl=on` @ 1920×1080, fullscreen |
| Input | PS/2 keyboard + USB tablet (absolute pointer, no mouse grab) |
| Audio | Intel HDA via DirectSound |
| Accel | WHPX |
| Network | user NAT, host `localhost:2222` → guest SSH |
| Monitor | HMP on `127.0.0.1:55555` (used by text injection) |

---

## Layout

```
D:\ArchVM\
  ├─ README.md
  ├─ disks\   arch-hyprland.qcow2, OVMF_CODE.fd, OVMF_VARS.fd
  ├─ iso\     archlinux-x86_64.iso (SHA256-verified), seed.iso
  ├─ seed\    vm.conf, bootstrap.sh, chroot-setup.sh, firstboot.sh
  ├─ manager\ archvm_manager.py, build_seed.py, config.json, archvm.ico
  └─ logs\
```

**`seed\*.sh` must stay LF.** `build_seed.py` normalises on build, but keep your
editor from writing CRLF — CRLF breaks these scripts inside Linux.

---

## Troubleshooting

**Hyprland resolution looks zoomed** — virtio-gpu resizes the guest to match the
QEMU window, so a windowed VM gets a smaller display. Go fullscreen (default
now, or `Ctrl`+`Alt`+`F`). Don't pin a fixed mode in `monitors.lua`; that fights
the dynamic resize.

**Screen fully repaints when refocusing** — Hyprland's VFR stops rendering when
idle and repaints everything on wake. `~/.config/hypr/custom/general.lua` sets
`misc.vfr = false` to prevent this. Blur is also disabled there; re-enable it if
you want it back and performance allows.

**Check 3D acceleration is real:**

```bash
glxinfo -B | grep -i renderer
```

`virgl` = hardware accelerated. `llvmpipe` = software fallback; try the
`sdl,gl=on` backend instead.

**Never set `GALLIUM_DRIVER`** in the guest. Mesa selects virgl automatically via
the `virtio_gpu` DRM driver; forcing `virpipe` picks the vtest backend, which
expects a `virgl_test_server` socket and renders badly.

**First-login install failed partway** — it is idempotent, just re-run:

```bash
~/firstboot.sh
```

**WHPX error on start** — enable the platform from an **admin** prompt, reboot:

```
dism /online /enable-feature /featurename:HypervisorPlatform /all /norestart
```

**Reclaim host disk space** — stop the VM, then:

```
"C:\Program Files\qemu\qemu-img.exe" convert -O qcow2 arch-hyprland.qcow2 compacted.qcow2
```

---

## Credits

- [end-4/dots-hyprland](https://github.com/end-4/dots-hyprland) — illogical-impulse
- [pctrade/end4-pc](https://github.com/pctrade/end4-pc) — the Quickshell fork
