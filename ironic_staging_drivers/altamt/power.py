# Copyright 2016 Hewlett Packard Enterprise Development LP
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
import time
from ironic.drivers import base
from ironic.common.i18n import _
from ironic.common import exception
from ironic.conductor import task_manager
from ironic.common import states

import common


class AMTPower(base.PowerInterface):
    """The power interface class"""

    def get_properties(self):
        """don't know what this does"""
        return common.REQUIRED_PROPERTIES

    def validate(self, task):
        common._parse_driver_info(task.node)

    def get_power_state(self, task):
        driver_info = common._parse_driver_info(task.node)
        return common._get_power_state(driver_info)

    @task_manager.require_exclusive_lock
    def set_power_state(self, task, power_state):
        """"""
        driver_info = common._parse_driver_info(task.node)
        driver_internal_info = task.node.driver_internal_info

        if power_state == states.POWER_ON:
            requested_dev = driver_internal_info.get('amt_boot_device')
            if requested_dev:
                state = common._power_on(
                    driver_info,
                    device=common.BOOT_DEVICE_MAP[requested_dev]
                )

                if not driver_internal_info.get('amt_boot_persistent'):
                    del(driver_internal_info['amt_boot_device'])
                    del(driver_internal_info['amt_boot_persistent'])
                    task.node.driver_internal_info = driver_internal_info
            else:
                state = common._power_on(driver_info)
        elif power_state == states.POWER_OFF:
            state = common._power_off(driver_info)
        else:
            raise exception.InvalidParameterValue(
                _("set_power_state called with "
                  " invalid power state %s.") % power_state
            )

        if state != power_state:
            raise exception.PowerStateFailure(pstate=power_state)

    @task_manager.require_exclusive_lock
    def reboot(self, task):
        self.set_power_state(task, states.POWER_OFF)
        time.sleep(3)
        self.set_power_state(task, states.POWER_ON)
