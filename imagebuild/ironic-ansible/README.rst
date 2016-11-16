==============
ironic-ansible
==============

Builds a ramdisk for Ironic Ansible deploy driver.

This element is based on the following elements:

- ``devuser`` to create and configure a user for Ansible to access the node
- ``ironic-agent`` to provide Ironic API lookup and heartbeats via IPA

Consult docs for those elements for available options.

Additionally this element:

- ensures OpenSSH is installed and configured properly
- correctly sets hostname to avoid some Ansible problems with elevation

Note: compared to ``devuser`` element, this element **always** gives
the configured user password-less sudo permissions (*unconfigurable*).

Requires Ironic API >= 1.22.
