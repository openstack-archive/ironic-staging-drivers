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
from oslo_config import cfg
from oslo_log import log as logging
from ironic.common.i18n import _
from ironic.common import states
from ironic.common import boot_devices
from ironic.common import exception
from client import Client
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

CLIENT = None


def init_client(driver_info):
    Client(driver_info['address'], driver_info['password'])


def command(driver_info, command, special=''):
    command_map = {
        'on': CLIENT.power_on_with_device(special),
        'off': CLIENT.power_off(),
        'power_state': CLIENT.power_status(),
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
        ps = POWER_MAP[command(driver_info, 'power_state')]
    except KeyError:
        # response isn't in our map so raise PowerStateFailure
        raise exception.PowerStateFailure(pstate=None)
    return ps


def _power_on(driver_info, device=None):
    """Turn the power on
    """
    response = command(driver_info, 'on', device)

    if response == '0':
        return states.POWER_ON
    else:
        return _get_power_state(driver_info)


def _power_off(driver_info):
    """turn the power off
    """
    response = command(driver_info, 'off')

    if response == '0':
        return states.POWER_ON
    else:
        return _get_power_state(driver_info)


def _parse_driver_info(node):
    """This function seems to verify that the address and password exist in
    the database for the node"""
    address = node.driver_info.get('amt_address')
    password = node.driver_info.get('amt_password')
    if not address or not password:
        raise exception.InvalidParamterValue(_(
            "Missing one or more of the following required parameters: %s."
        ) % REQUIRED_PROPERTIES.keys())
    return {'address': address,
            'password': password}
