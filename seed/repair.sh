#!/usr/bin/env bash
# Upgrade an existing ArchVM guest to the unattended first-boot flow.
#
# Run from the Arch live ISO with the VM disk attached:
#     mkdir -p /s && mount /dev/sr1 /s && bash /s/repair.sh
#
# Installs the current firstboot script and the systemd unit that runs it, so
# the machine builds its desktop by itself and ends at a graphical greeter
# instead of a bare console. Safe to run on a finished install: it detects the
# completion marker and only fixes the boot target.
set -euo pipefail

SEED="$(cd "$(dirname "$0")" && pwd)"
source "$SEED/vm.conf"

DISK=${DISK:-/dev/vda}
ROOT_PART="${DISK}2"
EFI_PART="${DISK}1"

echo "==> Mounting $ROOT_PART"
mkdir -p /mnt
mountpoint -q /mnt || mount "$ROOT_PART" /mnt
mkdir -p /mnt/boot
mountpoint -q /mnt/boot || mount "$EFI_PART" /mnt/boot 2>/dev/null || true

HOME_DIR="/mnt/home/$USERNAME"
if [ ! -d "$HOME_DIR" ]; then
  echo "!! No home directory for '$USERNAME' at $HOME_DIR"
  echo "   Users present:"; ls -1 /mnt/home 2>/dev/null || true
  exit 1
fi
UID_N=$(stat -c %u "$HOME_DIR")
GID_N=$(stat -c %g "$HOME_DIR")

echo "==> Installing the current first-boot script"
install -m 0755 -o "$UID_N" -g "$GID_N" "$SEED/firstboot.sh" "$HOME_DIR/firstboot.sh"
install -m 0644 -o "$UID_N" -g "$GID_N" "$SEED/vm.conf" "$HOME_DIR/.vm.conf"

echo "==> Installing the unattended first-boot unit"
cat > /mnt/etc/systemd/system/archvm-setup.service <<EOF
[Unit]
Description=ArchVM first-boot desktop installation
After=network-online.target systemd-user-sessions.service
Wants=network-online.target
Conflicts=getty@tty1.service
Before=getty@tty1.service
ConditionPathExists=!/home/$USERNAME/.local/share/hypr-setup-done

[Service]
Type=oneshot
User=$USERNAME
Group=$USERNAME
WorkingDirectory=/home/$USERNAME
Environment=HOME=/home/$USERNAME
Environment=TERM=linux
Environment=ARCHVM_UNATTENDED=1
ExecStart=/home/$USERNAME/firstboot.sh
StandardInput=tty
StandardOutput=tty
StandardError=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
TimeoutStartSec=infinity
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

echo "==> Making the boot visible (dropping 'quiet')"
for f in /mnt/boot/loader/entries/*.conf; do
  [ -f "$f" ] || continue
  sed -i 's/[[:space:]]*\bquiet\b//g' "$f"
done

cat > /mnt/etc/issue <<'EOF'
Arch Linux \r (\l)

  If the desktop is not installed yet, just log in - the installer
  resumes automatically. To re-run it by hand:  ~/firstboot.sh

EOF

if [ -f "$HOME_DIR/.local/share/hypr-setup-done" ]; then
  echo "==> Desktop already installed; enabling the graphical target only"
  systemctl --root=/mnt enable sddm.service 2>/dev/null || true
  systemctl --root=/mnt set-default graphical.target
else
  echo "==> Desktop not finished; enabling the unattended installer"
  systemctl --root=/mnt enable archvm-setup.service
  systemctl --root=/mnt set-default multi-user.target
  # The build needs unattended sudo; firstboot removes this when it finishes.
  cat > /mnt/etc/sudoers.d/99-firstboot-tmp <<EOF
# Temporary, removed by firstboot.sh when the desktop build finishes.
# !authenticate is deliberate: makepkg calls sudo with --preserve-env, which a
# bare NOPASSWD rule does not cover, and the build then stops on a hidden
# password prompt.
Defaults:$USERNAME !authenticate
$USERNAME ALL=(ALL:ALL) NOPASSWD: SETENV: ALL
EOF
  chmod 440 /mnt/etc/sudoers.d/99-firstboot-tmp
fi

sync
umount -R /mnt 2>/dev/null || true

echo
echo "============================================================"
echo " Repair complete. Power the VM off, detach the installer,"
echo " and start it normally - the desktop build runs by itself."
echo "============================================================"
