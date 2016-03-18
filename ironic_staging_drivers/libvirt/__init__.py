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

from ironic.drivers import base
from ironic.drivers.modules import agent
from ironic.drivers.modules import fake
from ironic.drivers.modules import iscsi_deploy
from ironic.drivers.modules import pxe
from ironic_staging_drivers.libvirt import power


class FakeLibvirtFakeDriver(base.BaseDriver):
    """Example implementation of a Driver."""

    def __init__(self):
        self.power = power.LibvirtPower()
        self.deploy = fake.FakeDeploy()
        self.management = power.LibvirtManagement()


class PXELibvirtAgentDriver(base.BaseDriver):
    """PXE + Agent + Libvirt driver.

    NOTE: This driver is meant only for testing environments.

    This driver implements the `core` functionality, combining
    :class:`ironic.drivers.modules.power.LibvirtPower` (for power on/off and
    reboot of virtual machines tunneled over Libvirt API), with
    :class:`ironic.drivers.modules.agent.AgentDeploy` (for image
    deployment). Implementations are in those respective classes; this class
    is merely the glue between them.
    """

    def __init__(self):
        self.power = power.LibvirtPower()
        self.boot = pxe.PXEBoot()
        self.deploy = agent.AgentDeploy()
        self.management = power.LibvirtManagement()
        self.vendor = agent.AgentVendorInterface()
        self.raid = agent.AgentRAID()


class PXELibvirtISCSIDriver(base.BaseDriver):
    """PXE + Libvirt + iSCSI driver.

    This driver implements the `core` functionality, combining
    :class:`ironic.drivers.modules.pxe.PXEBoot` for boot and
    :class:`ironic_staging_drivers.libvirt.LibvirtPower` for power on/off and
    :class:`ironic.drivers.modules.iscsi_deploy.ISCSIDeploy` for image
    deployment. Implementations are in those respective classes; this
    class is merely the glue between them.
    """

    def __init__(self):
        self.power = power.LibvirtPower()
        self.boot = pxe.PXEBoot()
        self.deploy = iscsi_deploy.ISCSIDeploy()
        self.management = power.LibvirtManagement()
        self.vendor = iscsi_deploy.VendorPassthru()
