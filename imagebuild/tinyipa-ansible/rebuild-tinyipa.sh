#!/bin/bash

# Downloads the pre-built tinyipa image from tarballs.openstack.org and
# rebuilds it to be usable with ansible-deploy driver.
#
# During rebuild this script installs and configures OpenSSH server and
# makes required changes for Ansible + Python to work in compiled/optimized
# Python environment.
#
# By default, id_rsa or id_dsa keys  of the user performing the build
# are baked into the image as authorized_keys for 'tc' user.
# To supply different public ssh key, befor running this script set
# SSH_PUBLIC_KEY environment variable to point to absolute path to the key.
# 
# This script produces "tinyipa-$BRANCH_PATH-ansible.gz" that can serve
# as ramdisk for both ansible-deploy driver and agent-based Ironic drivers,
# and a copy of tinyipa-$BRANCH_PATH.vmlinuz for image kernel

set -ex
WORKDIR=$(readlink -f $0 | xargs dirname)
SSH_PUBLIC_KEY=${SSH_PUBLIC_KEY:-}
source ${WORKDIR}/build_files/tc-mirror.sh
TINYCORE_MIRROR_URL=${TINYCORE_MIRROR_URL:-}
BRANCH_PATH=${BRANCH_PATH:-master}

TC=1001
STAFF=50

REBUILDDIR="$WORKDIR/rebuild"
CHROOT_PATH="/usr/local/sbin:/usr/local/bin:/apps/bin:/usr/sbin:/usr/bin:/sbin:/bin"
CHROOT_CMD="sudo chroot $REBUILDDIR /usr/bin/env -i PATH=$CHROOT_PATH http_proxy=$http_proxy https_proxy=$https_proxy no_proxy=$no_proxy"
TC_CHROOT_CMD="sudo chroot --userspec=$TC:$STAFF $REBUILDDIR /usr/bin/env -i PATH=$CHROOT_PATH http_proxy=$http_proxy https_proxy=$https_proxy no_proxy=$no_proxy"

function validate_params {
    echo "Validating location of public SSH key"
    if [ -n "$SSH_PUBLIC_KEY" ]; then
        if [ -r "$SSH_PUBLIC_KEY" ]; then
            _found_ssh_key="$SSH_PUBLIC_KEY"
        fi
    else
        for fmt in rsa dsa; do
            if [ -r "$HOME/.ssh/id_$fmt.pub" ]; then
                _found_ssh_key="$HOME/.ssh/id_$fmt.pub"
                break
            fi
        done
    fi

    if [ -z $_found_ssh_key ]; then
        echo "Failed to find neither provided nor default SSH key"
        exit 1
    fi

    choose_tc_mirror
}

function get_tinyipa {
    mkdir -p $WORKDIR/build_files/cache
    cd $WORKDIR/build_files/cache
    wget -N http://tarballs.openstack.org/ironic-python-agent/tinyipa/files/tinyipa-${BRANCH_PATH}.gz
    TINYIPA_RAMDISK="$WORKDIR/build_files/cache/tinyipa-${BRANCH_PATH}.gz"
}

function unpack_ramdisk {

    if [ -d "$REBUILDDIR" ]; then
        sudo rm -rf "$REBUILDDIR"
    fi

    mkdir -p "$REBUILDDIR"

    # Extract rootfs from .gz file
    ( cd "$REBUILDDIR" && zcat "$TINYIPA_RAMDISK" | sudo cpio -i -H newc -d )

}

function prepare_chroot {
    sudo cp $REBUILDDIR/etc/resolv.conf $REBUILDDIR/etc/resolv.conf.old
    sudo cp /etc/resolv.conf $REBUILDDIR/etc/resolv.conf

    sudo cp -a $REBUILDDIR/opt/tcemirror $REBUILDDIR/opt/tcemirror.old
    sudo sh -c "echo $TINYCORE_MIRROR_URL > $REBUILDDIR/opt/tcemirror"

    mkdir -p $REBUILDDIR/tmp/builtin/optional
    $CHROOT_CMD chown -R tc.staff /tmp/builtin
    $CHROOT_CMD chmod -R a+w /tmp/builtin
    $CHROOT_CMD ln -sf /tmp/builtin /etc/sysconfig/tcedir
    echo "tc" | $CHROOT_CMD tee -a /etc/sysconfig/tcuser
    $CHROOT_CMD mkdir -p /usr/local/tce.installed
    $CHROOT_CMD chmod 777 /usr/local/tce.installed

    mkdir -p $REBUILDDIR/tmp/overides
    sudo cp -f $WORKDIR/build_files/fakeuname $REBUILDDIR/tmp/overides/uname

    trap "sudo umount $REBUILDDIR/proc" EXIT
    # Mount /proc for chroot commands
    sudo mount --bind /proc "$REBUILDDIR/proc"
}

