.. _ansible:

#####################
Ansible-deploy driver
#####################

Ansible is an already mature and popular automation tool, written in Python
and requiring no agents running on the node being configured.
All communications with the node are by default performed over secure SSH
transport.

This deployment driver is using Ansible playbooks to define the
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
Control of deployment types and cleaning steps is through tags and
auxiliary steps file for cleaning.
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
Partition table created will be of ``msdos`` type.

Configdrive partition
~~~~~~~~~~~~~~~~~~~~~

Creating a configdrive partition is supported for both whole disk
and partition images, on both ``msdos`` and ``GPT`` labeled disks.

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
and can interleave Ansible event log into the log file configured in
main ironic configuration file (``/etc/ironic/ironic.conf`` by default),
or use a separate file to log Ansible events into.

.. note::
    Currently this has some quirks in DevStack - due to default
    logging system there the ``log_file`` must be set explicitly in
    ``$playbooks_path/callback_plugins/ironic_log.ini`` when running
    DevStack in 'developer' mode using ``screen``.



Requirements
============

ironic
    Requires ironic API ≥ 1.22 when using callback functionality.
    For better logging, ironic should be > 6.1.0 release.

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
and an element for ``diskimage-builder`` will be provided.

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

   A. No ironic-conductor restart is necessary.
   B. A new deploy ramdisk must be built and assigned to nodes only when
      you want to use a command/script/package not present in the current
      deploy ramdisk and you can not or do not want
      to install those at runtime.

Variables you have access to
----------------------------

This driver will pass the following extra arguments to ``ansible-playbook``
invocation which you can use in your plays as well
(some of them are optional and might not be defined):

``image``
    Dictionary of the following structure:

    .. code-block:: json

       {"image": {
           "url": "<url-to-user-image>",
           "disk_format": "<qcow|raw|..>",
           "checksum": "<hash-algo:hash>",
           "mem_req": 12345
           }
       }

    where

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
      Calculated from the image size and ``[ansible]extra_memory``
      config option.

``configdrive``
    Optional. When defined in ``instance_info`` is a dictionary
    of the following structure:

    .. code-block:: json

       {"configdrive": {
           "type": "<url|file>",
           "location": "<local-path-or-url>"
           }
       }

    where

    - ``type`` - either ``url`` or ``file``
    - ``location`` - depending on ``type``, either a URL or path to file
      stored on ironic-conductor node to fetch the content
      of configdrive partition from.

``ironic_partitions``
    Optional. List of dictionaries defining partitions to create on the node
    in the form:

    .. code-block:: json

       {"ironic_partitions": [
           {
               "name": "<partition name>",
               "size_mib": 12345,
               "boot": "yes|no|..",
               "swap": "yes|no|.."
           }
       ]}

    The driver will populate this list from ``root_gb``, ``swap_mb`` and
    ``ephemeral_gb`` fields of ``instance_info``.

``ephemeral_format``
    Optional. Taken from ``instance_info``, it defines file system to be
    created on the ephemeral partition.
    Defaults to the value of ``[pxe]default_ephemeral_format`` option
    in ironic configuration file.

``preserve_ephemeral``
    Optional. Taken from the ``instance_info``, it specifies if the ephemeral
    partition must be preserved or rebuilt. Defaults to ``no``.

``ironic_extra``
    Dictionary holding a copy of ``extra`` field of ironic node,
    with any per-node information.

As usual for Ansible playbooks, you also have access to standard
Ansible facts discovered by ``setup`` module.

Included custom Ansible modules
-------------------------------

The provided ``playbooks_path/library`` folder includes several custom
Ansible modules used by default implementation of ``deploy`` role.
You can use these modules in your playbooks as well.

``stream_url``
    Streaming download from HTTP(S) source to the disk device directly,
    tries to be compatible with Ansible-core ``get_url`` module in terms of
    module arguments.
    Due to the low level of such operation it is not idempotent.

``parted``
    creates partition tables and partitions with ``parted`` utility.
    Due to the low level of such operation it is not idempotent.

.. _Ironic Python Agent: http://docs.openstack.org/developer/ironic-python-agent
