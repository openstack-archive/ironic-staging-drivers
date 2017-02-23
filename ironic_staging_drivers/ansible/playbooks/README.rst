############################################
Playbooks for ironic's ansible-deploy driver
############################################

deploy.yaml
===========

Default playbook trying to resemble default IPA behavior.

For partition images, it will create up to 4 partitions (for root, swap and
ephemeral partitions, and configdrive) based on info in instance_info,
with root partition being last to allow it to grow.

For whole-disk images, the configdrive partition will be created at the end
of the disk (or at the end of first 2TB in case of MBR disk label).

deploy-single-lvm.yaml
======================

If image is a partition image and instance_info has ``image_properties`` key
with sub-key ``lvm_partitions``, the logic of deployment will be modified as
follows.

For other cases, the same logic as in `deploy.yaml`_ will be used
(by re-using the same Ansible roles).

Prerequisites
-------------

- LVM is installed in both deploy ramdisk and user image.
- Deploy ramdisk supports creation of required file systems
- user image is a partition image,  with grub installed
  (only localboot is supported by ansible-deploy driver).

Logic of deployment
-------------------

On each disk available 100MiB boot and 64MiB configdrive partitions will be
created. The rests of disks will be plugged into a single LVM volume group
'system', and partitions for the user image will be created on it.

Partitions to create on the ``system`` LVG are defined by ``image_properties``
key in the node's ``instance_info`` (in integrated case populated from Glance).
For this custom logic of deployment to kick in, it has to be dictionary
containing an ``lvm_partitions`` key following dict structure::

    {
        "lvm_partitions: {
            "root: {
                "size": "<partition-size>",
                "mount": "/",
                "fstype": "<file-system-to-create>"
            },
            ...
            "<another partition>": {
                "size": "<partition-size>",
                "mount": "/path/to/other/mount/point",
                "fstype": "<file-system-to-create>"
            }
        }
    }

The ``root`` element is mandatory,
``boot`` element must be absent (boot partition is created outside of LVM).

``fstype`` must be supported by deploy ramdisk.
It is not mandatory for ``root`` partition as it will be overwritten
by the user image any way.

``size`` is passed directly to Ansible's ``lvol`` module, and can accept
units (default is M) and % of VG or free space (see Ansible and LVM docs).

The bootloader will be installed into 'boot' partition of the first disk,
and this will be mounted as ``/boot`` to the user image.

The configdrive will be written to 'configdrive' partition on the first disk.

Other created LVM partitions will be populated by files from existing paths
in user image and entered into ``fstab`` so that they are mounted on boot.

Example (for ironic standalone) to create a 50G rootfs,
and 10% of overall size for ``/var/log`` formatted as ``ext2``::

    $ openstack baremetal node set <node> \
        --driver-info ansible_deploy_playbook='deploy-single-lvm.yaml' \
        --instance-info image_source="http://..." \
        --instance-info image_checksum='md5:...' \
        --instance-info root_gb=10 \
        --instance-info image_disk_format='qcow2' \
        --instance-info image_container_format='bare' \
        --instance-info kernel='noop' \
        --instance-info ramdisk='noop' \
        --instance-info configdrive='http://...' \
        --instance-info image_properties='{"lvm_partitions": {"root": {"size": "50G", "mount": "/"}, "logs": {"size": "10%VG", "fstype": "ext2", "mount": "/var/log"}}}'

    $ openstack baremetal node deploy <node>