function clean_up_chroot {
    # Unmount /proc and clean up everything
    sudo umount $REBUILDDIR/proc
    # all went well, remove the trap
    trap - EXIT
    sudo rm $REBUILDDIR/etc/sysconfig/tcuser
    sudo rm $REBUILDDIR/etc/sysconfig/tcedir
    sudo rm -rf $REBUILDDIR/usr/local/tce.installed
    sudo rm -rf $REBUILDDIR/tmp/builtin
    sudo rm -rf $REBUILDDIR/tmp/tcloop
    sudo rm -rf $REBUILDDIR/tmp/overrides
    sudo mv $REBUILDDIR/opt/tcemirror.old $REBUILDDIR/opt/tcemirror
    sudo mv $REBUILDDIR/etc/resolv.conf.old $REBUILDDIR/etc/resolv.conf
}

function install_ssh {
    # Install and configure bare minimum for SSH access
    $TC_CHROOT_CMD tce-load -wic openssh
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
    cat $_found_ssh_key | $TC_CHROOT_CMD tee /home/tc/.ssh/authorized_keys
    $CHROOT_CMD chown tc.staff /home/tc/.ssh/authorized_keys
    $TC_CHROOT_CMD chmod 600 /home/tc/.ssh/authorized_keys
}

function fix_python_optimize {
    echo "PYTHONOPTIMIZE=1" | $TC_CHROOT_CMD tee -a /home/tc/.ssh/environment
    echo "PermitUserEnvironment yes" | $CHROOT_CMD tee -a /usr/local/etc/ssh/sshd_config
    echo 'Defaults env_keep += "PYTHONOPTIMIZE"' | $CHROOT_CMD tee -a /etc/sudoers
}

function make_symlinks {

    set +x
    echo "Symlink all from /usr/local/sbin to /usr/sbin"
    cd "$REBUILDDIR/usr/local/sbin"
    for target in *
    do
        if [ ! -f "$REBUILDDIR/usr/sbin/$target" ]
        then
            $CHROOT_CMD ln -s "/usr/local/sbin/$target" "/usr/sbin/$target"
        fi
    done
    echo "Symlink all from /usr/local/bin to /usr/bin"
    # this also includes symlinking Python to the place expected by Ansible
    cd "$REBUILDDIR/usr/local/bin"
    for target in *
    do
        if [ ! -f "$REBUILDDIR/usr/bin/$target" ]
        then
            $CHROOT_CMD ln -s "/usr/local/bin/$target" "/usr/bin/$target"
        fi
    done
    set -x
}

function rebuild_ramdisk {
    # Rebuild build directory into gz file
    ( cd "$REBUILDDIR" && sudo find | sudo cpio -o -H newc | gzip -9 > "$WORKDIR/tinyipa-${BRANCH_PATH}-ansible.gz" )
    # Output files with sizes created by this script
    cd "$WORKDIR"
    wget -N http://tarballs.openstack.org/ironic-python-agent/tinyipa/files/tinyipa-${BRANCH_PATH}.vmlinuz
    echo "Produced files:"
    du -h "tinyipa-${BRANCH_PATH}-ansible.gz" "tinyipa-${BRANCH_PATH}.vmlinuz"
}

sudo -v

validate_params
get_tinyipa
unpack_ramdisk
prepare_chroot

# NOTE (pas-ha) default tinyipa is built without SSH access, enable it here
install_ssh
# NOTE(pas-ha) default tinyipa is built with PYOPTIMIZE_TINYIPA=true and
# for Ansible+python to work we need to ensure that PYTHONOPTIMIZE=1 is
# set for all sessions from 'tc' user including those that are escalated
# with 'sudo' afterwards
fix_python_optimize
# NOTE(pas-ha) Apparently on TinyCore Ansible's 'command' module is
# not searching for executables in the '/usr/local/(s)bin' paths.
# Thus we need to have everything from there symlinked to '/usr/(s)bin'
# which is being searched, so that 'command' module picks full utilities
# installed by 'util-linux' instead of built-in simplified BusyBox ones.
make_symlinks

clean_up_chroot
rebuild_ramdisk
