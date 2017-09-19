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
# override Ansible version to install
# default is specified in ironic_staging_drivers/ansible/python-requirements.txt
# if set, must be a pip-recognizable version spec for Ansible PyPI package
IRONIC_STAGING_ANSIBLE_VERSION_SPEC=${IRONIC_STAGING_ANSIBLE_VERSION_SPEC:-}

function setup_ironic_enabled_interfaces_for {

    local iface=$1
    local iface_var
    local ironic_iface_var
    local staging_ifs
    iface_var=$(echo $iface | tr '[:lower:]' '[:upper:]')
    ironic_iface_var="IRONIC_ENABLED_${iface_var}_INTERFACES"
    staging_ifs=$($IRONIC_STAGING_LIST_EP_CMD -t ironic.hardware.interfaces.${iface})

    # NOTE(pas-ha) need fake management interface enabled for staging-wol hw type,
    # and even if WoL is disabled by skips or filters, no harm in enabling it any way
    if [[ $iface == 'management' ]]; then
        if [[ -n ${staging_ifs} ]]; then
            staging_ifs+=",fake"
        else
            staging_ifs='fake'
        fi
    fi

    if [[ -n ${staging_ifs} ]]; then
        iniset $IRONIC_CONF_FILE DEFAULT "enabled_${iface}_interfaces" "${!ironic_iface_var},$staging_ifs"
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
    for i in $IRONIC_DRIVER_INTERFACE_TYPES; do
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
            # NOTE(pas-ha) install 'other' dependencies first just in case
            # they contain something required to build Python dependencies
            if [[ -f "$o_deps" ]]; then
               echo_summary "Installing $driver other dependencies"
               source $o_deps
            fi
            if [[ -f "$p_deps" ]]; then
               echo_summary "Installing $driver python dependencies"
               pip_install -r $p_deps
            fi
        fi
    done
    if [ -n ${IRONIC_STAGING_ANSIBLE_VERSION_SPEC} ]; then
        # NOTE(pas-ha) re-install another Ansible version.
        # useful for bitrot-like jobs to test with previous releases
        # or (if we ever cap Ansible version) with new releases
        echo_summary "Overriding Ansible version to ${IRONIC_STAGING_ANSIBLE_VERSION_SPEC}"
        pip_install "ansible${IRONIC_STAGING_ANSIBLE_VERSION_SPEC}"
    fi
}

function configure_ironic_testing_driver {
    if [[ "$IRONIC_STAGING_DRIVER" =~ "ansible" && \
          "$IRONIC_STAGING_DRIVER" =~ "ipmi" ]]; then
        echo_summary "Configuring ansible deploy driver interface"
        configure_ansible_deploy_driver
    else
        die $LINENO "Failed to configure ${IRONIC_STAGING_DRIVER} driver/hw type: not supported by devstack plugin or other pre-conditions not met"
    fi
}

function configure_ansible_deploy_driver {
    # NOTE(pas-ha) DevStack now defaults to tls-proxy being enabled.
    # Using custom CA bundle is not that easy with TinyCore,
    # requiring extra rebuild steps and resulting in bigger image,
    # so just disable validating SSL certs for now in DevStack
    # similar to what ironic does for IPA by default in DevStack
    iniset $IRONIC_CONF_FILE ansible image_store_insecure True

    # set logging for ansible-deploy
    # NOTE(pas-ha) w/o systemd or syslog, there will be no output
    # of single ansible tasks to ironic log,
    # only in the stdout returned by processutils
    if [[ "$USE_SYSTEMD" == "True" ]]; then
        iniset $IRONIC_STAGING_DRIVERS_DIR/ironic_staging_drivers/ansible/playbooks/callback_plugins/ironic_log.ini ironic use_journal "True"
    elif [[ "$SYSLOG" == "True" ]]; then
        iniset $IRONIC_STAGING_DRIVERS_DIR/ironic_staging_drivers/ansible/playbooks/callback_plugins/ironic_log.ini ironic use_syslog "True"
    fi
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
        # switch driver to ansible-enabled hardware type, use minimal API version that supports setting driver interfaces,
        # set nodes to use the uploaded ramdisk and appropriate SSH creds.
        # TODO(pas-ha) remove API version when OSC defaults to 'latest'
        # TODO(pas-ha) change the job definition in project-config to set the HW type
        # when stable/pike is no longer supported
        openstack --os-cloud devstack-admin --os-baremetal-api-version 1.31 baremetal node set $node \
             --driver staging-ansible-ipmi \
             --deploy-interface staging-ansible \
             --driver-info deploy_ramdisk=$ansible_ramdisk_id \
             --driver-info ansible_deploy_username=tc \
             --driver-info ansible_deploy_key_file=$ansible_key_file
    done
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
        if [[ -n ${IRONIC_STAGING_DRIVER} ]]; then
            configure_ironic_testing_driver
        fi
    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        if [[ -n ${IRONIC_STAGING_DRIVER} ]]; then
            set_ironic_testing_driver
        fi
    fi
fi
