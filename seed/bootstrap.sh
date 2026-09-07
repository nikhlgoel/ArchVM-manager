#!/usr/bin/env bash
# Stage 1: runs in the Arch live ISO. Partitions, installs base system.
set -euo pipefail

SEED="$(cd "$(dirname "$0")" && pwd)"
source "$SEED/vm.conf"

DISK=/dev/vda

echo "==> Arch + Hyprland automated install"
echo "    target disk: $DISK   user: $USERNAME   host: $HOSTNAME"
echo
lsblk "$DISK" || { echo "ERROR: $DISK not found"; exit 1; }
echo
# AUTO_CONFIRM is set by the setup wizard, where the user has already ticked
# an explicit "this erases the virtual disk" confirmation. Without it we ask.
if [ "${AUTO_CONFIRM:-}" = "yes" ]; then
  echo "Disk wipe confirmed in the setup wizard - continuing."
else
  read -rp "This ERASES $DISK. Type YES to continue: " ok
  [ "$ok" = "YES" ] || { echo "aborted"; exit 1; }
fi

echo "==> Clock + mirrors"
timedatectl set-ntp true || true
pacman -Sy --noconfirm archlinux-keyring || true

echo "==> Partitioning $DISK (GPT: 1G EFI + rest ext4)"
sgdisk --zap-all "$DISK"
sgdisk -n1:0:+1G  -t1:ef00 -c1:EFI  "$DISK"
sgdisk -n2:0:0    -t2:8300 -c2:root "$DISK"
partprobe "$DISK"; sleep 2

mkfs.fat -F32 -n EFI  "${DISK}1"
mkfs.ext4 -F  -L root "${DISK}2"

echo "==> Mounting"
mount "${DISK}2" /mnt
mkdir -p /mnt/boot
mount "${DISK}1" /mnt/boot

echo "==> pacstrap base system (this takes a while)"
pacstrap -K /mnt \
  base base-devel linux linux-firmware \
  networkmanager sudo git curl wget nano vim \
  mesa mesa-utils vulkan-virtio vulkan-icd-loader libva-mesa-driver \
  pipewire pipewire-pulse pipewire-alsa wireplumber \
  zram-generator polkit xdg-user-dirs \
  qemu-guest-agent spice-vdagent openssh wl-clipboard \
  fish reflector man-db

echo "==> fstab"
genfstab -U /mnt >> /mnt/etc/fstab

echo "==> Copying stage 2 + 3 into the new system"
mkdir -p /mnt/root/seed
cp "$SEED"/vm.conf "$SEED"/chroot-setup.sh "$SEED"/firstboot.sh /mnt/root/seed/
chmod +x /mnt/root/seed/*.sh

echo "==> Running stage 2 inside chroot"
arch-chroot /mnt bash /root/seed/chroot-setup.sh

echo
echo "============================================================"
echo " Base install DONE."
echo " Run:  umount -R /mnt && reboot"
echo " Then log in as '$USERNAME' - the desktop install runs"
echo " automatically on first login."
echo "============================================================"
