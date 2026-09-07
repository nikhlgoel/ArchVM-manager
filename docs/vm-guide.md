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

## What the install does on its own

Once you press **Install Arch**, nothing else needs typing:

1. The VM boots the Arch ISO and the installer command is typed in for you.
2. `bootstrap.sh` partitions, `pacstrap`s the base system and configures it.
3. It unmounts and **powers the VM off** - not reboots, because the ISO is
   still first in the boot order at that point.
4. The manager notices and **restarts the VM from the disk**.
5. That boot **logs you in on tty1 automatically** and builds the Hyprland
   desktop. This is the long part.
6. When it finishes it removes the autologin and **reboots into SDDM**, the
   graphical login.

You end at a greeter with the Hyprland session selected. Sign in with the
password you set in the wizard.

If a step fails the chain stops at a shell with the error on screen, autologin
still in place, and `~/firstboot.sh` ready to re-run. The log is at
`~/hypr-install.log`.

To keep the old behaviour - stopping after each stage so you can look around -
set `AUTO_REBOOT=no` in `seed/vm.conf` and rebuild the seed ISO.

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

---

## Graphics: why there is no OpenGL

**virgl (`virtio-vga-gl`) does not work on Windows hosts.** It needs DMABUF to
present its scanout, and no Windows QEMU display backend implements it:

| Pairing | What happens |
|---|---|
| `virtio-vga-gl` + `gtk,gl=on` | QEMU **exits**: *GtkGLArea console lacks DMABUF support* |
| `virtio-vga-gl` + `sdl,gl=on` | QEMU runs, window stays **black** — the scanout never presents |
| `virtio-vga` + `gtk` | **Works** |
| `virtio-vga` + `sdl` | **Works** |

So the VM uses plain `virtio-vga`, and the guest falls back to Mesa's `llvmpipe`
software renderer. Hyprland runs; compositing is on the CPU. Turning blur off in
`~/.config/hypr/custom/general.lua` helps noticeably.

Verify inside the guest with:

```bash
glxinfo -B | grep -i renderer
```

`llvmpipe` is expected here. There is no configuration that produces `virgl` on
a Windows host.

---

## "TDX not supported by the host platform"

Harmless. The Linux kernel's TDX guest driver probes for Intel Trust Domain
Extensions on every boot and logs this at error priority when they are absent —
which they always are in a normal VM. It has no effect on the install and can be
ignored.

---

## The screen looks blank after boot

The console is almost certainly working. Press **Enter** — the login prompt is
drawn once, and a short prompt on a 1920x1080 black screen is easy to miss.

If the window is genuinely black and does not respond to Enter, the display
pairing is wrong; see the graphics table above. Newer builds correct this
automatically on startup and tell you they did.

## The desktop install stopped partway

It is resumable and idempotent. Log in again — it restarts by itself — or run:

```bash
~/firstboot.sh
```

Progress is appended to `~/hypr-install.log`, so you can see exactly where it
stopped:

```bash
tail -40 ~/hypr-install.log
```

---

## What happens after the base install

You should not see a console login at any point on the happy path:

1. **Base install finishes** and the VM reboots.
2. **The desktop builds itself.** A systemd unit (`archvm-setup.service`) runs
   the build on first boot with its output on tty1, so the screen shows package
   progress rather than a login prompt. Nobody needs to log in.
3. **It enables SDDM and reboots** when finished.
4. **You land on a graphical greeter** with the Hyprland session and your
   account already selected.

The build takes 30-60 minutes and compiles a lot of AUR packages. Interrupting
it is safe — it holds a lock, resumes on the next boot, and appends to
`~/hypr-install.log`.

If the build **fails**, the unit hands tty1 back so you get a normal login and
a message explaining how to resume.

### Repairing an existing guest

A VM installed by an older version can be upgraded to this flow. Boot the
installer ISO with the disk attached and run:

```
mkdir -p /s && mount /dev/sr1 /s && bash /s/repair.sh
```

That installs the current first-boot script and unit, drops `quiet` from the
kernel command line, fixes the sudo rule, and sets the right boot target. It is
safe on a finished install — it detects the completion marker and only switches
to the graphical target.

### Why the sudo rule looks heavy-handed

`/etc/sudoers.d/99-firstboot-tmp` contains:

```
Defaults:<user> !authenticate
<user> ALL=(ALL:ALL) NOPASSWD: SETENV: ALL
```

A plain `NOPASSWD: ALL` is not sufficient. `makepkg` calls sudo with
`--preserve-env`, which needs the `SETENV` tag, and any uncovered path falls
back to prompting. Inside a systemd unit that prompt is effectively invisible
and blocks the build indefinitely. `firstboot.sh` now asserts `sudo -n true`
before starting, so a broken rule fails in seconds with an explanation instead
of hanging.

The rule is removed automatically when the build completes.
