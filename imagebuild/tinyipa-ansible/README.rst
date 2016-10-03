###################################################
TinyIPA image compatible with Ansible-deploy driver
###################################################

It is possible to rebuild the pre-built tinyipa ramdisk available from
http://tarballs.openstack.org/ironic-python-agent/tinyipa
to make it usable with Ansible-deploy driver.

Rebuilding TinyIPA
==================

#. Run the provided ``rebuild-tinyipa.sh`` script,
   set environment variables as explained in `Build options`_.

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

Build options
-------------

#. If rebuilding an existing tinyipa ramdisk file, set the
   ``TINYIPA_RAMDISK_FILE`` environment variable to absolute path to
   this file before running this script::

       export TINYIPA_RAMDISK_FILE=</full/path/to/tinyipa-ramdisk-file>

#. When not provided with existing file, this script will rebuild the
   tinyipa master branch build.
   To use a stable branch, set ``BRANCH_PATH`` environment variable
   (``master`` by default) before running the rebuild script accordingly.
   Branch names for stable releases must be in the form ``stable-<release>``,
   for example::

       export BRANCH_PATH=stable-newton

   Consult https://tarballs.openstack.org/ironic-python-agent/tinyipa/files/
   for currently available versions.

#. By default, the script will bake ``id_rsa`` or ``id_dsa`` public SSH keys
   of the user running the build into the ramdisk as authorized_keys for
   ``tc`` user.
   To provide a custom key, set absolute path to it as ``SSH_PUBLIC_KEY``
   environment variable before running this script::

       export SSH_PUBLIC_KEY=<path-to-public-ssh-key>

Using Makefile
--------------

For simplified configuration, a Makefile is provided to use ``make`` for
some standard operations.

make
  will install required dependencies and run the ``rebuild-tinyipa`` script
  without arguments, downloading and rebuilding the image available at
  https://tarballs.openstack.org
  All customizations through environment variables still apply.

make clean
  will cleanup temporary files and images created during build
