###################################################
TinyIPA image compatible with Ansible-deploy driver
###################################################

It is possible to rebuild the pre-built tinyipa ramdisk available from
http://tarballs.openstack.org/ironic-python-agent/tinyipa
to make it usable with Ansible-deploy driver.


Customizing the build
=====================

#. By default, this script will rebuild the tinyipa master branch build.
   To use a stable branch, set ``BRANCH_PATH`` environment variable
   (``master`` by default) before running the rebuild script accordingly,
   for example::

       export BRANCH_PATH=stable-newton

   Consult http://tarballs.openstack.org/ironic-python-agent/tinyipa/files/
   for currently available versions.

   * It is possible to rebuild a local copy of tinyipa ramdisk by providing
     absolute path to it as first argument to the script, in which case
     ``BRANCH_PATH`` is ignored.

#. By default, the script will bake ``id_rsa`` or ``id_dsa`` public SSH keys
   of the user running the build into the ramdisk as authorized_keys for
   ``tc`` user.
   To provide a custom key, set absolute path to it as ``SSH_PUBLIC_KEY``
   environment variable before running this script::

       export SSH_PUBLIC_KEY=<path-to-public-ssh-key>


Running the build
=================

#. Run the provided ``rebuild-tinyipa.sh`` script

   * Without arguments, a pre-built ramdisk of appropriate version
     (as specified by ``BRANCH_PATH``) will be downloaded from
     tarballs.openstack.org and rebuilt.
   * Alternatively, an absolute path to the locally available tinyipa
     ramdisk file can be provided as first script argument.

#. Running this script will create a rebuilt ramdisk as
   ``ansible-<original-tinyipa-ramdisk-name>``.
   That file must be uploaded to Glance as ARI image.

   * If tinyipa kernel is not in Glance yet, an appropriate version can be
     downloaded from tarballs.openstack.org and
     uploaded to Glance as AKI image.

#. Update nodes that use ``*_ansible`` driver:

   * Assign ramdisk uploaded in the previous step as
     ``driver_info/deploy_ramdisk``.

   * The kernel image created during TinyIPA build
     (``tinyipa[-branch_name].vmlinuz``) should be used as
     ``driver_info/deploy_kernel`` if not set yet.

   * Set ``tc`` as ``driver_info/ansible_deploy_user``.

     + If you have used a custom ``SSH_PUBLIC_KEY`` specify it as
       ``driver_info/ansible_deploy_key_file``

   * Ensure that the private SSH key file has correct ``600`` or ``400``
     exclusive permissions for the user running the ironic-conductor process.

#. You can also assign the ramdisk created to other nodes that use
   ``IPA``-based ramdisks as ``driver_info/deploy_ramdisk`` to have a
   unified deploy image for all nodes.
   It should work for them the same as original tinyipa ramdisk.

Preparing DevStack
==================

The included script ``prepare-devstack.sh`` will setup your DevStack to work
with and test ansible-deploy driver. It will:

* Generate a set of SSH keys
* Download the ``ir-deploy-agent_ipmitool.initramfs`` tinyipa ramdisk image
  from Glance
* Rebuild it to ``ansible-ir-deploy-agent_ipmitool.initramfs`` ramdisk with
  the SSH keys generated
* Upload the rebuilt ramdisk to Glance
* Update *all* the ironic nodes to use ``pxe_ipmitool_ansible`` driver,
  with ``deploy_ramdisk``, ``ansible_deploy_user`` and
  ``ansible_deploy_key_file`` driver properties set appropriately.

Using Makefile
==============

For simplified configuration, a Makefile is provided to use ``make`` for
some standard operations.

make
  will install required dependencies and run the ``rebuild-tinyipa`` script
  without arguments, downloading and rebuilding the image available at
  http://tarballs.openstack.org

make devstack
  will install required dependencies and run ``prepare-devstack.sh`` script,
  rebuilding the image from Glance and setting nodes to use ansible-deploy
  driver. All customizations through environment variables still apply.

make clean
  will cleanup temporary files and images created during build
