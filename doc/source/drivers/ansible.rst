.. _ansible:

######################
Ansible-deploy drivers
######################

Ansible is an already mature and popular automation tool, written in Python
and requiring no agents running on the node being configured.
All communications with the node are by default performed over secure SSH
transport.

This deployment driver is using Ansible playbooks to define the
deployment logic. It is not based on Ironic Python Agent and does not need
it to be running in the bootstrap image.


Overview
========

The main advantage of this driver is extended flexibility in regards of
changing and adapting node deployment logic to the particular use case,
using the tooling already familiar to operators.

It also allows to shorten the usual feature development cycle of
"implement logic in Ironic,
implement logic in Agent,
rebuild bootstrap image,
upload it to Glance/HTTP storage,
reassign bootstrap image to nodes,
restart Ironic service and
run a test deployment".

The main disadvantage is a synchronous manner of performing
deployment/cleaning tasks, as Ansible is invoked as ``ansible-playbook``
CLI command via Python's ``subprocess`` library.

Each action (deploy, clean) is described by single playbook with roles,
which is run whole during deployment, or tag-wise during cleaning.
Control of deployment types and cleaning steps is through tags and
auxiliary steps file for cleaning.
The playbooks for actions can be set per-node, as is cleaning steps
file.

Features
--------

Supports two modes for continuing deployment:

- having the bootstrap image calling back to Ironic API's
  ``heartbeat`` endpoint (default)
- polling the node until the ssh port is open as part of a playbook

User images
~~~~~~~~~~~

Supports whole images and partition images:

- compressed images are downloaded to RAM and converted to disk device;
- raw images are streamed to disk directly from HTTP.

For partition images the driver will create root partition, and,
if requested, also ephemeral and swap partitions as set in node's
``instance_info`` by Nova or operator.
Partition table created will be of ``msdos`` type.

Configdrive partition
~~~~~~~~~~~~~~~~~~~~~

Creating a configdrive partition is supported for both whole disk
and partition images, on both MBR and GPT labeled disks.

Root device hints
~~~~~~~~~~~~~~~~~

Root device hints are currently not supported (first device returned as
``ansible_devices`` fact is used), but support for them is planned.

Node cleaning
~~~~~~~~~~~~~

Cleaning is supported, both automated and manual.
Currently the driver has two default clean steps:

- wiping device metadata
- disk shredding

Their priority can be overriden via options in Ironic configuration file's
``[deploy]`` section the same as for Ironic Python Agent-based drivers.

As in the case of this driver all cleaning steps are known to conductor,
booting the bootstrap image is completely skipped when
there are no cleaning steps to perform.

Aborting cleaning tasks is not supported.

Logging
~~~~~~~

Logging is implemented as custom Ansible callback module,
that used oslo.log and oslo.config and can interleave Ansbile event log
into the log file configured in `ironic.conf` (has some quirks in DevStack
due to default logging system there),
or use a separate file to Ansible events into.


Requirements
============

Ironic
    Requires Ironic API ≥ 1.22 when using callback functionality.
    For better logging, Ironic should be > 6.1.0 release.

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
- python-requests (for Ironic callback and streaming image download)
- python-netifaces (for Ironic callback)

Set of scripts to build a suitable bootstrap ramdisk based on TinyCore Linux
(codename ``irsible``),
and an element for ``diskimage-builder`` will be provided.

Setting up your environment
===========================

#. Install Ironic (either as part of OpenStack/DevStack or standalone)
#. Install Ansible (``pip install ansible`` should suffice).
#. Install ``ironic-staging-drivers``
#. Edit Ironic configuration file

   A. Add one of the ansible-enabled drivers to ``enabled_drivers`` option.
      (see `Available drivers and options`_).
   B. Add ``[ansible]`` config section and configgure it if needed
      (see `Configiuration file`_).

#. (Re)start Ironic-conductor service
#. Build a suitable kernel and ramdisk images
#. Upload them to Glance or put in your HTTP storage
   when Ironic is standalone.
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
    Uses PXE/iPXE to boot the nodes, and Ironic's SSH driver for
    Power/Management. Used only in testing environments.

pxe_libvirt_ansible
    Alternative to ``pxe_ssh_ansible``, uses LibVirt-based driver for
    Power/Management (part of ``ironic-stafing-drivers``).
    Can be used for bigger CI environments, where it is has better
    performance than Ironic's SSH driver.

Ansible-deploy options
----------------------

Configiuration file
~~~~~~~~~~~~~~~~~~~

Driver options are configured in ``[ansible]`` section of Ironic
configuration file.

