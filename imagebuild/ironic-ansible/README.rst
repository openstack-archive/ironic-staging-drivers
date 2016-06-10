==============
ironic-ansible
==============

Builds a ramdisk for Ironic Ansible deploy driver.

This element uses ``devuser`` for user name and key settings,
and ``ironic-python-agent`` for Ironic API lookup and heartbeats.

Consult docs for those elements for available options.

Note: compared to ``devuser`` element, this element **always** gives
the configured user password-less sudo permissions (*unconfigurable*).

Requires Ironic API >= 1.22.
