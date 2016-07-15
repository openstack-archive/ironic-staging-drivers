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


import json
import os
import subprocess


import netaddr
import netifaces


def _get_interface_info(interface_name):
    addr_path = '/sys/class/net/%s/address' % interface_name
    with open(addr_path) as addr_file:
        mac_addr = addr_file.read().strip()

    return {'name': interface_name,
            'mac_address': mac_addr,
            'ipv4_address': _get_ipv4_addr(interface_name)}

def _get_ipv4_addr(interface_id):
    try:
        addrs = netifaces.ifaddresses(interface_id)
        return addrs[netifaces.AF_INET][0]['addr']
    except (ValueError, IndexError, KeyError):
        # No default IPv4 address found
        return None

def _is_device(interface_name):
    device_path = '/sys/class/net/%s/device' % interface_name 
    return os.path.exists(device_path)

def _is_loopback(iface):
    is_loopback = (iface['ipv4_address'] and
                   netaddr.IPAddress(iface['ipv4_address']).is_loopback())
    return iface['name'] == 'lo' or is_loopback

def list_network_interfaces():
    iface_names = os.listdir('/sys/class/net')
    ifaces = [_get_interface_info(name)
            for name in iface_names
            if _is_device(name)]

    # ignore interfaces w/o link information
    interfaces = []
    for iface in ifaces: 
        if iface['mac_address'] and not _is_loopback(iface):
            interfaces.append(iface)
    return interfaces

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
        argument_spec = dict(),
        supports_check_mode=True
    )

    facts = { "custom_facts":{
        "memory_mb": get_physical_memory(),
        "interfaces": list_network_interfaces(),
        "boot_interface": kernel_cmdline().get('BOOTIF') }}

    ansible_facts = {"ansible_facts" : facts}
    module.exit_json(**ansible_facts)


from ansible.module_utils.basic import *  # noqa
if __name__ == '__main__':
    main()

