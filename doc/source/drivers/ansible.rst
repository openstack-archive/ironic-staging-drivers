.. _ansible:

#####################
Ansible-deploy driver
#####################

Ansible is an already mature and popular automation tool, written in Python
and requiring no agents running on the node being configured.
All communications with the node are by default performed over secure SSH
transport.

The Ansible-deploy deployment driver is using Ansible playbooks to define the
deployment logic. It is not based on `Ironic Python Agent`_ (IPA)
and does not generally need it to be running in the deploy ramdisk.

.. note::
    The "playbook API", that is the set and structure of variables passed
    into playbooks from the driver, is not stable yet and will most probably
    change in next versions.

Overview
========

The main advantage of this driver is extended flexibility in regards of
changing and adapting node deployment logic to the particular use case,
using the tooling already familiar to operators.

It also allows to shorten the usual feature development cycle of

* implementing logic in ironic,
* implementing logic in IPA,
* rebuilding deploy ramdisk,
* uploading it to Glance/HTTP storage,
* reassigning deploy ramdisk to nodes,
* restarting ironic service and
* runing a test deployment

by using a more "stable" deploy ramdisk and not requiring
ironic-conductor restarts (see `Extending playbooks`_).

The main disadvantage is a synchronous manner of performing
deployment/cleaning tasks, as Ansible is invoked as ``ansible-playbook``
CLI command via Python's ``subprocess`` library.

Each action (deploy, clean) is described by single playbook with roles,
which is run whole during deployment, or tag-wise during cleaning.
Control of cleaning steps is through tags and auxiliary clean steps file.
The playbooks for actions can be set per-node, as is cleaning steps
file.

Features
--------

Supports two modes for continuing deployment (configured in driver
options, see `Configuration file`_):

- having the deploy ramdisk calling back to ironic API's
  ``heartbeat`` endpoint (default)
- polling the node until the ssh port is open as part of a playbook

User images
~~~~~~~~~~~

Supports whole-disk images and partition images:

- compressed images are downloaded to RAM and converted to disk device;
- raw images are streamed to disk directly.

For partition images the driver will create root partition, and,
if requested, ephemeral and swap partitions as set in node's
``instance_info`` by nova or operator.
Partition table created will be of ``msdos`` type by default,
the node's``disk_label`` capability is honored if it is set in node's
``instance_info``.

Configdrive partition
~~~~~~~~~~~~~~~~~~~~~

Creating a configdrive partition is supported for both whole disk
and partition images, on both ``msdos`` and ``GPT`` labeled disks.

Root device hints
~~~~~~~~~~~~~~~~~

Root device hints are currently supported in their basic form only
(with exact matches, without oslo.utils operators).
If no root device hint is provided for the node, first device returned as
part of ``ansible_devices`` fact is used as root device to create partitions
on or write the whole disk image to.

Node cleaning
~~~~~~~~~~~~~

Cleaning is supported, both automated and manual.
Currently the driver has two default clean steps:

- wiping device metadata
- disk shredding

Their priority can be overridden via options in ironic configuration file's
``[deploy]`` section the same as for IPA-based drivers.

As in the case of this driver all cleaning steps are known to conductor,
booting the deploy ramdisk is completely skipped when
there are no cleaning steps to perform.

Aborting cleaning tasks is not supported.

Logging
~~~~~~~

Logging is implemented as custom Ansible callback module,
that makes use of ``oslo.log`` and ``oslo.config`` libraries
and can re-use logging configuration defined in the main ironic configuration
file (``/etc/ironic/ironic.conf`` by default) to set logging for Ansible
events, or use a separate file for this purpose.

.. note::
    Currently this has some quirks in DevStack - due to default
    logging system there the ``log_file`` must be set explicitly in
    ``$playbooks_path/callback_plugins/ironic_log.ini`` when running
    DevStack in 'developer' mode using ``screen``.


Requirements
============

ironic
    Requires ironic version >= 8.0.0. (Pike release or newer).

Ansible
    Tested with and targets Ansible ≥ 2.1

Bootstrap image requirements
----------------------------

