#!/bin/bash

set -ex

TINYCORE_MIRROR_URL=${TINYCORE_MIRROR_URL-"http://repo.tinycorelinux.net/"}
IRSIBLE_FOR_ANSIBLE=${IRSIBLE_FOR_ANSIBLE:-true}
IRSIBLE_FOR_IRONIC=${IRSIBLE_FOR_IRONIC:-true}
IRSIBLE_SSH_KEY=${IRSIBLE_SSH_KEY:-}

if [ "$IRSIBLE_FOR_ANSIBLE" = false ]; then
    IRSIBLE_FOR_IRONIC=false
fi

if [ "$IRSIBLE_FOR_IRONIC" = true ]; then
    IRSIBLE_FOR_ANSIBLE=true
fi

WORKDIR=$(readlink -f $0 | xargs dirname)
BUILDDIR="$WORKDIR/build"
FINALDIR="$WORKDIR/final"

TC=1001
STAFF=50

CHROOT_PATH="/tmp/overides:/usr/local/sbin:/usr/local/bin:/apps/bin:/usr/sbin:/usr/bin:/sbin:/bin"
CHROOT_CMD="sudo chroot $FINALDIR /usr/bin/env -i PATH=$CHROOT_PATH http_proxy=$http_proxy https_proxy=$https_proxy no_proxy=$no_proxy"
TC_CHROOT_CMD="sudo chroot --userspec=$TC:$STAFF $FINALDIR /usr/bin/env -i PATH=$CHROOT_PATH http_proxy=$http_proxy https_proxy=$https_proxy no_proxy=$no_proxy"

echo "Finalising irsible:"

cd $WORKDIR

sudo -v

if [ -d "$FINALDIR" ]; then
    sudo rm -rf "$FINALDIR"
fi

mkdir "$FINALDIR"

# Extract rootfs from .gz file
( cd "$FINALDIR" && zcat $WORKDIR/build_files/corepure64.gz | sudo cpio -i -H newc -d )

#####################################
# Setup Final Dir
#####################################

sudo cp $FINALDIR/etc/resolv.conf $FINALDIR/etc/resolv.conf.old
sudo cp /etc/resolv.conf $FINALDIR/etc/resolv.conf

sudo cp -a $FINALDIR/opt/tcemirror $FINALDIR/opt/tcemirror.old
sudo sh -c "echo $TINYCORE_MIRROR_URL > $FINALDIR/opt/tcemirror"

# Modify ldconfig for x86-64
$CHROOT_CMD cp /sbin/ldconfig /sbin/ldconfigold
printf '/sbin/ldconfigold $@ | sed "s/unknown/libc6,x86-64/"' | $CHROOT_CMD tee -a /sbin/ldconfignew
$CHROOT_CMD cp /sbin/ldconfignew /sbin/ldconfig
$CHROOT_CMD chmod u+x /sbin/ldconfig

mkdir -p $FINALDIR/tmp/builtin/optional
$CHROOT_CMD chown -R tc.staff /tmp/builtin
$CHROOT_CMD chmod -R a+w /tmp/builtin
$CHROOT_CMD ln -sf /tmp/builtin /etc/sysconfig/tcedir
echo "tc" | $CHROOT_CMD tee -a /etc/sysconfig/tcuser

# Mount /proc for chroot commands
sudo mount --bind /proc $FINALDIR/proc
# Fake uname to get correct dependencies
mkdir $FINALDIR/tmp/overides
cp $WORKDIR/build_files/fakeuname $FINALDIR/tmp/overides/uname

# Install and configure bare minimum for SSH access
$TC_CHROOT_CMD tce-load -wi openssh
# Configure OpenSSH
$CHROOT_CMD cp /usr/local/etc/ssh/sshd_config.orig /usr/local/etc/ssh/sshd_config
echo "PasswordAuthentication no" | $CHROOT_CMD tee -a /usr/local/etc/ssh/sshd_config
# Generate and configure host keys - RSA, DSA, Ed25519
# NOTE(pas-ha) ECDSA host key will still be re-generated fresh on every image boot
$CHROOT_CMD ssh-keygen -t rsa -N "" -f /usr/local/etc/ssh/ssh_host_rsa_key
$CHROOT_CMD ssh-keygen -t dsa -N "" -f /usr/local/etc/ssh/ssh_host_dsa_key
$CHROOT_CMD ssh-keygen -t ed25519 -N "" -f /usr/local/etc/ssh/ssh_host_ed25519_key
echo "HostKey /usr/local/etc/ssh/ssh_host_rsa_key" | $CHROOT_CMD tee -a /usr/local/etc/ssh/sshd_config
echo "HostKey /usr/local/etc/ssh/ssh_host_dsa_key" | $CHROOT_CMD tee -a /usr/local/etc/ssh/sshd_config
echo "HostKey /usr/local/etc/ssh/ssh_host_ed25519_key" | $CHROOT_CMD tee -a /usr/local/etc/ssh/sshd_config

# setup user and SSH keys
$CHROOT_CMD mkdir -p /home/tc
$CHROOT_CMD chown -R tc.staff /home/tc
$TC_CHROOT_CMD mkdir -p /home/tc/.ssh
if [ -n "$IRSIBLE_SSH_KEY" ]; then
    if [ -f "$IRSIBLE_SSH_KEY" ]; then
        cat $IRSIBLE_SSH_KEY | $TC_CHROOT_CMD tee /home/tc/.ssh/authorized_keys
    fi
