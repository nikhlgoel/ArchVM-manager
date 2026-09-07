#!/usr/bin/env bash
# Stage 3: runs as the normal user on first login. Installs the desktop.
set -uo pipefail
source "$HOME/.vm.conf"

LOG="$HOME/hypr-install.log"

# The systemd unit and a login shell can both reach here. Only one may build,
# or they fight over pacman's database lock.
LOCK="$HOME/.local/share/archvm-setup.lock"
mkdir -p "$(dirname "$LOCK")"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "The desktop installation is already running (probably on tty1)."
  echo "Watch it with:  tail -f $LOG"
  exit 0
fi

exec > >(tee -a "$LOG") 2>&1

echo "############################################################"
echo "#  Installing illogical-impulse (Hyprland) + $FORK_NAME"
echo "#"
echo "#  This takes 30-60 minutes and compiles a lot of packages."
echo "#  It is safe to interrupt: log in again, or run ~/firstboot.sh,"
echo "#  and it picks up where it stopped."
echo "#"
echo "#  Log: $LOG"
echo "############################################################"

die(){
  echo
  echo "############################################################"
  echo "!! FAILED: $*"
  echo "!! Nothing is lost - this is resumable."
  echo "!! Log in and it restarts, or run:  ~/firstboot.sh"
  echo "!! Full log: $LOG"
  echo "############################################################"
  # Running unattended we own tty1; give it back so there is a usable login.
  if [ "${ARCHVM_UNATTENDED:-}" = "1" ]; then
    sudo systemctl start getty@tty1.service 2>/dev/null || true
  fi
  exit 1
}

# Self-heal: ensure the whole home tree is ours before anything writes to it.
if [ "$(stat -c %U "$HOME/.local" 2>/dev/null || echo "$USER")" != "$USER" ]; then
  echo "==> Fixing ownership of $HOME"
  sudo chown -R "$USER:$USER" "$HOME"
fi

# The kernel logs "virt/tdx: TDX not supported by the host platform" at error
# priority on every boot inside a VM. It is informational - the TDX guest
# driver probing for Intel Trust Domain Extensions - and affects nothing.
echo "==> Note: any 'TDX not supported' message in the log is harmless."

# Assert unattended sudo before doing anything long. Without this a missing
# rule surfaces an hour in, as a password prompt nobody is watching, and the
# build hangs until the VM is killed.
echo "==> Checking unattended sudo"
if ! sudo -n true 2>/dev/null; then
  die "passwordless sudo is not active. /etc/sudoers.d/99-firstboot-tmp is
    missing or wrong, so the build would stop at a password prompt.
    Re-run the installer, or add this as root and try again:
      Defaults:$USER !authenticate"
fi
echo "    ok"

echo "==> Waiting for network"
for i in $(seq 1 30); do
  ping -c1 -W1 archlinux.org &>/dev/null && break
  [ "$i" = 30 ] && die "no network"
  sleep 2
done

echo "==> System update"
sudo pacman -Syu --noconfirm || die "pacman -Syu"

echo "==> AUR helper (yay)"
if ! command -v yay &>/dev/null; then
  sudo pacman -S --needed --noconfirm git base-devel || die "base-devel"
  tmp=$(mktemp -d)
  git clone https://aur.archlinux.org/yay-bin.git "$tmp/yay-bin" || die "clone yay"
  ( cd "$tmp/yay-bin" && makepkg -si --noconfirm ) || die "build yay"
  rm -rf "$tmp"
fi

echo "==> Cloning illogical-impulse"
II="$HOME/dots-hyprland"
if [ -d "$II/.git" ]; then
  git -C "$II" stash -u &>/dev/null || true
  git -C "$II" pull --ff-only || true
else
  git clone --depth 1 https://github.com/end-4/dots-hyprland.git "$II" || die "clone dots-hyprland"
fi

echo "==> Running upstream installer (non-interactive, long)"
cd "$II"
./setup install -f --skip-allgreeting || die "dots-hyprland setup install"

echo "==> Layering the $FORK_NAME Quickshell fork"
mkdir -p "$HOME/.config/quickshell"
FORKDIR="$HOME/.config/quickshell/$FORK_NAME"
if [ -d "$FORKDIR/.git" ]; then
  git -C "$FORKDIR" pull --ff-only || true
else
  git clone "$FORK_REPO" "$FORKDIR" || die "clone $FORK_REPO"
fi

echo "==> Making $FORK_NAME the default shell config"
VARS="$HOME/.config/hypr/hyprland/variables.lua"
if [ -f "$VARS" ]; then
  cp "$VARS" "$VARS.bak.$(date +%s)"
  sed -i "s/hl\.env(\"qsConfig\", \"ii\")/hl.env(\"qsConfig\", \"$FORK_NAME\")/" "$VARS"
  grep -q 'quickshell:settingsToggle' "$VARS" || cat >> "$VARS" <<'EOF'

