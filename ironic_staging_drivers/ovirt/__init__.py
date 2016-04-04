# -*- encoding: utf-8 -*-
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
"""
PXE Driver and supporting meta-classes.
"""


from ironic.common import exception
from ironic.drivers import base
from ironic.drivers import generic
from ironic.drivers.modules import pxe
from oslo_utils import importutils

from ironic_staging_drivers.ovirt import ovirt


class PXEAndoVirtDriver(base.BaseDriver):
    """PXE + oVirt driver.

    NOTE: This driver is meant only for testing environments.

    This driver implements the `core` functionality, combining
    :class:`ironic.drivers.ovirt.oVirtPower` for power on/off and
    reboot of oVirt virtual machines, with :class:`ironic.driver.pxe.PXE`
    for image deployment. Implementations are in those respective classes;
    this class is merely the glue between them.
    """

    def __init__(self):
        if not importutils.try_import('ovirtsdk4'):
            raise exception.DriverLoadError(driver=self.__class__.__name__,
                                            reason=_("Unable to import"
                                                     "ovirtsdk4 library"))
        self.power = ovirt.oVirtPower()
        self.deploy = pxe.PXEDeploy()


class oVirtHardware(generic.GenericHardware):
    """oVirt hardware type.

    Uses oVirt for power and management.
    """

    @property
    def supported_management_interfaces(self):
        """List of supported management interfaces."""
        return [ovirt.oVirtManagement]

    @property
    def supported_power_interfaces(self):
        """List of supported power interfaces."""
        return [ovirt.oVirtPower]
