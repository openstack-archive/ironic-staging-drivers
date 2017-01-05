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

# Supported hints:
# "model" (STRING): device identifier
# "vendor" (STRING): device vendor
# "serial" (STRING): disk serial number
# "size" (INT): size of the device in GiB
# "wwn" (STRING): unique storage identifier
# "wwn_with_extension" (STRING): unique storage identifier with the vendor
# extension appended
# "wwn_vendor_extension" (STRING): unique vendor storage identifier
# "rotational" (BOOLEAN): whether it’s a rotational device or not
# "name" (STRING): the device name

# Example of ansible device facts:
# "ansible_devices": {
#     "sda": {
#         "model": "ST1000DM003-1SB1",
#         "removable": "0",
#         "rotational": "1",
#         "sas_address": null,
#         "sas_device_handle": null,
#         "scheduler_mode": "deadline",
#         "sectors": "1953525168",
#         "sectorsize": "512",
#         "size": "931.51 GB",
#         "support_discard": "0",
#         "vendor": "ATA"
#     }
# }

from ironic_lib import utils as il_utils
from oslo_utils import strutils

GIB = 1 << 30

EXTRA_PARAMS = set(['wwn', 'serial', 'wwn_with_extension',
                    'wwn_vendor_extension'])


# NOTE: ansible calculates device size as float with 2-digits precision,
# Ironic requires size in GiB, if we will use ansible size parameter
# a bug is possible for devices > 1 TB
def size_gib(device_info):
    sectors = device_info.get('sectors')
    sectorsize = device_info.get('sectorsize')
    if sectors is None or sectorsize is None:
        return

    return (int(sectors) * int(sectorsize)) // GIB


def create_devices_list(devices, devices_wwn):
    dev_list = []
    for name, info in devices.items():
        merged_info = {'name': '/dev/' + name}
        merged_info['model'] = info.get('model')
        merged_info['vendor'] = info.get('vendor')
        rotational = info.get('rotational')
        if rotational is not None:
            rotational = strutils.bool_from_string(rotational, strict=True)
        merged_info['rotational'] = rotational
        if name in devices_wwn:
            merged_info.update(devices_wwn[name])

        merged_info['size'] = size_gib(info)
        dev_list.append(merged_info)

    return dev_list


def main():
    module = AnsibleModule(
        argument_spec=dict(
            root_device_hints=dict(required=True, type='dict'),
            ansible_devices=dict(required=True, type='dict'),
            ansible_devices_wwn=dict(required=True, type='dict')
        ),
        supports_check_mode=True)

    hints = module.params['root_device_hints']
    devices = module.params['ansible_devices']
    devices_wwn = module.params['ansible_devices_wwn']

    if devices_wwn is None:
        extra = set(hints) & EXTRA_PARAMS
        if extra:
            module.fail_json(msg='Extra hints (supported by additional ansible'
                             ' module) are set but this information can not be'
                             ' collected. Extra hints: %s' % ', '.join(extra))

    devices_list = create_devices_list(devices, devices_wwn or {})

    device = None
    try:
        device = il_utils.match_root_device_hints(devices_list, hints)
    except ValueError:
        pass

    if device is None:
        module.fail_json(msg='Root device hints are set, but none of the '
                         'devices satisfy them. Collected devices info: %s'
                         % devices_list)

    ret_data = {'ansible_facts': {'ironic_root_device': device['name']}}
    module.exit_json(**ret_data)


from ansible.module_utils.basic import *  # noqa
if __name__ == '__main__':
    main()
