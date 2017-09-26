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
from ironic.common.i18n import _
from ironic.drivers import base
from ironic.drivers import generic
from ironic.drivers.modules import agent
from ironic.drivers.modules import fake
from ironic.drivers.modules import iscsi_deploy
from ironic.drivers.modules import pxe
from oslo_log import log as logging
from oslo_utils import importutils

from ironic_staging_drivers.iboot import power as iboot_power

LOG = logging.getLogger(__name__)


class FakeIBootFakeDriver(base.BaseDriver):
    """Fake iBoot driver."""

    def __init__(self):
        if not importutils.try_import('iboot'):
            raise ironic_exception.DriverLoadError(
                driver=self.__class__.__name__,
                reason=_("Unable to import iboot library"))
        self.boot = fake.FakeBoot()
        self.power = iboot_power.IBootPower()
        self.deploy = fake.FakeDeploy()


class PXEIBootISCSIDriver(base.BaseDriver):
    """PXE + IBoot PDU driver + iSCSI driver.

    This driver implements the `core` functionality, combining
    :class:`ironic.drivers.modules.pxe.PXEBoot` for boot and
    :class:`ironic_staging_drivers.iboot.power.IBootPower` for power
    and :class:`ironic.drivers.modules.iscsi_deploy.ISCSIDeploy` for
    image deployment. Implementations are in those respective classes;
    this class is merely the glue between them.
    """
    def __init__(self):
        LOG.warning("This driver is deprecated and will be removed "
                    "in the Rocky release. "
                    "Use 'staging-iboot' hardware type instead.")
        if not importutils.try_import('iboot'):
            raise ironic_exception.DriverLoadError(
                driver=self.__class__.__name__,
                reason=_("Unable to import iboot library"))
        self.power = iboot_power.IBootPower()
        self.boot = pxe.PXEBoot()
        self.deploy = iscsi_deploy.ISCSIDeploy()


class PXEIBootAgentDriver(base.BaseDriver):
    """PXE + IBoot PDU driver + Agent driver.

    This driver implements the `core` functionality, combining
    :class:`ironic.drivers.modules.pxe.PXEBoot` for boot and
    :class:`ironic_staging_drivers.iboot.power.IBootPower` for power
    and :class:'ironic.driver.modules.agent.AgentDeploy' for image
    deployment. Implementations are in those respective classes;
    this class is merely the glue between them.
    """
    def __init__(self):
        LOG.warning("This driver is deprecated and will be removed "
                    "in the Rocky release. "
                    "Use 'staging-iboot' hardware type instead.")
        if not importutils.try_import('iboot'):
            raise ironic_exception.DriverLoadError(
                driver=self.__class__.__name__,
                reason=_("Unable to import iboot library"))
        self.power = iboot_power.IBootPower()
        self.boot = pxe.PXEBoot()
        self.deploy = agent.AgentDeploy()


class IBootHardware(generic.GenericHardware):
    """IBoot hardware type.

    Uses IBoot for power management.
    """

    @property
    def supported_management_interfaces(self):
        """List of supported management interfaces."""
        return [fake.FakeManagement]

    @property
    def supported_power_interfaces(self):
        """List of supported power interfaces."""
        return [iboot_power.IBootPower]
