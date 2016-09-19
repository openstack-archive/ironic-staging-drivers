.. _libvirt:

###############
Libvirt drivers
###############

Overview
========

This driver implements Power/Management interfaces for virtual baremetal
hardware and is based on Libvirt [1]_ library and its Python interface.
Thus it is suited **for testing environments only**.

It performs considerably better that Ironic's SSH driver, especially when
there are many virtual baremetal nodes placed on hypervizor [2]_.
It also supports additional connection transports, including TCP with SASL
authentication that can be considered as secure alternative to SSH.

Known drawbacks in comparison to Ironic's SSH driver are:

- no support for user+password SSH authentication
- some use cases possible with SSH driver are not supported

  - e.g. managing VirtualBox VMs on a Windows host from Linux guest

Setting up the environment
==========================

#. Install Ironic
#. Install ironic-staging-drivers
#. Install ``libvirt-python``

   * When installing from PyPI, you'd need development version of
     ``libvirt`` package from your distribution
     (e.g. ``libvirt-dev`` in Ubuntu, ``libvirt-devel`` in Fedora)
     and all the usual Python packages required to compile C-extensions
     in your system
     (on DevStack, those are already installed when nova-compute is enabled).

#. Add desired driver(s) to the list of ``enabled_drivers`` in ironic.conf
   (see `Available drivers and options`_)
   and restart ironic-conductor service.
#. Create or update existing virtual baremetal nodes to use one of
   libvirt-based drivers enabled in the previous step.
#. Update node properties with driver-specific fields if needed.
   (see `Node driver_info`_).
   Default values are suitable for single-node DevStack.
#. Deploy the node.

Available drivers and options
=============================

Several drivers are provided by Ironic-staging drivers

pxe_libvirt_agent
    Uses PXE to Boot interface, Libvirt for Power/Management and Agent deploy

pxe_libvirt_iscsi
    Uses PXE to Boot interface, Libvirt for Power/Management and ISCSI deploy

fake_libvirt_fake
    This driver is used for testing of Libvirt Power/Management driver
    interfaces themselves.

As for all Ironic drivers, you can easily create your own collection of driver
interfaces to suit your needs and register that as Ironic driver.

Config
------
These driver interfaces have no specific options in Ironic configuration file.

Node driver_info
----------------

libvirt_uri
    (optional) Libvirt URI to connect to.
    Default is ``qemu+unix:///system``.

ssh_key_filename
    (optional) File name of private SSH key when using ``qemu+ssh://``
    transport.
    The file must have appropriate permissions for the user running
    ironic-conductor service.
    Default is to use default SSH keys for that user.
    Note that for private keys with password those must be pre-loaded into
    ``ssh-agent``.

sasl_username
    username to authenticate as.
    Required when using TCP transport with SASL authentication.

sasl_password
    password to use for SASL authentication.
    Required when using TCP transport with SASL authentication.

References
==========

.. [1] https://libvirt.org
.. [2] https://github.com/pshchelo/ironic_libvirt_vs_virsh