else
    for fmt in rsa dsa; do
        if [ -f "$HOME/.ssh/id_$fmt.pub" ]; then
            cat $HOME/.ssh/id_$fmt.pub | $TC_CHROOT_CMD tee /home/tc/.ssh/authorized_keys
            break
        fi
    done
fi
$CHROOT_CMD chown tc.staff /home/tc/.ssh/authorized_keys
$TC_CHROOT_CMD chmod 600 /home/tc/.ssh/authorized_keys 

if [ "$IRSIBLE_FOR_ANSIBLE" = true ]; then
    # install Python
    $TC_CHROOT_CMD tce-load -wi python
    # Symlink Python to place expected by Ansible by default
    $CHROOT_CMD ln -s /usr/local/bin/python /usr/bin/python
    if [ "$IRSIBLE_FOR_IRONIC" = true ]; then
        # install other packages
        while read line; do
            $TC_CHROOT_CMD tce-load -wi $line
        done < $WORKDIR/build_files/finalreqs.lst
        # install compiled qemu-utils
        cp $WORKDIR/build_files/qemu-utils.* $FINALDIR/tmp/builtin/optional
        echo "qemu-utils.tcz" | $TC_CHROOT_CMD tee -a /tmp/builtin/onboot.lst

        # Ensure tinyipa picks up installed kernel modules
        $CHROOT_CMD depmod -a `$WORKDIR/build_files/fakeuname -r`

        # Install Python dependencies
        # Download pip bootstrap
        cd "$FINALDIR/tmp"
        wget https://bootstrap.pypa.io/get-pip.py
        # Copy python wheels from build to final dir
        cp -Rp "$BUILDDIR/tmp/wheels" "$FINALDIR/tmp/wheelhouse"
        # Copy python requirements file
        cp $WORKDIR/build_files/requirements.txt $FINALDIR/tmp/requirements.txt
        # install python requirements
        $CHROOT_CMD python /tmp/get-pip.py --no-wheel --no-index --find-links=file:///tmp/wheelhouse -r /tmp/requirements.txt
        # cleanup pip and wheels
        rm -rf $FINALDIR/tmp/wheelhouse
        rm -rf $FINALDIR/tmp/get-pip.py
        rm -rf $FINALDIR/tmp/requirements.txt
        # Uninstall pip and setuptools
        $CHROOT_CMD pip uninstall -y pip setuptools
        # Byte-compile all site-packages
        set +e
        $CHROOT_CMD python -m compileall /usr/local/lib/python2.7/site-packages
        set -e
        find $FINALDIR/usr/local/lib/python2.7/site-packages -name "*.py" | sudo xargs rm
    fi

    # NOTE(pas-ha) Apparently on TC Ansible is not searching for 
    # executables in the /usr/local/sbin path
    # Symlink everything from there to /usr/sbin which is being searched
    cd $FINALDIR/usr/local/sbin
    for target in *
    do
        if [ ! -f "$FINALDIR/usr/sbin/$target" ]
        then
            $CHROOT_CMD ln -s "/usr/local/sbin/$target" "/usr/sbin/$target"
        fi
    done
fi

# Unmount /proc and clean up everything
sudo umount $FINALDIR/proc
sudo umount $FINALDIR/tmp/tcloop/*
sudo rm -rf $FINALDIR/tmp/tcloop
sudo rm -rf $FINALDIR/usr/local/tce.installed
sudo mv $FINALDIR/etc/resolv.conf.old $FINALDIR/etc/resolv.conf
sudo mv $FINALDIR/opt/tcemirror.old $FINALDIR/opt/tcemirror
sudo rm $FINALDIR/etc/sysconfig/tcuser
sudo rm $FINALDIR/etc/sysconfig/tcedir
sudo rm -rf $FINALDIR/tmp/overides

# Copy bootlocal.sh to opt
sudo cp "$WORKDIR/build_files/bootlocal.sh" "$FINALDIR/opt/."

if [ "$IRSIBLE_FOR_IRONIC" ]; then
    # Copy and register Ansible callback
    sudo cp "$WORKDIR/build_files/callback.py" "$FINALDIR/opt/."
    echo "# Run Ansible callback" | $CHROOT_CMD tee -a /opt/bootlocal.sh
    echo "python /opt/callback.py" | $CHROOT_CMD tee -a /opt/bootlocal.sh
fi

# Disable ZSwap
sudo sed -i '/# Main/a NOZSWAP=1' "$FINALDIR/etc/init.d/tc-config"


###############################
# Pack everything back to image
###############################

# Allow an extension to be added to the generated files by specifying
# $BRANCH_PATH e.g. export BRANCH_PATH=master results in irsible-master.gz etc
branch_ext=''
if [ -n "$BRANCH_PATH" ]; then
    branch_ext="-$BRANCH_PATH"
fi

# Rebuild build directory into gz file
( cd "$FINALDIR" && sudo find | sudo cpio -o -H newc | gzip -9 > "$WORKDIR/irsible${branch_ext}.gz" )

# Copy vmlinuz to new name
cp "$WORKDIR/build_files/vmlinuz64" "$WORKDIR/irsible${branch_ext}.vmlinuz"

# Create tar.gz containing irsible files
cd $WORKDIR
tar czf irsible${branch_ext}.tar.gz irsible${branch_ext}.gz irsible${branch_ext}.vmlinuz
echo "Produced files:"
du -h irsible${branch_ext}.tar.gz irsible${branch_ext}.gz irsible${branch_ext}.vmlinuz