- password-less sudo permissions for the user used by Ansible
- python 2.7.x
- openssh-server
- GNU coreutils
- utils-linux
- parted
- gdisk
- qemu-utils
- python-requests (for ironic callback and streaming image download)
- python-netifaces (for ironic callback)

Set of scripts to build a suitable deploy ramdisk based on TinyCore Linux,
and an element for ``diskimage-builder`` is provided.

Setting up your environment
===========================

#. Install ironic (either as part of OpenStack/DevStack or standalone)
#. Install Ansible (``pip install ansible`` should suffice).
#. Install ``ironic-staging-drivers``
#. Edit ironic configuration file

   A. Add one of the Ansible-enabled drivers to ``enabled_drivers`` option.
      (see `Available drivers and options`_).
   B. Add ``[ansible]`` config section and configure it if needed
      (see `Configuration file`_).

#. (Re)start ironic-conductor service
#. Build suitable deploy kernel and ramdisk images
#. Upload them to Glance or put in your HTTP storage
#. Create new or update existing nodes to use the enabled driver
   of your choice and populate `Driver properties for the Node`_ when
   different from defaults.
#. Deploy the node as usual.

Available drivers and options
=============================

Three drivers are provided:

pxe_ipmitool_ansible
    Uses PXE/iPXE to boot of nodes, and ``ipmitool`` for Power/Management.
    This is the driver to use with real hardware nodes.

pxe_ssh_ansible
    Uses PXE/iPXE to boot the nodes, and ironic's SSH driver for
    Power/Management. Used only in testing environments.

pxe_libvirt_ansible
    Alternative to ``pxe_ssh_ansible``, uses LibVirt-based driver for
    Power/Management (part of ``ironic-staging-drivers``).
    Can be used for bigger CI environments, where it is has better
    performance than ironic's SSH driver.

Ansible-deploy options
----------------------

Configuration file
~~~~~~~~~~~~~~~~~~~

Driver options are configured in ``[ansible]`` section of ironic
configuration file.

use_ramdisk_callback
    Whether to expect the callback from the deploy ramdisk when it is
    ready to accept command or use passive polling for running SSH daemon
    on the node as part of running playbooks.
    Note that setting it to False *requires* Neutron to resolve the IP
    of the node for Ansible to attempt connection to, and thus is not
    suitable for standalone deployment.
    Default is True.

verbosity
    None, 0-4. Corresponds to number of 'v's passed to ``ansible-playbook``.
    Default (None) will pass 'vvvv' when global debug is enabled in ironic,
    and nothing otherwise.

ansible_playbook_script
    Full path to the ``ansible-playbook`` script. Useful mostly for
    testing environments when you e.g. run Ansible from source instead
    of installing it.
    Default (None) will search in ``$PATH`` of the user running
    ironic-conductor service.

playbooks_path
    Path to folder that contains all the Ansible-related files
    (Ansible inventory, deployment/cleaning playbooks, roles etc).
    Default is to use the playbooks provided with ``ironic-staging-drivers``
    from where it is installed.

config_file_path
    Path to Ansible's config file. When set to None will use global system
    default (usually ``/etc/ansible/ansible.cfg``).
    Default is ``playbooks_path``/ansible.cfg

ansible_extra_args
    Extra arguments to pass to ``ansible-playbook`` on each invocation.
    Default is None.

extra_memory
    Memory overhead (in MiB) for the Ansible-related processes
    in the deploy ramdisk.
    Affects decision if the downloaded user image will fit into RAM
    of the node.
    Default is 10.

post_deploy_get_power_state_retries
    Number of times to retry getting power state to check if
    bare metal node has been powered off after a soft poweroff.
    Default is 6.

post_deploy_get_power_state_retry_interval
    Amount of time (in seconds) to wait between polling power state
    after triggering soft poweroff.
    Default is 5.


Driver properties for the Node
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Set them per-node via:

.. code-block:: shell

   ironic node-update <node> <op> driver_info/<key>=<value>

or:

.. code-block:: shell

   openstack baremetal node set <node> --driver-info <key>=<value>


ansible_deploy_username
    User name to use for Ansible to access the node (default is ``ansible``).

