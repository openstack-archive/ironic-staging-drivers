# Copyright 2016 Hewlett Packard Enterprise Development LP
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from ironic.common import boot_devices
from ironic.drivers import base
from ironic.common.i18n import _
from ironic.common import exception
import common


class AMTManagement(base.ManagementInterface):
    """Management Interface class"""

    def get_properties(self):
        """ get properties method"""
        return common.REQUIRED_PROPERTIES

    def validate(self, task):
        """validates that you have enough information to manage a node"""
        common._parse_driver_info(task.node)

    def get_supported_boot_devices(self):
        """returns a list of supported boot devices"""
        return [boot_devices.PXE, boot_devices.DISK, boot_devices.CDROM,
                boot_devices.BIOS, boot_devices.SAFE]

    def set_boot_device(self, task, device, persistent=False):
        """set the boot device"""
        if device not in self.get_supported_boot_devices():
            raise exception.InvalidParameterValue(_(
                "Invalid boot device %s specified.") % device)

        # AMT/vPro doesn't support set boot_device persistent, so we have to
        # save amt_boot_device/amt_boot_persistent in driver_internal_info.
        driver_internal_info = task.node.driver_internal_info
        driver_internal_info['amt_boot_device'] = device
        driver_internal_info['amt_boot_persistent'] = persistent
        task.node.driver_internal_info = driver_internal_info
        task.node.save()

    def get_boot_device(self, task):
        """Because amt doesn't have a persistent boot device setting this just
        checks for a driver info setting.. if missing it will return the
        default which is "hd" """
        driver_internal_info = task.node.driver_internal_info
        device = driver_internal_info.get('amt_boot_device')
        persistent = driver_internal_info.get('amt_boot_persistent')
        if not device:
            device = common.DEFAULT_BOOT_DEVICE
            persistent = True
        return {'boot_device': device,
                'persistent': persistent}

    def get_sensors_data(self, task):
        raise NotImplementedError()
