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

from ironic.drivers import generic

from ironic_staging_drivers.libvirt import power


class LibvirtHardware(generic.GenericHardware):
    """Libvirt hardware type.

    Uses Libvirt for power and management.
    """

    @property
    def supported_management_interfaces(self):
        """List of supported management interfaces."""
        return [power.LibvirtManagement]

    @property
    def supported_power_interfaces(self):
        """List of supported power interfaces."""
        return [power.LibvirtPower]
