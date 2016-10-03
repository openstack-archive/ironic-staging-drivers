TinyIPA image compatible with Ansible-deploy driver
=============================================================

The TinyIPA image is almost suitable for Ansible-deploy driver when
built properly, except for some file location issues that are fixed
by rebuilding the ramdisk with the provided ``tinyipa-for-ansible.sh``
script.

Build instructions
------------------

#. Build the TinyIPA with both SSH access **enabled**
   and Python optimizations **disabled**
   (you'd need a recent, post-Newton tinyipa build scripts for this)::

       git clone git://git.openstack.org/openstack/ironic-python-agent
       cd ironic-python-agent/imagebuild/tinyipa
       export ENABLE_SSH=true
       # optionally set the path to the public SSH key
       # export SSH_PUBLIC_KEY=<path-to-public-ssh-key>
       export PYOPTIMIZE_TINYIPA=false
       make

   * Note that currently *neither of those settings is default in TinyIPA*,
     thus you can not use pre-built TinyIPA images from
     http://tarballs.openstack.org,
     and must really build new TinyIPA ramdisk with these settings on.

   * Please refer to TinyIPA's README for other available build options.

#. Run the provided script against created tinyipa ramdisk file
   (``<ironic-python-agent-repo-root>/imagebuild/tinyipa/tinyipa[-branch_name].gz``)::

       cd <ironic-staging-drivers-repo-root>/imagebuild/tinyipa-ansible
       ./tinyipa-for-ansible.sh <path-to-tinyipa-ramdisk.gz>

#. This will create ``tinyipa-ansible.gz`` file that should be uploaded
   to Glance as ARI image

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
