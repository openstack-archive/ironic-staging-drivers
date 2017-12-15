#!/bin/bash
# plugin.sh - devstack plugin for ironic-staging-drivers

IRONIC_STAGING_DRIVERS_DIR=$DEST/ironic-staging-drivers
IRONIC_DRIVERS_EXCLUDED_DIRS='tests common'
# NOTE(pas-ha) change this back when there is any other then former
# ansible-deploy driver being able to set up by this devstack plugin
IRONIC_STAGING_DRIVER=""
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
}

function configure_ironic_testing_driver {
    die $LINENO "Failed to configure ${IRONIC_STAGING_DRIVER} driver/hw type: not supported by devstack plugin or other pre-conditions not met"
}

function set_ironic_testing_driver {
    die $LINENO "Failed to configure ironic to use ${IRONIC_STAGING_DRIVER} driver/hw type: not supported by devstack plugin or other pre-conditions not met"
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
