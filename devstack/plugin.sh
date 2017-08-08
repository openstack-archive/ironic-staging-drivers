#!/bin/bash
# plugin.sh - devstack plugin for ironic-staging-drivers

IRONIC_STAGING_DRIVERS_DIR=$DEST/ironic-staging-drivers
IRONIC_DRIVERS_EXCLUDED_DIRS='tests common'
IRONIC_STAGING_DRIVER=${IRONIC_STAGING_DRIVER:-}
# NOTE(pas-ha) skip iboot drivers by default as they require package not available on PyPI
IRONIC_STAGING_DRIVERS_SKIPS=${IRONIC_STAGING_DRIVERS_SKIPS:-"iboot"}
IRONIC_STAGING_DRIVERS_FILTERS=${IRONIC_STAGING_DRIVERS_FILTERS:-}
IRONIC_STAGING_LIST_EP_CMD="$PYTHON $IRONIC_STAGING_DRIVERS_DIR/tools/list-package-entrypoints.py ironic-staging-drivers"
if [[ -n "$IRONIC_STAGING_DRIVERS_SKIPS" ]]; then
    IRONIC_STAGING_LIST_EP_CMD+=" -s $IRONIC_STAGING_DRIVERS_SKIPS"
fi
if [[ -n "$IRONIC_STAGING_DRIVERS_FILTERS" ]]; then
    IRONIC_STAGING_LIST_EP_CMD+=" -f $IRONIC_STAGING_DRIVERS_FILTERS"
fi

IRONIC_STAGING_INTERFACE_TYPES="boot deploy power management console inspect raid vendor storage network"
# these are copied from ironic's code as ironic's devstack plugin does not
# have defaults for them
# TODO(pas-ha) propose using explicit defaults to ironic's devstack plugin
IRONIC_STAGING_DEFAULT_POWER_INTERFACES="ipmitool"
IRONIC_STAGING_DEFAULT_BOOT_INTERFACES="pxe"
IRONIC_STAGING_DEFAULT_MANAGEMENT_INTERFACES="ipmitool"
IRONIC_STAGING_DEFAULT_DEPLOY_INTERFACES="iscsi,direct"
IRONIC_STAGING_DEFAULT_CONSOLE_INTERFACES="no-console"
IRONIC_STAGING_DEFAULT_INSPECT_INTERFACES="no-inspect"
IRONIC_STAGING_DEFAULT_RAID_INTERFACES="agent,no-raid"
IRONIC_STAGING_DEFAULT_VENDOR_INTERFACES="ipmitool,no-vendor"
IRONIC_STAGING_DEFAULT_STORAGE_INTERFACES="cider,noop"
IRONIC_STAGING_DEFAULT_NETWORK_INTERFACES="flat,noop"

function setup_ironic_enabled_interfaces_for {

    local iface=$1
    local iface_var=$(echo $iface | tr '[:lower:]' '[:upper:]')
    local ironic_iface_var="IRONIC_ENABLED_${iface_var}_INTERFACES"
    local implicit_defaults_var="IRONIC_STAGING_DEFAULT_${iface_var}_INTERFACES"
    local enabled_ifs
    local staging_ifs=$($IRONIC_STAGING_LIST_EP_CMD -t ironic.hardware.interfaces.${iface})

    if [[ -n ${staging_ifs} ]]; then
        if [[ -z "${!ironic_iface_var}" ]]; then
            enabled_ifs="${!implicit_defaults_var}"
        else
            enabled_ifs="${!ironic_iface_var}"
        fi
        # NOTE(pas-ha) need fake management interface enabled for staging-wol hw type
        if [[ $iface == 'management' ]]; then
            enabled_ifs+=",fake"
        fi
        iniset $IRONIC_CONF_FILE DEFAULT "enabled_${iface}_interfaces" "$enabled_ifs,$staging_ifs"
    fi
}

function update_ironic_enabled_drivers {
    # NOTE(pas-ha) not carying about possible duplicates any more,
    #              as it was fixed in ironic already
    # NOTE(vsaienko) if ironic-staging-drivers are called after ironic
    # setting IRONIC_ENABLED_* will not take affect. Update ironic
    # configuration explicitly for each option.
    local staging_hw_types

    # hardware types
    staging_hw_types=$($IRONIC_STAGING_LIST_EP_CMD -t ironic.hardware.types)
    if [[ -z "$IRONIC_ENABLED_HARDWARE_TYPES" ]]; then
        IRONIC_ENABLED_HARDWARE_TYPES="$staging_hw_types"
    else
        IRONIC_ENABLED_HARDWARE_TYPES+=",$staging_hw_types"
    fi
    iniset $IRONIC_CONF_FILE DEFAULT enabled_hardware_types "$IRONIC_ENABLED_HARDWARE_TYPES"

    # NOTE(pas-ha) find and enable any type of ironic hardware interface
    # registered by ironic-staging-drivers package (minding skips and filters)
    for i in $IRONIC_STAGING_INTERFACE_TYPES; do
        setup_ironic_enabled_interfaces_for $i
    done
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
    if [[ "$IRONIC_STAGING_DRIVER" =~ "ansible" && \
          "$IRONIC_STAGING_DRIVER" =~ "ipmi" && \
          "$IRONIC_DEPLOY_DRIVER" == "agent_ipmitool" && \
          "$IRONIC_RAMDISK_TYPE" == "tinyipa" ]]; then
        echo_summary "Setting nodes to use 'staging-ansible-ipmi' hardware type with 'staging-ansible' deploy interface"
        set_ansible_deploy_driver
    else
        die $LINENO "Failed to configure ironic to use ${IRONIC_STAGING_DRIVER} driver/hw type: not supported by devstack plugin or other pre-conditions not met"
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

    for node in $(openstack --os-cloud devstack baremetal node list -f value -c UUID); do
        openstack --os-cloud devstack-admin baremetal node maintenance set $node
        # switch driver to ansible-enabled hardware type, use minimal API version that supports setting driver interfaces
        # TODO(pas-ha) remove API version when OSC defaults to 'latest'
        openstack --os-cloud devstack-admin --os-baremetal-api-version 1.31 baremetal node set $node \
             --driver staging-ansible-ipmi \
             --deploy-interface staging-ansible \
             --driver-info deploy_ramdisk=$ansible_ramdisk_id \
             --driver-info ansible_deploy_username=tc \
             --driver-info ansible_deploy_key_file=$ansible_key_file
        # set nodes to use the uploaded ramdisk and appropriate SSH creds
        openstack --os-cloud devstack-admin baremetal node maintenance unset $node
    done

    # set logging for ansible-deploy
    # NOTE(ps-ha) we can do it this late as this config is read by our custom Ansible callback plugin only
    # NOTE(pas-ha) w/o systemd or syslog, there will be no output of single
    # ansible tasks to ironic log, only in the stdout returned by processutils
    if [[ "$USE_SYSTEMD" == "True" ]]; then
        iniset $IRONIC_STAGING_DRIVERS_DIR/ironic_staging_drivers/ansible/playbooks/callback_plugins/ironic_log.ini ironic use_journal "True"
    elif [[ "$SYSLOG" == "True" ]]; then
        iniset $IRONIC_STAGING_DRIVERS_DIR/ironic_staging_drivers/ansible/playbooks/callback_plugins/ironic_log.ini ironic use_syslog "True"
    fi
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
        if [[ -n ${IRONIC_STAGING_DRIVER} ]]; then
            set_ironic_testing_driver
        fi
    fi
fi
