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

import collections
import os

try:
    import pyudev
    HAS_PYUDEV = True
    CONTEXT = pyudev.Context()
except ImportError:
    HAS_PYUDEV = False


COLLECT_INFO = (('wwn', 'WWN'), ('serial', 'SERIAL_SHORT'),
                ('wwn_with_extension', 'WWN_WITH_EXTENSION'),
                ('wwn_vendor_extension', 'WWN_VENDOR_EXTENSION'))


def get_devices_params(devices):

    dev_dict = collections.defaultdict(dict)

    for device in devices:
        try:
            # We need one extra parameter for hints that ironic supports
            dev_dict[device]['hctl'] = os.listdir(
                '/sys/block/%s/device/scsi_device' % device)[0]
        except (OSError, IndexError):
            pass

        if HAS_PYUDEV:
            name = '/dev/' + device
            try:
                udev = pyudev.Device.from_device_file(CONTEXT, name)
            except (ValueError, EnvironmentError, pyudev.DeviceNotFoundError):
                pass
            else:
                for key, udev_key in COLLECT_INFO:
                    dev_dict[device][key] = udev.get('ID_%s' % udev_key)

    return {"ansible_facts": {"devices_wwn": dev_dict}}


def main():
    module = AnsibleModule(
        argument_spec=dict(
            devices=dict(required=True, type='list'),
        ),
        supports_check_mode=True,
    )

    devices = module.params['devices']
    data = get_devices_params(devices)
    module.exit_json(**data)


from ansible.module_utils.basic import *  # noqa
if __name__ == '__main__':
    main()
