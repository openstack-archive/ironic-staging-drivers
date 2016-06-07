# coding=utf-8

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

import time

from oslo_config import cfg
from oslo_log import log as logging

from ironic.common import boot_devices
from ironic.common import exception
from ironic.common.i18n import _
from ironic.common import states
from ironic.conductor import task_manager
from ironic.drivers import base

from amt.client import Client
from requests import ConnectionError

CONF = cfg.CONF

opt_group = cfg.OptGroup(name='amt',
                         title='Options for the AMT power driver')
CONF.register_group(opt_group)
CONF.register_opts(opt_group)

LOG = logging.getLogger(__name__)

REQUIRED_PROPERTIES = {
    'amt_address': _('IP address or host name of the node. Required.'),
    'amt_password': _('Password. Required.'),
}

POWER_MAP = {
    '2': states.POWER_ON,
    '8': states.POWER_OFF,
}

BOOT_DEVICE_MAP = {
    boot_devices.PXE: 'pxe',
    boot_devices.DISK: 'hd',
    boot_devices.CDROM: 'cd',
    boot_devices.BIOS: 'bios',
    boot_devices.SAFE: 'hdsafe',
}

DEFAULT_BOOT_DEVICE = boot_devices.DISK


def amtctrl(driver_info, command, special=''):
    """all interactions with the client object happen here.
    """

    amt_client = Client(driver_info['address'], driver_info['password'])

    command_map = {
        'on': amt_client.power_on_with_device(special),
        'off': amt_client.power_off(),
        'power_state': amt_client.power_status(),
    }

    try:
        response = command_map[command]
    except ConnectionError as e:
        # timeout (network is probably down)
        LOG.error(e)
        raise exception.AMTFailure(cmd=command)
    except KeyError:
        # command attempted that we don't have mapped
        raise NotImplementedError()
    else:
        return response


def _get_power_state(driver_info):
    """call out to client and return the power state.
    """
    try:
        ps = POWER_MAP[amtctrl(driver_info, 'power_state')]
    except KeyError:
        # response isn't in our map so raise PowerStateFailure
        raise exception.PowerStateFailure(pstate=None)
    return ps


def _power_on(driver_info, device=''):
    """turn the power on
    """
    response = amtctrl(driver_info, 'on', device)

    if response == '0':
        return states.POWER_ON
    else:
        return _get_power_state(driver_info)


def _power_off(driver_info):
    """turn the power off
    """
    response = amtctrl(driver_info, 'off')

    if response == '0':
        return states.POWER_ON
    else:
        return _get_power_state(driver_info)


def _parse_driver_info(node):
    """this function seems to verify that the address and password exist in
    the database for the node"""
    address = node.driver_info.get('amt_address')
    password = node.driver_info.get('amt_password')
    if not address or not password:
        raise exception.InvalidParamterValue(_(
            "Missing one or more of the following required parameters: %s."
        ) % REQUIRED_PROPERTIES.keys())
    return {'address': address,
            'password': password}


class AMTPower(base.PowerInterface):
    """The power interface class"""

    def get_properties(self):
        """don't know what this does"""
        return REQUIRED_PROPERTIES

    def validate(self, task):
        _parse_driver_info(task.node)

    def get_power_state(self, task):
        driver_info = _parse_driver_info(task.node)
        return _get_power_state(driver_info)

    @task_manager.require_exclusive_lock
    def set_power_state(self, task, power_state):

        driver_info = _parse_driver_info(task.node)
        driver_internal_info = task.node.driver_internal_info

        if power_state == states.POWER_ON:
            requested_dev = driver_internal_info.get('amt_boot_device')
            if requested_dev:
                state = _power_on(driver_info,
                                  device=BOOT_DEVICE_MAP[requested_dev])
                if not driver_internal_info.get('amt_boot_persistent'):
                    del(driver_internal_info['amt_boot_device'])
                    del(driver_internal_info['amt_boot_persistent'])
                    task.node.driver_internal_info = driver_internal_info
            else:
                state = _power_on(driver_info)
        elif power_state == states.POWER_OFF:
            state = _power_off(driver_info)
        else:
            raise exception.InvalidParameterValue(
                _("set_power_state called with "
                  " invalid power state %s.") % power_state
            )

        if state != power_state:
            raise exception.PowerStateFailure(pstate=power_state)

    @task_manager.require_exclusive_lock
    def reboot(self, task):
        self.set_power_state(task, states.POWER_OFF)
        time.sleep(3)
        self.set_power_state(task, states.POWER_ON)


class AMTManagement(base.ManagementInterface):
    """Management Interface class"""

    def get_properties(self):
        """ get properties method"""
        return REQUIRED_PROPERTIES

    def validate(self, task):
        """validates that you have enough information to manage a node"""
        _parse_driver_info(task.node)

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
            device = DEFAULT_BOOT_DEVICE
            persistent = True
        return {'boot_device': device,
                'persistent': persistent}

    def get_sensors_data(self, task):
        raise NotImplementedError()
