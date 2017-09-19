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

from ironic.drivers import base
from ironic.drivers import generic
from ironic.drivers.modules import agent
from ironic.drivers.modules import fake
from ironic.drivers.modules import iscsi_deploy
from ironic.drivers.modules import pxe
from oslo_log import log as logging

from ironic_staging_drivers.wol import power as wol_power

LOG = logging.getLogger(__name__)


class FakeWakeOnLanFakeDriver(base.BaseDriver):
    """Fake Wake-On-Lan driver."""

    def __init__(self):
        self.boot = fake.FakeBoot()
        self.power = wol_power.WakeOnLanPower()
        self.deploy = fake.FakeDeploy()


class PXEWakeOnLanISCSIDriver(base.BaseDriver):
    """PXE + WakeOnLan + iSCSI driver.

    This driver implements the `core` functionality, combining
    :class:`ironic.drivers.modules.pxe.PXEBoot` for boot and
    :class:`ironic_staging_drivers.wol.power.WakeOnLanPower` for power
    and :class:`ironic.drivers.modules.iscsi_deploy.ISCSIDeploy` for
    image deployment.  Implementations are in those respective classes;
    this class is merely the glue between them.

    """
    def __init__(self):
        LOG.warning("This driver is deprecated and will be removed "
                    "in the Rocky release. "
                    "Use 'staging-wol' hardware type instead.")
        self.boot = pxe.PXEBoot()
        self.power = wol_power.WakeOnLanPower()
        self.deploy = iscsi_deploy.ISCSIDeploy()


class PXEWakeOnLanAgentDriver(base.BaseDriver):
    """PXE + WakeOnLan + Agent driver.

    This driver implements the `core` functionality, combining
    :class:`ironic.drivers.modules.pxe.PXEBoot` for boot and
    :class:`ironic_staging_drivers.wol.power.WakeOnLanPower` for power
    and :class:`ironic.drivers.modules.agent.AgentDeploy` for
    image deployment.  Implementations are in those respective classes;
    this class is merely the glue between them.

    """
    def __init__(self):
        LOG.warning("This driver is deprecated and will be removed "
                    "in the Rocky release. "
                    "Use 'staging-wol' hardware type instead.")
        self.boot = pxe.PXEBoot()
        self.power = wol_power.WakeOnLanPower()
        self.deploy = agent.AgentDeploy()


class WOLHardware(generic.GenericHardware):
    """WOL hardware type.

    Uses wake on lan for power on.
    """

    @property
    def supported_management_interfaces(self):
        """List of supported management interfaces."""
        return [fake.FakeManagement]

    @property
    def supported_power_interfaces(self):
        """List of supported power interfaces."""
        return [wol_power.WakeOnLanPower]
