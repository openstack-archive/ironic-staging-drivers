#########################################
Irsible - Tiny Core Ironic Ansible Deploy
#########################################

.. WARNING::
    This is experimental! Build tested on Ubuntu Server 14.04

Inspired by code from ``ironic-python-agent/imagebuild/tinyipa``

Included packages
=================

* python

  * requests
  * netifaces

* coreutils
* parted
* util-linux
* qemu-utils (built from source)
* sgdisk


Operational requirements
========================

Instance properties
-------------------

With this bootstrap image and Ironic's ansible-deploy driver,
140MB for a virtual baremetal node was found to be enough
to download a standard Cirros qcow image into RAM and convert it to disk.

When setting ``IRSIBLE_UNSQUASH`` to ``true`` (see `Image optimization`_),
the experimentally found required minimal amount of RAM is 210 MB.

Ironic version
--------------

When using Ironic callback/heartbeat functionality, *Ironic API must be of
version 1.22 or newer!*
This API version is provided by Ironic version ``6.1.0`` or later, or
OpenStack release ``Newton`` or later.

Build script requirements
=========================
For the main build script:

* wget
* unzip
* sudo
* awk
* mksquashfs

For building an ISO you'll also need:

* genisoimage


Build Instructions:
===================
To create a new ramdisk, run::

    make

or::

    make build final

to skip installing dependencies.

This will create two new files once completed:

* irsible.vmlinuz
* irsible.gz

These are your two files to upload to Glance for use with Ironic.


Building an ISO from a previous make run:
-----------------------------------------
Once you've built irsible it is possible to pack it into an ISO if required.
To create a bootable ISO, run::

     make iso

This will create one new file once completed:

* irsible.iso


To build a fresh ramdisk and build an iso from it:
--------------------------------------------------
Run::

    make all


To clean up the whole build environment run:
--------------------------------------------
Run::

    make clean

For cleaning up just the iso or just the ramdisk build::

    make clean_iso

or::

    make clean_build clean_final


Advanced options
================

SSH access keys
---------------

By default the ``id_rsa.pub`` or ``ir_dsa.pub`` SSH keys of the user who is
building the image will be added to ``authorized_keys`` for the user ``tc``.
To supply another public key, set the following variable
in the shell before building the image::

    export IRSIBLE_SSH_KEY=<path-to-the-public-key>

Creating a bare-minimal image
-----------------------------

By default the build process will also install Python into the image,
so that is becomes usable with Ansible right away.

If you want to create a very bare-minimal image to have it smaller and
install everything at run-time, set this variable in the shell
before building the image::

    export IRSIBLE_FOR_ANSIBLE=false

To use such image with Ansible, you will have to install Python and symlink
it to a location expected by Ansible
(or set this variable in your Ansible inventory)::

    ansible_python_interpreter=/usr/local/bin/python

The provided ``bootstrap.yaml`` Ansible playbook will do these steps for you.
You can include it in your playbooks when working with this image.

Creating minimal image for Ansible
----------------------------------

By default build script creates an image suitable for Ironic's ansible-deploy
driver, which includes installing (and building) some TC packages.
If you just want to build a minimal Ansible "slave", set this variable in the
shell before building the image::

    export IRSIBLE_FOR_IRONIC=false

Note
    This variable is ignored if ``IRSIBLE_FOR_ANSIBLE`` is set to ``false``.

Using with Ansible
==================

The user with configured SSH access is ``tc`` (default user in TinyCore),
use this username in your Ansible inventory or command line arguments.

This user already has password-less sudo permissions.

As this image is TinyCore-based, it lacks any standard package manager
like ``apt`` or ``yum``, use ``tce-*`` commands for package management
at run-time.

This image does not has ``bash`` installed, so do not use bash-isms in your
shell scripts that are to be run in this image.

Also, the minimal variants (as described above) are powered by ``busybox``
and lack many standard GNU tools,
do not rely on those in your Ansible playbooks when working with such images.

On the other hand those can be installed at run-time with
::

    tce-load -wi coreutils util-linux bash

so you can easily extend the ``bootstrap.yaml`` playbook. See this link for
more info on TinyCore's GNU/Linux compatibility:
http://tinycorelinux.net/faq.html#compatibility

Image optimization
==================

By default, build scripts will install TC packages in a standard manner for
this distribution, that is as squashfs'ed images mounted to loop devices via
unionfs.

You can have a bit smaller ramdisk and nicer looking ``mount`` listing
without all the loop devices mounted at the expense of more required RAM to
boot the deploy image if you set ``IRSIBLE_UNSQUASH=true`` environment
variable before building the image. This will install all the packages into
the ramdisk directly. Use that when your deployment playbooks can be affected
by all those extra mount points.

List of available env variables
===============================

IRSIBLE_FOR_ANSIBLE
    :Required: No
    :Default: true
    :Description: Installs and configures Python and OpenSSH server.
        Setting to ``false`` overrides ``IRSIBLE_FOR_IRONIC`` to ``false``.

IRSIBLE_FOR_IRONIC
    :Required: No
    :Default: true
    :Description: Installs additional software needed by
        Ironic's Ansible-deploy driver.
        Setting to ``true`` overrides ``IRSIBLE_FOR_ANSIBLE`` to ``true``.

IRSIBLE_SSH_KEY
    :Required: No
    :Default: ${HOME}/.ssh/id_{rsa,dsa}.pub
    :Description: Path to public SSH key to bake into the image as
        ``authorized_keys`` for user ``tc``.

IRSIBLE_UNSQUASH
    :Required: No
    :Default: false
    :Description: Whether to install packages as squashfs images or unpack
                  them to the system directly. Setting to ``true`` negatively
                  affects minimal required RAM to boot the image but allows
                  for cleaner reported mount points (``ansible_mounts`` fact).

BRANCH_PATH
    :Required: No
    :Default: not set
    :Description: When set, ``-$BRANCH_PATH`` is appended to names of
        produced files, e.g. setting to ``master`` will produce files
        ``irsible-master.gz`` etc.

TINYCORE_MIRROR_URL
    :Required: No
    :Default: http://repo.tinycorelinux.net/
    :Description: Allows to set custom location of repo with
        TinyCore packages.

QEMU_BRANCH
    :Required: No
    :Default: v2.6.1
    :Description: Branch/Tag in https://github.com/qemu/qemu repo
                  to checkout and built ``qemu-utils`` from
