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

from ironic.drivers import base
from ironic.drivers.modules import agent
from ironic.drivers.modules import fake
from ironic.drivers.modules import pxe
from ironic_staging_drivers.ovirt import ovirt

class PXEAndOvirtDriver(base.BaseDriver):
    """PXE + Ovirt driver.

    NOTE: This driver is meant only for testing environments.

    This driver implements the `core` functionality, combining
    :class:`ironic.drivers.ovirt.OvirtPower` for power on/off and
    reboot of Ovirt virtual machines, with :class:`ironic.driver.pxe.PXE`
    for image deployment. Implementations are in those respective classes;
    this class is merely the glue between them.
    """

    def __init__(self):
        if not importutils.try_import('ovirtsdk'):
            raise exception.DriverLoadError(
                    driver=self.__class__.__name__,
                    reason=_("Unable to import ovirtsdk library"))
        self.power = ovirt.OvirtPower()
        self.deploy = pxe.PXEDeploy()
