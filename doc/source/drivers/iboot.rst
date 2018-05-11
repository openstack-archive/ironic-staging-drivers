.. _IBOOT:

============
iBoot driver
============

Overview
========
The iBoot power driver enables you to take advantage of power cycle
management of nodes using Dataprobe iBoot devices over the DxP protocol.

The ``staging-iboot`` hardware type uses iBoot to manage power of the nodes.

Requirements
------------

* ``python-iboot`` library should be installed - https://github.com/darkip/python-iboot

Tested platforms
----------------

* iBoot-G2 [1]_

Configuring and enabling
------------------------

1. Add ``staging-iboot`` to ``enabled_hardware_types`` and
   ``enabled_power_interfaces`` in */etc/ironic/ironic.conf*. Also enable
   the ``fake`` management interface. For example::

    [DEFAULT]
    enabled_hardware_types = staging-iboot,ipmi
    enabled_management_interfaces = fake,ipmitool
    enabled_power_interfaces = staging-iboot,ipmitool

2. Restart the Ironic conductor service::

    service ironic-conductor restart

Registering a node
------------------

Nodes configured for the iBoot driver should have the ``driver`` property
set to ``staging-iboot``.

The following configuration values are also required in ``driver_info``:

- ``iboot_address``: The IP address of the iBoot PDU.
- ``iboot_username``: User name used for authentication.
- ``iboot_password``: Password used for authentication.

In addition, there are optional properties in ``driver_info``:

- ``iboot_port``: iBoot PDU port. Defaults to 9100.
- ``iboot_relay_id``: iBoot PDU relay ID. This option is useful in order
  to support multiple nodes attached to a single PDU. Defaults to 1.

The following sequence of commands can be used to enroll a node with
the iBoot driver.

1. Create node::

    openstack baremetal node create --driver staging-iboot \
        --driver-info iboot_username=<username> \
        --driver-info iboot_password=<password> \
        --driver-info iboot_address=<address>

References
==========
.. [1] iBoot-G2 official documentation - http://dataprobe.com/support_iboot-g2.html
