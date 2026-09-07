#!/usr/bin/env bash
# Stage 2: runs inside arch-chroot. System config, user, bootloader.
set -euo pipefail
source /root/seed/vm.conf

echo "==> Timezone / clock"
ln -sf "/usr/share/zoneinfo/$TIMEZONE" /etc/localtime
hwclock --systohc

echo "==> Locale"
# Arch's locale.gen is inconsistent: some entries carry the codeset in the
# name ("#en_US.UTF-8 UTF-8"), others do not ("#en_IN UTF-8"). Match either,
# and always enable en_US.UTF-8 so there is a guaranteed fallback.
LOCALE_BASE="${LOCALE%%.*}"
sed -i -E "s/^#[[:space:]]*(${LOCALE_BASE}(\.UTF-8)?[[:space:]]+UTF-8)[[:space:]]*$/\1/" /etc/locale.gen
sed -i -E "s/^#[[:space:]]*(en_US\.UTF-8[[:space:]]+UTF-8)[[:space:]]*$/\1/" /etc/locale.gen
locale-gen

# Use the requested locale only if it was actually generated.
WANT=$(echo "$LOCALE" | tr 'A-Z' 'a-z' | sed 's/utf-8/utf8/')
if locale -a 2>/dev/null | tr 'A-Z' 'a-z' | grep -qx "$WANT"; then
  EFFECTIVE_LOCALE="$LOCALE"
else
  echo "!! $LOCALE was not generated; falling back to en_US.UTF-8"
  EFFECTIVE_LOCALE="en_US.UTF-8"
fi
echo "LANG=$EFFECTIVE_LOCALE" > /etc/locale.conf
echo "KEYMAP=$KEYMAP" > /etc/vconsole.conf
# Explicit X11/Wayland keymap so Shift+digit symbols map correctly.
mkdir -p /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/00-keyboard.conf <<EOF
Section "InputClass"
    Identifier "system-keyboard"
    MatchIsKeyboard "on"
    Option "XkbLayout" "$KEYMAP"
    Option "XkbModel" "pc105"
EndSection
EOF

echo "==> Hostname"
echo "$HOSTNAME" > /etc/hostname
cat > /etc/hosts <<EOF
127.0.0.1   localhost
::1         localhost
127.0.1.1   $HOSTNAME.localdomain $HOSTNAME
EOF

echo "==> zram swap"
cat > /etc/systemd/zram-generator.conf <<'EOF'
[zram0]
zram-size = ram / 2
compression-algorithm = zstd
EOF

echo "==> Users"
echo "root:$ROOTPASS" | chpasswd
id -u "$USERNAME" &>/dev/null || useradd -m -G wheel -s /bin/bash "$USERNAME"
echo "$USERNAME:$USERPASS" | chpasswd
echo "%wheel ALL=(ALL:ALL) ALL" > /etc/sudoers.d/10-wheel
chmod 440 /etc/sudoers.d/10-wheel

# Temporary passwordless sudo so the first-boot desktop install is unattended.
# firstboot.sh deletes this file when it finishes.
echo "$USERNAME ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/99-firstboot-tmp
chmod 440 /etc/sudoers.d/99-firstboot-tmp

echo "==> initramfs (virtio modules)"
sed -i 's/^MODULES=()/MODULES=(virtio virtio_blk virtio_pci virtio_net virtio_gpu)/' /etc/mkinitcpio.conf
mkinitcpio -P

echo "==> systemd-boot"
bootctl --path=/boot install
ROOT_UUID=$(blkid -s UUID -o value /dev/vda2)
cat > /boot/loader/loader.conf <<'EOF'
default arch.conf
timeout 3
console-mode max
editor no
EOF
cat > /boot/loader/entries/arch.conf <<EOF
title   Arch Linux (Hyprland)
linux   /vmlinuz-linux
initrd  /initramfs-linux.img
options root=UUID=$ROOT_UUID rw
EOF

echo "==> Services"
systemctl enable NetworkManager
systemctl enable qemu-guest-agent
# SSH lets you paste commands in from Windows (host localhost:2222).
systemctl enable sshd
# spice-vdagent gives clipboard sync when a SPICE channel is present.
systemctl enable spice-vdagentd 2>/dev/null || true

echo "==> Staging first-boot desktop installer"
mkdir -p "/home/$USERNAME/.local/share" "/home/$USERNAME/.local/state" "/home/$USERNAME/.config"
# chown the whole tree - "install -d" only owns the final component,
# which left .local root-owned and broke the first-boot install.
chown -R "$USERNAME:$USERNAME" "/home/$USERNAME"
cp /root/seed/firstboot.sh "/home/$USERNAME/firstboot.sh"
cp /root/seed/vm.conf      "/home/$USERNAME/.vm.conf"
chown "$USERNAME:$USERNAME" "/home/$USERNAME/firstboot.sh" "/home/$USERNAME/.vm.conf"
chmod +x "/home/$USERNAME/firstboot.sh"

# Auto-run the desktop install once, on first interactive login.
cat >> "/home/$USERNAME/.bash_profile" <<'EOF'

# --- one-shot desktop install ---
if [ ! -f "$HOME/.local/share/hypr-setup-done" ] && [ -x "$HOME/firstboot.sh" ]; then
  "$HOME/firstboot.sh"
fi
EOF
chown "$USERNAME:$USERNAME" "/home/$USERNAME/.bash_profile"

# Log the user in on tty1 automatically for the next boot only. The desktop
# install is long and unattended; making someone type a password first, at a
# bare TTY, to reach a script that runs by itself is friction for no gain.
# firstboot.sh removes this drop-in when it finishes, so the permanent login
# is SDDM's graphical greeter.
echo "==> Temporary autologin on tty1 (removed after the desktop install)"
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty -o '-p -f -- \u' --noclear --autologin $USERNAME %I \$TERM
EOF

cat > /etc/issue <<'EOF'
Arch Linux \r (\l)

  If the desktop is not installed yet, just log in - the installer
  resumes automatically. To re-run it by hand:  ~/firstboot.sh

EOF

echo "==> Stage 2 complete"
