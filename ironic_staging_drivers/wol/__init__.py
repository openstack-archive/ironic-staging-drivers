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

from ironic.drivers import generic
from ironic.drivers.modules import fake
from ironic.drivers.modules import noop_mgmt

from ironic_staging_drivers.wol import power as wol_power


class WOLHardware(generic.GenericHardware):
    """WOL hardware type.

    Uses wake on lan for power on.
    """

    @property
    def supported_management_interfaces(self):
        """List of supported management interfaces."""
        return [noop_mgmt.NoopManagement, fake.FakeManagement]

    @property
    def supported_power_interfaces(self):
        """List of supported power interfaces."""
        return [wol_power.WakeOnLanPower]
