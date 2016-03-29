#!/bin/bash
# plugin.sh - devstack plugin for ironic-staging-drivers

IRONIC_STAGING_DRIVERS_DIR=$DEST/ironic-staging-drivers

# Comma separated list of ironic-staging-drivers. Will be added
# to IRONIC_ENABLED_DRIVERS if not enabled yet.
IRONIC_STAGING_DRIVERS_ENABLED='fake_libvirt_fake,pxe_libvirt_agent'

IRONIC_STAGING_DRIVERS_DIRS='amt intel_nm libvirt wol'

function update_ironic_enabled_drivers {
    local saveIFS
    saveIFS=$IFS
    IFS=","
    for driver in $IRONIC_STAGING_DRIVERS_ENABLED; do
        if [[ ! $IRONIC_ENABLED_DRIVERS =~ $(echo "\<$driver\>") ]]; then
            IRONIC_ENABLED_DRIVERS="${IRONIC_ENABLED_DRIVERS},$driver"
        fi
    done
    IFS=$saveIFS
    # NOTE(vsaienko) if ironic-staging-drivers are called after ironic
    # setting IRONIC_ENABLED_DRIVERS will not take affect. Update ironic
    # configuration explicitly.
    iniset $IRONIC_CONF_FILE DEFAULT enabled_drivers $IRONIC_ENABLED_DRIVERS
}

function install_ironic_staging_drivers {
    setup_develop $IRONIC_STAGING_DRIVERS_DIR
}

function install_drivers_dependencies {
    local p_deps
    local o_deps
    for driver in $IRONIC_STAGING_DRIVERS_DIRS; do
        p_deps=${IRONIC_STAGING_DRIVERS_DIR}/ironic_staging_drivers/${driver}/python-requirements.txt
        o_deps=${IRONIC_STAGING_DRIVERS_DIR}/ironic_staging_drivers/${driver}/other-requirements.sh
        if [[ -f "$p_deps" ]]; then
            echo_summary "Installing $driver python dependencies"
            pip install -r $p_deps
        fi
        if [[ -f "$o_deps" ]]; then
            echo_summary "Installing $driver other dependencies"
            bash $o_deps
        fi
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
    fi
fi