use_ramdisk_callback
    Whether to expect the callback from the bootstrap image when it is
    ready to accept command or use passive polling for running SSH daemon
    on the node as part of running playbooks.
    Default is True.

verbosity
    None, 0-4. Corresponds to number of 'v's passed to ``ansible-playbook``.
    Default (None) will pass 4 when global debug is enabled in Ironic,
    and 0 otherwise.

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
    Memory (in MiB) used by the in-bootstrap Ansible-related processes.
    Affects decision if the downloaded user image will fit into RAM
    of the node.
    Default is 10MiB.

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

Set them per-node via::

    ``ironic node-update <node> <op> driver_info/<key>=<value>``

or::

    ``openstack baremetal node set <node> --driver-info <key>=<value>``.


ansible_deploy_user
    User name to use for Ansible to access the node (default is ``ansible``).

ansible_deploy_key_file
    Private SSH key used to access the node. If none is provided (default),
    Ansible will use the default SSH keys configured for the user running
    ironic-conductor service.
    Also note, that for private keys with password, these must be pre-loaded
    to ``ssh-agent``.

ansible_deploy_playbook
    Name of the playbook file inside the ``playbooks_path`` folder
    to use when deploying this node.
    Default is ``deploy.yaml``.

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

The ``playbooks_path`` configured in the Ironic config is expected
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

Extending playbooks
-------------------

Most probably you'd start experimenting like this:

#. Create a copy of ``deploy.yaml`` playbook, name it distinctively.
#. Create Ansible roles with your customized logic in ``roles`` folder.

   A. Add the role with logic to be run *before* image download/writing
      as the first role in your playbook. This is a good place to
      set facts overriding those provided/omitted by the driver,
      like ``ironic_partitions`` or ``ironic_root_device``.
   B. Add the role with logic to be run *after* image is written to disk
      as second-to-last role in the playbook (right before ``shutdown`` role).

#. Assign the playbook you've created to the node's
   ``driver_info/ansible_deploy_playbook`` field.
#. Run deployment.

   A. No Ironic-conductor restart is necessary.
   B. A new bootstrap image must be built and assigned to nodes only when
      you want to use a command/script/package not present in the current
      bootstrap image and you can not or do not want to install it at runtime.

Variables you have access to
----------------------------

This driver will pass the following extra arguments to ansible-playbook
which you can use in your plays as well (some of them might not be defined):

image
    Dictionary containing:

    - ``url`` - URL to download the target image from as set in
      ``instance_info/image_url``.
    - ``disk_format`` - fetched from Glance or set in
      ``instance_info/image_disk_format``.
      Mainly used to distinguish ``raw`` images that can be streamed directly
      to disk.
    - ``checksum`` - (optional) image checksum as fetched from Glance or set
      in ``instance_info/image_checksum``. Used to verify downloaded image.
      When deploying from Glance, this will always be ``md5`` checksum.
      When deploying standalone, can also be set in the form ``<algo>:<hash>``
      to specify another hashing algorithm, which must be supported by
      Python ``hashlib`` package from standard library.
    - ``mem_req`` - (optional) required available memory on the node to fit
      the target image when not streamed to disk directly.
      Calculated from image size and ``[ansible]extra_memory`` config option.

configdrive
    Optional. When defined in ``instance_info`` (e.g. by Nova) is a
    dictonary of

    - ``type`` - either ``url`` or ``file``
    - ``location`` - depending on ``type``, either a URL of path to file
      stored on ironic-conductor node to fetch the content
      of configdrive partition from.

    In standalone deployments, you are free to override this variable
    in your playbooks.

ironic_partitions
    Optional. List of dictionaries defining partitions to create on the node
    in the form::

        {'name': <partition name>,
         'size_mib': <partition size in MiB>,
         'boot': <bool>,
         'swap': <bool>}

    When deployed via Nova, the driver will populate this list from
    ``root_gb``, ``swap_mb`` and ``ephemeral_gb`` fields of ``instance_info``.
    It will also honor ``ephemeral_format`` and ``preserve_ephemeral`` fields
    of ``instance_info``.

    In standalone deployment, you are free to override it in your playbooks.

ironic_extra
    Copy of ``extra`` field of Ironic node, with any per-node information.

As usual for Ansible playbooks, you also have access to standard
Ansible facts discovered by ``setup`` module.

Included custom Ansible modules
-------------------------------

The provided ``playbooks_path/library`` folder includes several custom
Ansible modules used by default implementation of ``deploy`` role.
You can use these modules in your playbooks as well.

stream_url
    Streaming download from http(s) source to the disk device directly,
    tries to be compatible with Ansible-core ``get_url`` module in terms of
    module arguments.

parted
    creates partition tables and partitions with `parted` utility.