ansible_deploy_key_file
    Private SSH key used to access the node. If none is provided (default),
    Ansible will use the default SSH keys configured for the user running
    ironic-conductor service.
    Also note, that for private keys with password, these must be pre-loaded
    into ``ssh-agent``.

ansible_deploy_playbook
    Name of the playbook file inside the ``playbooks_path`` folder
    to use when deploying this node.
    Default is ``deploy.yaml``.

ansible_shutdown_playbook
    Name of the playbook file inside the ``playbooks_path`` folder
    to use to gracefully shutdown the node in-band.
    Default is ``shutdown.yaml``.

ansible_clean_playbook
    Name of the playbook file inside the ``playbooks_path`` folder
    to use when cleaning the node.
    Default is ``clean.yaml``.

ansible_clean_steps_config
    Name of the YAML file inside the ``playbooks_path`` folder
    that holds description of cleaning steps used by this node,
    and defines playbook tags in ``ansible_clean_playbook`` file
    corresponding to each cleaning step.
    Default is ``clean_steps.yaml``.


Customizing the deployment logic
================================


Expected playbooks directory layout
-----------------------------------

The ``playbooks_path`` configured in the ironic config is expected
to have a standard layout for an Ansible project with some additions::

    <playbooks_path>
    |
    \_ inventory
    \_ add-ironic-nodes.yaml
    \_ roles
     \_ role1
     \_ role2
     \_ ...
    |
    \_callback_plugins
     \_ ...
    |
    \_ library
     \_ ...


The extra files relied by this driver are:

inventory
    Ansible inventory file containing a single entry of
    ``conductor ansible_connection=local``.
    This basically defines an alias to ``localhost``.
    Its purpose is to make logging for tasks performed by Ansible locally and
    referencing the localhost in playbooks more intuitive.
    This also suppresses warnings produced by Ansible about ``hosts`` file
    being empty.

add-ironic-nodes.yaml
    This file contains an Ansible play that populates in-memory Ansible
    inventory with access info received from the ansible-deploy driver,
    as well as some per-node variables.
    Include it in all your custom playbooks as the first play.

The default ``deploy.yaml`` playbook is using several smaller roles that
correspond to particular stages of deployment process:

    - ``discover`` - e.g. set root device and image target
    - ``prepare`` - if needed, prepare system, for example create partitions
    - ``deploy`` - download/convert/write user image and configdrive
    - ``configure`` - post-deployment steps, e.g. installing the bootloader

Some more included roles are:

    - ``wait`` - used when the driver is configured to not use callback from
      node to start the deployment. This role waits for OpenSSH server to
      become available on the node to connect to.
    - ``shutdown`` - used to gracefully power the node off in-band
    - ``clean`` - defines cleaning procedure, with each clean step defined
      as separate playbook tag.

Extending playbooks
-------------------

Most probably you'd start experimenting like this:

#. Create a copy of ``deploy.yaml`` playbook, name it distinctively.
#. Create Ansible roles with your customized logic in ``roles`` folder.

   A. In your custom deploy playbook, replace the ``prepare`` role
      with your own one that defines steps to be run
      *before* image download/writing.
      This is a good place to set facts overriding those provided/omitted
      by the driver, like ``ironic_partitions`` or ``ironic_root_device``,
      and create custom partitions or (software) RAIDs.
   B. In your custom deploy playbook, replace the ``configure`` role
      with your own one that defines steps to be run
      *after* image is written to disk.
      This is a good place for example to configure the bootloader and
      add kernel options to avoid additional reboots.

#. Assign the custom deploy playbook you've created to the node's
   ``driver_info/ansible_deploy_playbook`` field.
#. Run deployment.

   A. No ironic-conductor restart is necessary.
   B. A new deploy ramdisk must be built and assigned to nodes only when
      you want to use a command/script/package not present in the current
      deploy ramdisk and you can not or do not want
      to install those at runtime.

Variables you have access to
----------------------------

This driver will pass the single JSON-ified extra var argument to
Ansible (as ``ansible-playbook -e ..``).
Those values are then accessible in your plays as well
(some of them are optional and might not be defined):

