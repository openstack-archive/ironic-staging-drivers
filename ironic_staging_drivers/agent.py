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
from ironic.drivers import base
from ironic.drivers.modules import agent
from ironic.drivers.modules import pxe
from oslo_utils import importutils

from ironic_staging_drivers.iboot import power as iboot_power
from ironic_staging_drivers.wol import power as wol_power


class PXEAndWakeOnLanAgentDriver(base.BaseDriver):
    """PXE + WakeOnLan + Agent driver.

    This driver implements the `core` functionality, combining
    :class:`ironic.drivers.modules.pxe.PXEBoot` for boot and
    :class:`ironic_staging_drivers.wol.power.WakeOnLanPower` for power
    and :class:`ironic.drivers.modules.agent.AgentDeploy` for
    image deployment.  Implementations are in those respective classes;
    this class is merely the glue between them.

    """
    def __init__(self):
        self.boot = pxe.PXEBoot()
        self.power = wol_power.WakeOnLanPower()
        self.deploy = agent.AgentDeploy()
        self.vendor = agent.AgentVendorInterface()


class PXEAndIBootAgentDriver(base.BaseDriver):
    """Agent + IBoot PDU driver.

    This driver implements the `core` functionality, combining
    :class:`ironic_staging_drivers.iboot.power.IBootPower` for power
    on/off and reboot with
    :class:'ironic.driver.modules.agent.AgentDeploy' (for image deployment.)
    Implementations are in those respective classes;
    this class is merely the glue between them.
    """
    def __init__(self):
        if not importutils.try_import('iboot'):
            raise ironic_exception.DriverLoadError(
                driver=self.__class__.__name__,
                reason=_("Unable to import iboot library"))
        self.power = iboot_power.IBootPower()
        self.boot = pxe.PXEBoot()
        self.deploy = agent.AgentDeploy()
        self.vendor = agent.AgentVendorInterface()
