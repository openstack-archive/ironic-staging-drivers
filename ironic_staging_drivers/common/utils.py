# Copyright 2016 Red Hat, Inc.
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

from ironic.common import exception as ironic_exception

from ironic_staging_drivers.common.i18n import _


def validate_network_port(port, port_name="Port"):
    """Validates the given port.

    :param port: TCP/UDP port.
    :param port_name: Name of the port.
    :returns: An integer port number.
    :raises: InvalidParameterValue, if the port is invalid.
    """
    try:
        port = int(port)
    except ValueError:
        raise ironic_exception.InvalidParameterValue(_(
            '%(port_name)s "%(port)s" is not a valid integer.') %
            {'port_name': port_name, 'port': port})
    if port < 1 or port > 65535:
        raise ironic_exception.InvalidParameterValue(_(
            '%(port_name)s "%(port)s" is out of range. Valid port '
            'numbers must be between 1 and 65535.') %
            {'port_name': port_name, 'port': port})
    return port