.. code-block:: yaml


   ironic:
     nodes:
     - ip: <IPADDRESS>
       name: <NODE_UUID>
       user: <USER ANSIBLE WILL USE>
       extra: <COPY OF NODE's EXTRA FIELD>
     image:
       url: <URL TO FETCH THE USER IMAGE FROM>
       disk_format: <qcow2|raw|...>
       container_format: <bare|...>
       checksum: <hash-algo:hashstring>
       mem_req: <REQUIRED FREE MEMORY TO DOWNLOAD IMAGE TO RAM>
       tags: <LIST OF IMAGE TAGS AS DEFINED IN GLANCE>
       properties: <DICT OF IMAGE PROPERTIES AS DEFINED IN GLANCE>
     configdrive:
       type: <url|file>
       location: <URL OR PATH ON CONDUCTOR>
     partition_info:
       label: <msdos|gpt>
       preserve_ephemeral: <bool>
       ephemeral_format: <FILESYSTEM TO CREATE ON EPHEMERAL PARTITION>
       partitions: <LIST OF PARTITIONS IN FORMAT EXPECTED BY PARTED MODULE>


Some more explanations:

``ironic.nodes``
    List of dictionaries (currently of only one element) that will be used by
    ``add-ironic-nodes.yaml`` play to populate in-memory inventory.
    It also contains a copy of node's ``extra`` field so you can access it in
    the playbooks. The Ansible's host is set to node's UUID.

``ironic.image``
    All fields of node's ``instance_info`` that start with ``image_`` are
    passed inside this variable. Some extra notes and fields:

    - ``mem_req`` is calculated from image size (if available) and config
      option ``[ansible]extra_memory``.
    - if ``checksum`` initially does not start with ``hash-algo:``, hashing
      algorithm is assumed to be ``md5`` (default in Glance).

``ironic.partiton_info.partitions``
    Optional. List of dictionaries defining partitions to create on the node
    in the form:

    .. code-block:: yaml

       partitions:
       - name: <NAME OF PARTITION>
         unit: <UNITS FOR SIZE>
         size: <SIZE OF THE PARTITION>
         type: <primary|extended|logical>
         align: <ONE OF PARTED_SUPPORTED OPTIONS>
         format: <PARTITION TYPE TO SET>
         flags:
           flag_name: <bool>

    The driver will populate this list from ``root_gb``, ``swap_mb`` and
    ``ephemeral_gb`` fields of ``instance_info``.
    The driver will also prepend the ``bios_grub``-labeled partition
    when deploying on GPT-labeled disk,
    and pre-create a 64MiB partiton for configdrive if it is set in
    ``instance_info``.

    Please read the documentation included in the ``ironic_parted`` module's
    source for more info on the module and its arguments.

``ironic.partiton_info.ephemeral_format``
    Optional. Taken from ``instance_info``, it defines file system to be
    created on the ephemeral partition.
    Defaults to the value of ``[pxe]default_ephemeral_format`` option
    in ironic configuration file.

``ironic.partiton_info.preserve_ephemeral``
    Optional. Taken from the ``instance_info``, it specifies if the ephemeral
    partition must be preserved or rebuilt. Defaults to ``no``.

As usual for Ansible playbooks, you also have access to standard
Ansible facts discovered by ``setup`` module.

Included custom Ansible modules
-------------------------------

The provided ``playbooks_path/library`` folder includes several custom
Ansible modules used by default implementation of ``deploy`` and
``prepare`` roles.
You can use these modules in your playbooks as well.

``stream_url``
    Streaming download from HTTP(S) source to the disk device directly,
    tries to be compatible with Ansible's ``get_url`` module in terms of
    module arguments.
    Due to the low level of such operation it is not idempotent.

``ironic_parted``
    creates partition tables and partitions with ``parted`` utility.
    Due to the low level of such operation it is not idempotent.
    Please read the documentation included in the module's source
    for more information about this module and its arguments.
    The name is chosen so that the ``parted`` module included in Ansible 2.3
    is not shadowed.

.. _Ironic Python Agent: http://docs.openstack.org/developer/ironic-python-agent
