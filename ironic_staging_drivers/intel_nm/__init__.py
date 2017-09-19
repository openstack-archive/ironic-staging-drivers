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
from ironic.drivers import ipmi
from ironic.drivers.modules import agent
from ironic.drivers.modules import fake
from ironic.drivers.modules import inspector
from ironic.drivers.modules import ipmitool
from ironic.drivers.modules import pxe
from ironic.drivers import utils
from oslo_log import log as logging

from ironic_staging_drivers.intel_nm import nm_vendor

LOG = logging.getLogger(__name__)


class FakeIntelNMDriver(base.BaseDriver):
    """Fake Intel NM driver."""

    def __init__(self):
        self.power = fake.FakePower()
        self.deploy = fake.FakeDeploy()
        self.vendor = nm_vendor.IntelNMVendorPassthru()


class AgentAndIPMIToolIntelNMDriver(base.BaseDriver):
    """Agent + IPMITool driver with Intel NM policies."""
    def __init__(self):
        LOG.warning("This driver is deprecated and will be removed "
                    "in the Rocky release. "
                    "Use 'staging-nm' hardware type instead.")
        self.power = ipmitool.IPMIPower()
        self.boot = pxe.PXEBoot()
        self.deploy = agent.AgentDeploy()
        self.management = ipmitool.IPMIManagement()
        self.console = ipmitool.IPMIShellinaboxConsole()
        self.ipmi_vendor = ipmitool.VendorPassthru()
        self.nm_vendor = nm_vendor.IntelNMVendorPassthru()
        self.mapping = {'send_raw': self.ipmi_vendor,
                        'bmc_reset': self.ipmi_vendor,
                        'control_nm_policy': self.nm_vendor,
                        'set_nm_policy': self.nm_vendor,
                        'get_nm_policy': self.nm_vendor,
                        'remove_nm_policy': self.nm_vendor,
                        'set_nm_policy_suspend': self.nm_vendor,
                        'get_nm_policy_suspend': self.nm_vendor,
                        'remove_nm_policy_suspend': self.nm_vendor,
                        'get_nm_capabilities': self.nm_vendor,
                        'get_nm_version': self.nm_vendor,
                        'get_nm_statistics': self.nm_vendor,
                        'reset_nm_statistics': self.nm_vendor}
        self.vendor = utils.MixinVendorInterface(self.mapping)
        self.raid = agent.AgentRAID()
        self.inspect = inspector.Inspector.create_if_enabled(
            'AgentAndIPMIToolDriver')


class IntelNMHardware(ipmi.IPMIHardware):
    """Intel NM hardware type.

    Hardware type with Intel Node Manager vendor methods.
    """

    @property
    def supported_vendor_interfaces(self):
        """List of supported vendor interfaces."""
        return (super(IntelNMHardware, self).supported_vendor_interfaces +
                [nm_vendor.IntelNMVendorPassthru])
