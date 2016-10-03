#!/bin/bash

set -ex
ORIGINAL_DRIVER=${IRONIC_DEPLOY_DRIVER:-agent_ipmitool}

if [[ $ORIGINAL_DRIVER =~ (agent|pxe)_ipmitool ]]; then
    ansible_driver='pxe_ipmitool_ansible'
elif [[ $ORIGINAL_DRIVER =~ (agent|pxe)_ssh ]]; then
    ansible_driver='pxe_ssh_ansible'
else
    echo "Unsupported original ironic driver"
    exit 1
fi

# find the original tinyipa ramdisk
original_name="ir-deploy-${ORIGINAL_DRIVER}.initramfs"
original_id=$(openstack --os-cloud devstack-admin image list -f value -c ID --property name=${original_name})
if [ -z $original_id ]; then
    echo "Failed to find tinyipa ramdisk in Glance"
    exit 1
fi

# rebuild ramdisk
openstack --os-cloud devstack-admin image save ${original_id} --file ${original_name}
DATA_DIR=${DATA_DIR:-/opt/stack/data}
mkdir -p ${DATA_DIR}/ironic/ssh_keys
ssh_key_path="${DATA_DIR}/ironic/ssh_keys/ansible_key"
ssh-keygen -t rsa -N "" -f ${ssh_key_path}
chmod 600 $ssh_key_path
export SSH_PUBLIC_KEY=${ssh_key_path}.pub
./rebuild-tinyipa.sh ${PWD}/${original_name}
# upload rebuilt ramdisk to Glance
ansible_name="ansible-${original_name}"
ansible_id=$(openstack --os-cloud devstack-admin image create ${ansible_name} --file ${ansible_name} --disk-format ari --container-format ari --public -f value -c id)

# set nodes to use ansible_deploy driver with uploaded ramdisk
nodes=$(openstack --os-cloud devstack baremetal node list -f value -c UUID)
for node in $nodes; do
    openstack --os-cloud devstack-admin baremetal node set $node \
        --driver ${ansible_driver} \
        --driver-info deploy_ramdisk=$ansible_id \
        --driver-info ansible_deploy_username=tc \
        --driver-info ansible_deploy_key_file=$ssh_key_path
done
