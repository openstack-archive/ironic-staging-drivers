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

"""Test class for oVirt driver module."""

import time

from ironic.common import boot_devices
from ironic.common import states
from ironic.conductor import task_manager
from ironic.tests.unit.conductor import mgr_utils
from ironic.tests.unit.db import base as db_base
from ironic.tests.unit.objects import utils as obj_utils
import mock

from ironic_staging_drivers.ovirt import ovirt as ovirt_power


def _ovirt_info():
    driver_info = {'ovirt_address': '127.0.0.1',
                   'ovirt_username': 'jhendrix@internal',
                   'ovirt_password': 'changeme',
                   'ovirt__insecure': True,
                   'ovirt_ca_file': None,
                   'ovirt_vm_name': 'jimi'}
    return driver_info


@mock.patch.object(time, 'sleep', lambda *_: None)
class oVirtDriverTestCase(db_base.DbTestCase):

    def setUp(self):
        super(oVirtDriverTestCase, self).setUp()
        self.config(enabled_power_interfaces='staging-ovirt',
                    enabled_management_interfaces='staging-ovirt')
        namespace = 'ironic.hardware.types'
        mgr_utils.mock_the_extension_manager(driver='staging-ovirt',
                                             namespace=namespace)
        self.node = obj_utils.create_test_node(self.context,
                                               driver='staging-ovirt',
                                               driver_info=_ovirt_info())
        self.port = obj_utils.create_test_port(self.context,
                                               node_id=self.node.id)

    def test__parse_parameters(self):
        params = ovirt_power._parse_driver_info(self.node)
        self.assertEqual('127.0.0.1', params['ovirt_address'])
        self.assertEqual('jhendrix@internal', params['ovirt_username'])
        self.assertEqual('changeme', params['ovirt_password'])
        self.assertEqual('jimi', params['ovirt_vm_name'])

    def test_get_properties(self):
        expected = list(ovirt_power.PROPERTIES.keys())
        with task_manager.acquire(
                self.context, self.node.uuid, shared=False) as task:
            driver_properties = [prop for prop in task.driver.get_properties()
                                 if prop in expected]
            self.assertEqual(sorted(expected), sorted(driver_properties))

    @mock.patch.object(ovirt_power.oVirtPower, 'set_power_state',
                       autospec=True, spec_set=True)
    def test_set_power_state_power_on(self, mock_power):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.power.set_power_state(task, states.POWER_ON)
            mock_power.assert_called_once_with(task.driver.power, task,
                                               states.POWER_ON)

    @mock.patch.object(ovirt_power.oVirtPower, 'set_power_state',
                       autospec=True, spec_set=True)
    def test_set_power_state_power_off(self, mock_power):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.power.set_power_state(task, states.POWER_OFF)
            mock_power.assert_called_once_with(task.driver.power, task,
                                               states.POWER_OFF)

    def test_get_supported_power_states(self):
        with task_manager.acquire(
                self.context, self.node.uuid, shared=True) as task:
            pstates = task.driver.power.get_supported_power_states(task)
            self.assertEqual([states.POWER_ON, states.POWER_OFF,
                              states.REBOOT], pstates)

    def test_get_supported_boot_devices(self):
        with task_manager.acquire(
                self.context, self.node.uuid, shared=True) as task:
            bdevices = task.driver.management.get_supported_boot_devices(task)
            self.assertEqual([boot_devices.CDROM, boot_devices.DISK,
                              boot_devices.PXE], bdevices)

    @mock.patch.object(ovirt_power.oVirtManagement, 'get_boot_device',
                       return_value='hd')
    def test_get_boot_device(self, mock_management):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            boot_dev = task.driver.management.get_boot_device(task)
            self.assertEqual('hd', boot_dev)

    @mock.patch.object(ovirt_power.oVirtManagement, 'set_boot_device',
                       autospec=True, spec_set=True)
    def test_set_boot_device(self, mock_power):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.management.set_boot_device(task, boot_devices.DISK)
            mock_power.assert_called_once_with(task.driver.management, task,
                                               boot_devices.DISK)
