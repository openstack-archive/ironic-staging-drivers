# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ironic.drivers import base
from ironic.drivers import ipmi
from ironic.drivers.modules import fake
from ironic.drivers.modules import ipmitool
from ironic.drivers.modules import pxe

from ironic_staging_drivers.ansible import deploy as ansible_deploy
from ironic_staging_drivers.ansible import vendor as ansible_vendor
from ironic_staging_drivers.libvirt import power as libvirt_power


class AnsibleAndIPMIToolDriver(base.BaseDriver):
    """Ansible + Ipmitool driver."""

    def __init__(self):
        self.power = ipmitool.IPMIPower()
        self.boot = pxe.PXEBoot()
        self.deploy = ansible_deploy.AnsibleDeploy()
        self.management = ipmitool.IPMIManagement()
        self.vendor = ipmitool.VendorPassthru()


class FakeAnsibleDriver(base.BaseDriver):
    """Ansible + Fake driver"""

    def __init__(self):
        self.power = fake.FakePower()
        self.boot = pxe.PXEBoot()
        self.deploy = ansible_deploy.AnsibleDeploy()
        self.management = fake.FakeManagement()
        self.vendor = ansible_vendor.AnsibleDeployPassthru()


class AnsibleAndLibvirtDriver(base.BaseDriver):
    """Ansible + Libvirt driver.

    NOTE: This driver is meant only for testing environments.
    """

    def __init__(self):
        self.power = libvirt_power.LibvirtPower()
        self.boot = pxe.PXEBoot()
        self.deploy = ansible_deploy.AnsibleDeploy()
        self.management = libvirt_power.LibvirtManagement()


# NOTE(yuriyz): This class is not a "real" hardware.
# Added to support the ansible deploy interface in 'ipmi' hardware
class AnsibleDeployIPMI(ipmi.IPMIHardware):

    @property
    def supported_deploy_interfaces(self):
        """List of supported deploy interfaces."""
        return (super(AnsibleDeployIPMI, self).supported_deploy_interfaces +
                [ansible_deploy.AnsibleDeploy])

    @property
    def supported_vendor_interfaces(self):
        """List of supported vendor interfaces."""
        return (super(AnsibleDeployIPMI, self).supported_vendor_interfaces +
                [ansible_vendor.AnsibleDeployPassthru])
