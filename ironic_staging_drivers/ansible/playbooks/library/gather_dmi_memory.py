#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import subprocess


def get_physical_memory():
    try:
        memory_mb = subprocess.check_output("sudo dmidecode --type 17 | "
                                            "grep Size | awk '{print $2}'",
                                            shell=True)
    except subprocess.CalledProcessError:
        memory_mb = ''
    return memory_mb.strip()


def kernel_cmdline():
    """Parse linux kernel command line"""
    with open('/proc/cmdline', 'rt') as f:
        cmdline = f.read()
    parameters = {}
    for p in cmdline.split():
        name, _, value = p.partition('=')
        parameters[name] = value
    return parameters


def main():
    module = AnsibleModule(
        argument_spec=dict(),
        supports_check_mode=True
    )

    facts = {"custom_facts": {
        "memory_mb": get_physical_memory(),
        "boot_interface": kernel_cmdline().get('BOOTIF')}}

    ansible_facts = {"ansible_facts": facts}
    module.exit_json(**ansible_facts)


from ansible.module_utils.basic import *  # noqa
if __name__ == '__main__':
    main()
