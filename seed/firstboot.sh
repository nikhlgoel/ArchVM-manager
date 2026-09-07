#!/usr/bin/env bash
# Stage 3: runs as the normal user on first login. Installs the desktop.
set -uo pipefail
source "$HOME/.vm.conf"

LOG="$HOME/hypr-install.log"
exec > >(tee -a "$LOG") 2>&1

echo "############################################################"
echo "#  Installing illogical-impulse (Hyprland) + $FORK_NAME"
echo "#  Log: $LOG"
echo "############################################################"

die(){ echo "!! FAILED: $*"; echo "!! Fix, then re-run: ~/firstboot.sh"; exit 1; }

# Self-heal: ensure the whole home tree is ours before anything writes to it.
if [ "$(stat -c %U "$HOME/.local" 2>/dev/null || echo "$USER")" != "$USER" ]; then
  echo "==> Fixing ownership of $HOME"
  sudo chown -R "$USER:$USER" "$HOME"
fi

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
export XDG_SESSION_TYPE=wayland
EOF

# Hyprland tuning for a virtual GPU: VFR causes full-screen repaints when the
# compositor wakes from idle, and blur is costly without DMABUF.
mkdir -p "$HOME/.config/hypr/custom"
if [ ! -s "$HOME/.config/hypr/custom/general.lua" ] ||    ! grep -q 'vfr' "$HOME/.config/hypr/custom/general.lua" 2>/dev/null; then
  cat > "$HOME/.config/hypr/custom/general.lua" <<'EOF'
-- QEMU/virtio-gpu tuning (added by automated setup)
hl.config({
    misc = { vfr = false },
    decoration = { blur = { enabled = false } },
})
EOF
fi
grep -q 'WLR_NO_HARDWARE_CURSORS' "$HOME/.profile" 2>/dev/null || \
  echo 'export WLR_NO_HARDWARE_CURSORS=1' >> "$HOME/.profile"

echo "==> Graphical login (SDDM) so the VM boots into a proper greeter"
# Without this the VM lands on a black TTY and Hyprland must be typed by hand.
# X11 greeter is used deliberately: the Wayland greeter needs a compositor
# (kwin_wayland/weston) and is far more fragile inside a VM.
sudo pacman -S --needed --noconfirm sddm xorg-server || die "sddm"

sudo mkdir -p /etc/sddm.conf.d
sudo tee /etc/sddm.conf.d/10-archvm.conf >/dev/null <<EOF
[Theme]
Current=breeze

[General]
# Hyprland needs a seat; the default is fine but be explicit.
Numlock=on
EOF

# Make sure a Hyprland session entry exists for SDDM to offer.
if [ ! -f /usr/share/wayland-sessions/hyprland.desktop ] &&    [ ! -f /usr/share/wayland-sessions/hyprland-uwsm.desktop ]; then
  sudo mkdir -p /usr/share/wayland-sessions
  sudo tee /usr/share/wayland-sessions/hyprland.desktop >/dev/null <<'EOF'
[Desktop Entry]
Name=Hyprland
Comment=Dynamic tiling Wayland compositor
Exec=Hyprland
Type=Application
EOF
fi

sudo systemctl enable sddm
sudo systemctl set-default graphical.target

echo "==> Revoking temporary passwordless sudo"
sudo rm -f /etc/sudoers.d/99-firstboot-tmp

touch "$HOME/.local/share/hypr-setup-done"
echo
echo "############################################################"
echo "#  DONE. Reboot - SDDM will show a graphical login."
echo "#  Pick the Hyprland session and sign in."
echo "#  Re-run this script any time: ~/firstboot.sh"
echo "############################################################"
