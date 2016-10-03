###################################################
TinyIPA image compatible with Ansible-deploy driver
###################################################

It is possible to rebuild the pre-built tinyipa image available from
_`http://tarballs.openstack.org/ironic-python-agent/tinyipa`
to make it usable with Ansible-deploy driver.


Customizing the build
=====================

#. By default, this script will rebuild the tinyipa master branch build.
   To use a stable branch, set ``BRANCH_PATH`` environment variable
   (``master`` by default) before running the rebuild script accordingly,
   for example::

       export BRANCH_PATH=stable-newton

   Consult _`http://tarballs.openstack.org/ironic-python-agent/tinyipa/files/`
   for currently available versions.
#. By default, the script will bake ``id_rsa`` or ``id_dsa`` public SSH keys
   of the user running the build into the ramdisk as authorized_keys for
   ``tc`` user.
   To provide a custom key, set absolute path to it as ``SSH_PUBLIC_KEY``
   environment variable before running this script::

       export SSH_PUBLIC_KEY=<path-to-public-ssh-key>


Running the build
=================

#. Run the provided ``rebuild-tinyipa.sh`` script

#. Running this script will create two images next to it

   * ``tinyipa-$BRANCH_PATH-ansible.gz`` file that should be uploaded
     to Glance as ARI image
   * ``tinyipa-$BRANCH_PATH.vmlinuz`` file that should be uploaded
     to Glance as AKI image if it is not there yet

#. Update nodes that use ``*_ansible`` driver:

   * Assign ramdisk uploaded in the previous step as
     ``driver_info/deploy_ramdisk``.

   * The kernel image created during TinyIPA build
     (``tinyipa[-branch_name].vmlinuz``) should be used as
     ``driver_info/deploy_kernel``.

   * Set ``tc`` as ``driver_info/ansible_deploy_user``.

     + If you have used a custom ``SSH_PUBLIC_KEY`` specify it as
       ``driver_info/ansible_deploy_key_file``

   * Ensure that the private SSH key file has correct ``600`` or ``400``
     exclusive permissions for the user running the ironic-conductor process.

#. You can also assign the ramdisk created to other nodes that use ``*agent*``
   drivers as ``driver_info/deploy_ramdisk`` to have a unified deploy image
   for all nodes, both using ``agent`` drivers and ``ansible`` ones.
   It should work for ``agent`` driver the same as original tinyipa ramdisk.
