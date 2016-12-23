#!/bin/bash
# plugin.sh - devstack plugin for ironic-staging-drivers

IRONIC_STAGING_DRIVERS_DIR=$DEST/ironic-staging-drivers
IRONIC_DRIVERS_EXCLUDED_DIRS='tests common'
IRONIC_STAGING_DRIVER=${IRONIC_STAGING_DRIVER:-}

function update_ironic_enabled_drivers {
    local saveIFS
    saveIFS=$IFS
    IFS=","
    while read driver; do
        if [[ ! $IRONIC_ENABLED_DRIVERS =~ $(echo "\<$driver\>") ]]; then
           if [[ -z "$IRONIC_ENABLED_DRIVERS" ]]; then
               IRONIC_ENABLED_DRIVERS="$driver"
           else
               IRONIC_ENABLED_DRIVERS+=",$driver"
           fi
        fi
    done < $IRONIC_STAGING_DRIVERS_DIR/devstack/enabled-drivers.txt
    IFS=$saveIFS
    # NOTE(vsaienko) if ironic-staging-drivers are called after ironic
    # setting IRONIC_ENABLED_DRIVERS will not take affect. Update ironic
    # configuration explicitly.
    iniset $IRONIC_CONF_FILE DEFAULT enabled_drivers "$IRONIC_ENABLED_DRIVERS"
}

function install_ironic_staging_drivers {
    setup_develop $IRONIC_STAGING_DRIVERS_DIR
}

function install_drivers_dependencies {
    local p_deps
    local o_deps
    for path in $IRONIC_STAGING_DRIVERS_DIR/ironic_staging_drivers/*; do
        driver=$(basename $path)
        if [[ -d $path && ! "$IRONIC_DRIVERS_EXCLUDED_DIRS" =~ "$driver" ]]; then
            p_deps=${IRONIC_STAGING_DRIVERS_DIR}/ironic_staging_drivers/${driver}/python-requirements.txt
            o_deps=${IRONIC_STAGING_DRIVERS_DIR}/ironic_staging_drivers/${driver}/other-requirements.sh
            if [[ -f "$p_deps" ]]; then
               echo_summary "Installing $driver python dependencies"
               pip_install -r $p_deps
            fi
            if [[ -f "$o_deps" ]]; then
               echo_summary "Installing $driver other dependencies"
               source $o_deps
            fi
        fi
    done
}

function set_ironic_testing_driver {
    if [[ "$IRONIC_STAGING_DRIVER" == "pxe_ipmitool_ansible" && \
          "$IRONIC_DEPLOY_DRIVER" == "agent_ipmitool" && \
          "$IRONIC_RAMDISK_TYPE" == "tinyipa" ]]; then
        echo_summary "Setting nodes to use ${IRONIC_STAGING_DRIVER} driver"
        set_ansible_deploy_driver
    fi
}

function set_ansible_deploy_driver {
    local tinyipa_ramdisk_name
    local ansible_key_file
    local ansible_ramdisk_id

    # ensure the tinyipa ramdisk is present in Glance
    tinyipa_ramdisk_name=$(openstack --os-cloud devstack-admin image show ${IRONIC_DEPLOY_RAMDISK_ID} -f value -c name)
    if [ -z $tinyipa_ramdisk_name ]; then
        die $LINENO "Failed to find ironic deploy ramdisk ${IRONIC_DEPLOY_RAMDISK_ID}"
    fi

    cd $IRONIC_STAGING_DRIVERS_DIR/imagebuild/tinyipa-ansible
    # download original tinyipa ramdisk from Glance
    openstack --os-cloud devstack-admin image save ${IRONIC_DEPLOY_RAMDISK_ID} --file ${tinyipa_ramdisk_name}
    export TINYIPA_RAMDISK_FILE="${PWD}/${tinyipa_ramdisk_name}"
    # generate SSH keys for deploy ramdisk and ansible driver
    mkdir -p ${IRONIC_DATA_DIR}/ssh_keys
    ansible_key_file="${IRONIC_DATA_DIR}/ssh_keys/ansible_key"
    ssh-keygen -q -t rsa -N "" -f ${ansible_key_file}
    export SSH_PUBLIC_KEY=${ansible_key_file}.pub
    # rebuild ramdisk, produces ansible-${tinyipa_ramdisk_name} file
    make
    # upload rebuilt ramdisk to Glance
    ansible_ramdisk_id=$(openstack --os-cloud devstack-admin image create "ansible-${tinyipa_ramdisk_name}" \
        --file "${PWD}/ansible-${tinyipa_ramdisk_name}" \
        --disk-format ari --container-format ari \
        --public \
        -f value -c id)

    # set nodes to use ansible_deploy driver with uploaded ramdisk
    # using pxe_ipmitool_ansible instead of agent_ipmitool
    for node in $(openstack --os-cloud devstack baremetal node list -f value -c UUID); do
        openstack --os-cloud devstack-admin baremetal node set $node \
            --driver ${IRONIC_STAGING_DRIVER} \
            --driver-info deploy_ramdisk=$ansible_ramdisk_id \
            --driver-info ansible_deploy_username=tc \
            --driver-info ansible_deploy_key_file=$ansible_key_file
    done
    # TODO(pas-ha) setup logging ansible callback plugin to log to specific file
    # for now all ansible logs are seen in ir-cond logs when run in debug logging mode
    # as stdout returned by processutils.execute
}

echo_summary "ironic-staging-drivers plugin.sh was called..."

if is_service_enabled ir-api ir-cond; then
    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        echo_summary "Installing Ironic-staging-drivers"
        install_ironic_staging_drivers
        install_drivers_dependencies

    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        echo_summary "Configuring Ironic-staging-drivers"
        update_ironic_enabled_drivers
    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        if [ -n $IRONIC_STAGING_DRIVER ]; then
            set_ironic_testing_driver
        fi
    fi
fi
