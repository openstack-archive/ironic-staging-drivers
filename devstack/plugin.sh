#!/bin/bash
# plugin.sh - devstack plugin for ironic-staging-drivers

IRONIC_STAGING_DRIVERS_DIR=$DEST/ironic-staging-drivers

# Comma separated list of ironic-staging-drivers. Will be added
# to IRONIC_ENABLED_DRIVERS if not enabled yet.
IRONIC_STAGING_DRIVERS_ENABLED='fake_libvirt_fake,pxe_libvirt_agent'

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
}

function install_ironic_staging_drivers {
    setup_develop $IRONIC_STAGING_DRIVERS_DIR
}

echo_summary "ironic-staging-drivers plugin.sh was called..."

if is_service_enabled ir-api ir-cond; then
    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        echo_summary "Installing Ironic-staging-drivers"
        install_ironic_staging_drivers

    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        echo_summary "Configuring Ironic-staging-drivers"
        update_ironic_enabled_drivers
    fi
fi
