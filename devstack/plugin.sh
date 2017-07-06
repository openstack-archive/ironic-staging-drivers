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
    IRONIC_STAGING_LIST_EP_CMD+="-s $IRONIC_STAGING_DRIVERS_SKIPS"
fi
if [[ -n "$IRONIC_STAGING_DRIVERS_FILTERS" ]]; then
    IRONIC_STAGING_LIST_EP_CMD+="-f $IRONIC_STAGING_DRIVERS_FILTERS"
fi


function update_ironic_enabled_drivers {
    # NOTE(pas-ha) ironic-staging-drivers currently export only below types
    #              of interfaces.
    # ADD NEW ONES IF ADDED TO THE CODE TO TEST THAT THEY ARE STARTING!
    # TODO(pas-ha) refactor and try to set any type of interfaces if found
    # NOTE(pas-ha) not carying about possible duplicates any more,
    #              as it was fixed in ironic already
    # NOTE(vsaienko) if ironic-staging-drivers are called after ironic
    # setting IRONIC_ENABLED_* will not take affect. Update ironic
    # configuration explicitly for each option.
    local staging_drivers
    local staging_hw_types
    local staging_power_ifs
    local staging_mgmt_ifs
    local staging_vendor_ifs
    local staging_deploy_ifs

    # TODO(pas-ha) remove setting classic drivers after ansible job is switched
    #              to use staging-ansible-ipmi dynamic driver
    # classic drivers
    staging_drivers=$($IRONIC_STAGING_LIST_EP_CMD -t ironic.drivers)
    if [[ -z "$IRONIC_ENABLED_DRIVERS" ]]; then
        IRONIC_ENABLED_DRIVERS="$staging_drivers"
    else
        IRONIC_ENABLED_DRIVERS+=",$staging_drivers"
    fi
    iniset $IRONIC_CONF_FILE DEFAULT enabled_drivers "$IRONIC_ENABLED_DRIVERS"

    # hardware types
    staging_hw_types=$($IRONIC_STAGING_LIST_EP_CMD -t ironic.hardware.types)
    if [[ -z "$IRONIC_ENABLED_HARDWARE_TYPES" ]]; then
        IRONIC_ENABLED_HARDWARE_TYPES="$staging_hw_types"
    else
        IRONIC_ENABLED_HARDWARE_TYPES+=",$staging_hw_types"
    fi
    iniset $IRONIC_CONF_FILE DEFAULT enabled_hardware_types "$IRONIC_ENABLED_HARDWARE_TYPES"

    # power interfaces
    staging_power_ifs=$($IRONIC_STAGING_LIST_EP_CMD -t ironic.hardware.interfaces.power)
    if [[ -z "$IRONIC_ENABLED_POWER_INTERFACES" ]]; then
        # NOTE(pas-ha) implict default is ipmitool
        IRONIC_ENABLED_POWER_INTERFACES="ipmitool,$staging_power_ifs"
    else
        IRONIC_ENABLED_POWER_INTERFACES+=",$staging_power_ifs"
    fi
    iniset $IRONIC_CONF_FILE DEFAULT enabled_power_interfaces "$IRONIC_ENABLED_POWER_INTERFACES"

    # management interfaces
    staging_mgmt_ifs=$($IRONIC_STAGING_LIST_EP_CMD -t ironic.hardware.interfaces.management)
    if [[ -z "$IRONIC_ENABLED_MANAGEMENT_INTERFACES" ]]; then
        # NOTE(pas-ha) implict default is ipmitool
        IRONIC_ENABLED_MANAGEMENT_INTERFACES="ipmitool,$staging_mgmt_ifs"
    else
        IRONIC_ENABLED_MANAGEMENT_INTERFACES+=",$staging_mgmt_ifs"
    fi
    iniset $IRONIC_CONF_FILE DEFAULT enabled_management_interfaces "$IRONIC_ENABLED_MANAGEMENT_INTERFACES"

    # vendor interfaces
    staging_vendor_ifs=$($IRONIC_STAGING_LIST_EP_CMD -t ironic.hardware.interfaces.vendor)
    if [[ -z "$IRONIC_ENABLED_VENDOR_INTERFACES" ]]; then
        # NOTE(pas-ha) implict default is ipmitool,no-vendor
        IRONIC_ENABLED_VENDOR_INTERFACES="ipmitool,no-vendor,$staging_vendor_ifs"
    else
        IRONIC_ENABLED_VENDOR_INTERFACES+=",$staging_vendor_ifs"
    fi
    iniset $IRONIC_CONF_FILE DEFAULT enabled_vendor_interfaces "$IRONIC_ENABLED_VENDOR_INTERFACES"

    # deploy interfaces
    staging_deploy_ifs=$($IRONIC_STAGING_LIST_EP_CMD -t ironic.hardware.interfaces.deploy)
    if [[ -z "$IRONIC_ENABLED_DEPLOY_INTERFACES" ]]; then
        # NOTE(pas-ha) implict default is iscsi,direct
        IRONIC_ENABLED_DEPLOY_INTERFACES="iscsi,direct,$staging_deploy_ifs"
    else
        IRONIC_ENABLED_DEPLOY_INTERFACES+=",$staging_deploy_ifs"
    fi
    iniset $IRONIC_CONF_FILE DEFAULT enabled_deploy_interfaces "$IRONIC_ENABLED_DEPLOY_INTERFACES"
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

    for node in $(openstack --os-cloud devstack baremetal node list -f value -c UUID); do
        openstack --os-cloud devstack-admin baremetal node maintenance set $node
        # switch driver to ansible-enabled one
        if [[ "$IRONIC_STAGING_DRIVER" =~ "staging" ]]; then
            # using hardware type
            openstack --os-cloud devstack-admin baremetal node set $node \
                 --driver ${IRONIC_STAGING_DRIVER} \
                 --deploy-interface staging-ansible \
                 --driver-info deploy_ramdisk=$ansible_ramdisk_id \
                 --driver-info ansible_deploy_username=tc \
                 --driver-info ansible_deploy_key_file=$ansible_key_file
        else
            # using classic driver
            # TODO(pas-ha) remove after ansible job is switched to use 
            #              staging-ansible-ipmi dynamic driver
            openstack --os-cloud devstack-admin baremetal node set $node \
                --driver ${IRONIC_STAGING_DRIVER} \
                --driver-info deploy_ramdisk=$ansible_ramdisk_id \
                --driver-info ansible_deploy_username=tc \
                --driver-info ansible_deploy_key_file=$ansible_key_file
        fi
        # set nodes to use the uploaded ramdisk and appropriate SSH creds
        openstack --os-cloud devstack-admin baremetal node maintenance unset $node
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
