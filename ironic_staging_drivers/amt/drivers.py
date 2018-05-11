# Copyright 2016 Intel Corporation.
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
from ironic.drivers.modules import agent

from ironic_staging_drivers.amt import deploy as amt_deploy
from ironic_staging_drivers.amt import management as amt_management
from ironic_staging_drivers.amt import power as amt_power


class AMTHardware(generic.GenericHardware):
    """AMT hardware type.

    Hardware type for Intel AMT.
    """

    @property
    def supported_deploy_interfaces(self):
        """List of supported deploy interfaces."""
        return [amt_deploy.AMTISCSIDeploy, agent.AgentDeploy]

    @property
    def supported_management_interfaces(self):
        """List of supported management interfaces."""
        return [amt_management.AMTManagement]

    @property
    def supported_power_interfaces(self):
        """List of supported power interfaces."""
        return [amt_power.AMTPower]
