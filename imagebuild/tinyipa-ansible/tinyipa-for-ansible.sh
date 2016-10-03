#!/bin/bash

# NOTE(pas-ha) Apparently on TinyCore Ansible's 'command' module is
# not searching for executables in the '/usr/local/(s)bin' paths.
# This script will rebuilt the tinyipa ramdisk to have everything from there
# symlinked to '/usr/(s)bin' which is being searched,
# so that 'command' module picks full utilities installed by 'util-linux'
# instead of built-in simplified BusyBox ones.

# Script usage:
# ./tinyipa-for-ansible.sh <path-to-tinyipa.gz>
#
# The incoming tinyipa.gz file must have been built with
# "ENABLE_SSH=True" and "PYOPTIMIZE_TINYIPA=False" for the produced image
# to work with ansible-deploy driver.
#
# Produces "tinyipa-ansible.gz" that can serve as ramdisk for both
# ansible-deploy driver and standard, agent-based Ironic drivers.

set -ex
TINYIPA_RAMDISK="$1"
WORKDIR=$(readlink -f $0 | xargs dirname)

FINALDIR="$WORKDIR/tinyipa-ansible"
CHROOT_PATH="/usr/local/sbin:/usr/local/bin:/apps/bin:/usr/sbin:/usr/bin:/sbin:/bin"
CHROOT_CMD="sudo chroot $FINALDIR /usr/bin/env -i PATH=$CHROOT_PATH http_proxy=$http_proxy https_proxy=$https_proxy no_proxy=$no_proxy"

sudo -v

if [ -d "$FINALDIR" ]; then
    sudo rm -rf "$FINALDIR"
fi

mkdir "$FINALDIR"

# Extract rootfs from .gz file
( cd "$FINALDIR" && zcat "$TINYIPA_RAMDISK" | sudo cpio -i -H newc -d )
trap "sudo umount $FINALDIR/proc" EXIT
# Mount /proc for chroot commands
sudo mount --bind /proc "$FINALDIR/proc"

set +e
echo "Symlink all from /usr/local/sbin to /usr/sbin"
cd "$FINALDIR/usr/local/sbin"
for target in *
do
    if [ ! -f "$FINALDIR/usr/sbin/$target" ]
    then
        $CHROOT_CMD ln -s "/usr/local/sbin/$target" "/usr/sbin/$target"
    fi
done
echo "Symlink all from /usr/local/bin to /usr/bin"
# this also includes symlinking Python to the place expected by Ansible
cd "$FINALDIR/usr/local/bin"
for target in *
do
    if [ ! -f "$FINALDIR/usr/bin/$target" ]
    then
        $CHROOT_CMD ln -s "/usr/local/bin/$target" "/usr/bin/$target"
    fi
done
set -e
sudo umount $FINALDIR/proc
trap - EXIT
# Rebuild build directory into gz file
( cd "$FINALDIR" && sudo find | sudo cpio -o -H newc | gzip -9 > "$WORKDIR/tinyipa-ansible.gz" )
