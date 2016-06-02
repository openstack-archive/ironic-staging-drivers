#!/usr/bin/python
# -*- coding: utf-8 -*-
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

import json
import sys
import time

import netifaces
import requests


_GET_ADDR_MAX_ITERATION = 50
_POST_CALLBACK_MAX_ITERATION =50
_RETRY_INTERVAL = 5


def _process_error(message):
    sys.stderr.write(message)
    sys.stderr.write('\n')
    sys.exit(1)


def _parse_kernel_cmdline():
    """Parse linux kernel command line"""
    with open('/proc/cmdline', 'rt') as f:
        cmdline = f.read()
    parameters = {}
    for p in cmdline.split():
        name, _, value = p.partition('=')
        parameters[name] = value
    return parameters

def _get_interface_ip(mac_addr):
    """"Get IP address of interface by mac."""
    interfaces = netifaces.interfaces()
    for iface in interfaces:
        addresses = netifaces.ifaddresses(iface)
        link_addresses = addresses.get(netifaces.AF_LINK, [])
        for link_addr in link_addresses:
            if link_addr.get('addr') == mac_addr:
                ip_addresses = addresses.get(netifaces.AF_INET)
                if ip_addresses:
                    # NOTE: return first address, ironic API does not
                    # support multiple
                    return ip_addresses[0].get('addr')
                else:
                    break

def main():
    """Script informs Ironic that bootstrap loading is done.

    There are three mandatory parameters in kernel command line.
    Ironic prepares these two:
    'ironic_api_url' - URL of Ironic API service,
    'deployment_id' - UUID of the node in Ironic.
    Passed from PXE boot loader:
    'BOOTIF' - MAC address of the boot interface.
    """
    kernel_params = _parse_kernel_cmdline()
    api_url = kernel_params.get('ironic_api_url')
    deployment_id = kernel_params.get('deployment_id')
    if api_url is None or deployment_id is None:
        _process_error('Mandatory parameter ("ironic_api_url" or '
                       '"deployment_id") is missing.')

    boot_mac = kernel_params.get('BOOTIF')
    if boot_mac is None:
        _process_error('Cannot define boot interface, "BOOTIF" parameter is '
                       'missing.')

    # There is a difference in syntax in BOOTIF variable between pxe and ipxe
    # boot with Ironic. For pxe boot the the leading `01-' denotes the device type
    # (Ethernet) and is not a part of the MAC address
    if boot_mac.startswith('01-'):
        boot_mac = boot_mac[3:].replace('-', ':')

    for n in range(_GET_ADDR_MAX_ITERATION):
        boot_ip = _get_interface_ip(boot_mac)
        if boot_ip is not None:
            break
        time.sleep(_RETRY_INTERVAL)
    else:
        _process_error('Cannot find IP address of boot interface.')

    data = {"callback_url": "ssh://" + boot_ip}

    passthru = '%(api-url)s/v1/nodes/%(deployment_id)s/vendor_passthru' \
               '/heartbeat' % {'api-url': api_url,
                               'deployment_id': deployment_id}

    for attempt in range(_POST_CALLBACK_MAX_ITERATION):
        try:
            resp = requests.post(passthru, data=json.dumps(data),
                                 headers={'Content-Type': 'application/json',
                                          'Accept': 'application/json'})
        except Exception as e:
            error = str(e)
        else:
            if resp.status_code != 202:
                error= ('Wrong status code %d returned from Ironic API' %
                        resp.status_code)
            else:
                break

        if attempt == (_POST_CALLBACK_MAX_ITERATION - 1):
            _process_error(error)

        time.sleep(_RETRY_INTERVAL)


if __name__ == '__main__':
    sys.exit(main())

