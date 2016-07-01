#!/bin/bash

set -ex

TINYCORE_MIRROR_URL=${TINYCORE_MIRROR_URL-"http://repo.tinycorelinux.net/"}
IRSIBLE_FOR_ANSIBLE=${IRSIBLE_FOR_ANSIBLE:-true}
IRSIBLE_FOR_IRONIC=${IRSIBLE_FOR_IRONIC:-true}

if [ "$IRSIBLE_FOR_ANSIBLE" = false ]; then
    IRSIBLE_FOR_IRONIC=false
fi

if [ "$IRSIBLE_FOR_IRONIC" = true ]; then
    IRSIBLE_FOR_ANSIBLE=true
fi

WORKDIR=$(readlink -f $0 | xargs dirname)
BUILDDIR="$WORKDIR/build"

TC=1001
STAFF=50

CHROOT_PATH="/tmp/overides:/usr/local/sbin:/usr/local/bin:/apps/bin:/usr/sbin:/usr/bin:/sbin:/bin"
CHROOT_CMD="sudo chroot $BUILDDIR /usr/bin/env -i PATH=$CHROOT_PATH http_proxy=$http_proxy https_proxy=$https_proxy no_proxy=$no_proxy"
TC_CHROOT_CMD="sudo chroot --userspec=$TC:$STAFF $BUILDDIR /usr/bin/env -i PATH=$CHROOT_PATH http_proxy=$http_proxy https_proxy=$https_proxy no_proxy=$no_proxy"

echo "Building irsible:"

# Ensure we have an extended sudo to prevent the need to enter a password over
# and over again.
sudo -v

# If an old build directory exists remove it
if [ -d "$BUILDDIR" ]; then
    sudo rm -rf "$BUILDDIR"
fi

##############################################
# Download and Cache Tiny Core Files
##############################################

cd $WORKDIR/build_files
wget -N $TINYCORE_MIRROR_URL/7.x/x86_64/release/distribution_files/corepure64.gz
wget -N $TINYCORE_MIRROR_URL/7.x/x86_64/release/distribution_files/vmlinuz64
cd $WORKDIR

# Finish here if not building for Ironic's ansible-deploy
if [ "$IRSIBLE_FOR_ANSIBLE" = false ]; then
    echo "Not building any extra packages"
    exit 0
fi

########################################################
# Build Required Dependecies in a Build Directory
########################################################

# Make directory for building in
mkdir "$BUILDDIR"

# Extract rootfs from .gz file
( cd "$BUILDDIR" && zcat $WORKDIR/build_files/corepure64.gz | sudo cpio -i -H newc -d )

# Download Qemu-utils source
git clone git://git.qemu-project.org/qemu.git $BUILDDIR/tmp/qemu --depth=1 --branch v2.5.1

# Configure mirror
sudo sh -c "echo $TINYCORE_MIRROR_URL > $BUILDDIR/opt/tcemirror"

sudo cp /etc/resolv.conf $BUILDDIR/etc/resolv.conf

trap "sudo umount $BUILDDIR/proc; sudo umount $BUILDDIR/dev/pts" EXIT
sudo mount --bind /proc $BUILDDIR/proc
sudo mount --bind /dev/pts $BUILDDIR/dev/pts

$CHROOT_CMD mkdir /etc/sysconfig/tcedir
$CHROOT_CMD chmod a+rwx /etc/sysconfig/tcedir
$CHROOT_CMD touch /etc/sysconfig/tcuser
$CHROOT_CMD chmod a+rwx /etc/sysconfig/tcuser

mkdir $BUILDDIR/tmp/overides
cp $WORKDIR/build_files/fakeuname $BUILDDIR/tmp/overides/uname

while read line; do
    $TC_CHROOT_CMD tce-load -wci $line
done < $WORKDIR/build_files/buildreqs.lst

# Build qemu-utils
rm -rf $WORKDIR/build_files/qemu-utils.tcz
$CHROOT_CMD /bin/sh -c "cd /tmp/qemu && ./configure --disable-system --disable-user --disable-linux-user --disable-bsd-user --disable-guest-agent && make && make install DESTDIR=/tmp/qemu-utils"
cd $WORKDIR/build_files && mksquashfs $BUILDDIR/tmp/qemu-utils qemu-utils.tcz && md5sum qemu-utils.tcz > qemu-utils.tcz.md5.txt
# Create qemu-utils.tcz.dep
echo "glib2.tcz" > qemu-utils.tcz.dep

# Build python wheels for dependencies
cd "$BUILDDIR/tmp"
wget https://bootstrap.pypa.io/get-pip.py
$CHROOT_CMD python /tmp/get-pip.py
#$CHROOT_CMD pip install pbr
cp $WORKDIR/build_files/requirements.txt $BUILDDIR/tmp/requirements.txt
$CHROOT_CMD pip wheel --wheel-dir /tmp/wheels setuptools
$CHROOT_CMD pip wheel --wheel-dir /tmp/wheels pip
$CHROOT_CMD pip wheel --pre --wheel-dir /tmp/wheels -r /tmp/requirements.txt