-- Settings panel (added by automated setup)
hl.bind("SUPER + escape", hl.dsp.global("quickshell:settingsToggle"), {description = "Toggle settings"})
EOF
  echo "    patched $VARS"
else
  echo "    !! $VARS not found - set qsConfig to '$FORK_NAME' manually"
fi

echo "==> QEMU/virtio graphics tuning"
mkdir -p "$HOME/.config/uwsm"
cat > "$HOME/.config/uwsm/env" <<'EOF'
# Running on QEMU virtio-gpu (virgl) - no real GPU passthrough available.
# Do NOT set GALLIUM_DRIVER here: mesa selects virgl automatically via the
# virtio_gpu DRM driver. Forcing "virpipe" picks the vtest backend, which
# expects a virgl_test_server socket and renders badly.
export WLR_NO_HARDWARE_CURSORS=1
export WLR_RENDERER_ALLOW_SOFTWARE=1
export XDG_SESSION_TYPE=wayland
EOF

# Hyprland tuning for a virtual GPU: VFR causes full-screen repaints when the
# compositor wakes from idle, and blur/shadows are costly in software rendering.
mkdir -p "$HOME/.config/hypr/custom"
if [ ! -s "$HOME/.config/hypr/custom/general.lua" ] ||    ! grep -q 'vfr' "$HOME/.config/hypr/custom/general.lua" 2>/dev/null; then
  cat > "$HOME/.config/hypr/custom/general.lua" <<'EOF'
-- QEMU/virtio-gpu tuning (added by automated setup)
hl.config({
    misc = { vfr = false },
    decoration = { blur = { enabled = false }, shadow = { enabled = false } },
})
EOF
fi
grep -q 'WLR_NO_HARDWARE_CURSORS' "$HOME/.profile" 2>/dev/null || \
  echo 'export WLR_NO_HARDWARE_CURSORS=1' >> "$HOME/.profile"
grep -q 'WLR_RENDERER_ALLOW_SOFTWARE' "$HOME/.profile" 2>/dev/null || \
  echo 'export WLR_RENDERER_ALLOW_SOFTWARE=1' >> "$HOME/.profile"

echo "==> Configuring the graphical login"
# sddm and xorg-server came with the base system, so this needs no network.
sudo pacman -S --needed --noconfirm sddm xorg-server || die "sddm"

sudo mkdir -p /etc/sddm.conf.d
sudo tee /etc/sddm.conf.d/10-archvm.conf >/dev/null <<'EOF'
[General]
# The X11 greeter is deliberate: SDDM's Wayland greeter needs its own
# compositor and is markedly less reliable inside a VM.
Numlock=on

[Theme]
Current=breeze
EOF

# Use the session file Hyprland actually installed, so the greeter opens on
# the right entry rather than whatever sorts first.
SESSION=""
for cand in /usr/share/wayland-sessions/hyprland-uwsm.desktop \
            /usr/share/wayland-sessions/hyprland.desktop; do
  [ -f "$cand" ] && SESSION="$cand" && break
done

if [ -z "$SESSION" ]; then
  echo "!! No Hyprland session file found; writing one."
  sudo mkdir -p /usr/share/wayland-sessions
  sudo tee /usr/share/wayland-sessions/hyprland.desktop >/dev/null <<'EOF'
[Desktop Entry]
Name=Hyprland
Comment=Dynamic tiling Wayland compositor
Exec=Hyprland
Type=Application
DesktopNames=Hyprland
EOF
  SESSION=/usr/share/wayland-sessions/hyprland.desktop
fi
echo "    session: $SESSION"

# SDDM preselects whatever it used last; seeding that state means the very
# first greeter already has Hyprland and this account chosen.
sudo mkdir -p /var/lib/sddm
sudo tee /var/lib/sddm/state.conf >/dev/null <<EOF
[Last]
Session=$SESSION
User=$USER
EOF
sudo chown -R sddm:sddm /var/lib/sddm 2>/dev/null || true

echo "==> Switching to graphical boot"
sudo systemctl enable sddm
sudo systemctl set-default graphical.target
# The unattended unit has done its job; stop it claiming tty1 again.
sudo systemctl disable archvm-setup.service 2>/dev/null || true
sudo systemctl enable getty@tty1.service 2>/dev/null || true

echo "==> Revoking temporary passwordless sudo"
sudo rm -f /etc/sudoers.d/99-firstboot-tmp

touch "$HOME/.local/share/hypr-setup-done"

echo
echo "############################################################"
echo "#  Done. Rebooting into the graphical login."
echo "#  Sign in as $USER and pick the Hyprland session."
echo "############################################################"
sleep 5

if [ "${ARCHVM_UNATTENDED:-}" = "1" ]; then
  sudo systemctl reboot
else
  echo "Run 'sudo systemctl reboot' when ready."
fi
