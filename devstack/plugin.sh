#!/bin/bash
# plugin.sh - devstack plugin for ironic-staging-drivers

IRONIC_STAGING_DRIVERS_DIR=$DEST/ironic-staging-drivers
IRONIC_DRIVERS_EXCLUDED_DIRS='tests common'


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
