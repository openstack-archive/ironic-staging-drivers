#!/bin/sh

# code from DIB bash ramdisk
readonly target_disk=$1
readonly root_part=$2
readonly root_part_mount=/mnt/rootfs

# We need to run partprobe to ensure all partitions are visible
partprobe $target_disk

mkdir -p $root_part_mount

mount $root_part $root_part_mount
if [ $? != "0" ]; then
   echo "Failed to mount root partition $root_part on $root_part_mount"
   exit 1
fi

mkdir -p $root_part_mount/dev
mkdir -p $root_part_mount/sys
mkdir -p $root_part_mount/proc

mount -o bind /dev $root_part_mount/dev
mount -o bind /sys $root_part_mount/sys
mount -o bind /proc $root_part_mount/proc

# Find grub version
V=
if [ -x $root_part_mount/usr/sbin/grub2-install ]; then
    V=2
fi

# Install grub
ret=1
if chroot $root_part_mount /bin/sh -c "/usr/sbin/grub$V-install ${target_disk}"; then
    echo "Generating the grub configuration file"

    # tell GRUB2 to preload its "lvm" module to gain LVM booting on direct-attached disks
    if [ "$V" = "2" ]; then
        echo "GRUB_PRELOAD_MODULES=lvm" >> $root_part_mount/etc/default/grub
    fi
    chroot $root_part_mount /bin/sh -c "/usr/sbin/grub$V-mkconfig -o /boot/grub$V/grub.cfg"
    ret=$?
fi

umount $root_part_mount/dev
umount $root_part_mount/sys
umount $root_part_mount/proc
umount $root_part_mount

if [ $ret != "0" ]; then
    echo "Installing grub bootloader failed"
fi
exit $ret
