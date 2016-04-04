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

from ironic.common import driver_factory
from ironic.common import exception as ironic_exception
from ironic.common import states
from ironic.conductor import task_manager
from ironic.tests.unit.conductor import mgr_utils
from ironic.tests.unit.db import base as db_base
from ironic.tests.unit.objects import utils as obj_utils
import mock

from ironic_staging_drivers.ovirt import ovirt as ovirt_power


def _ovirt_info():
    driver_info = {'ovirt_host': '127.0.1.1',
                   'ovirt_user': 'jhendrix@internal',
                   'ovirt_password': 'changeme',
                   'ovirt_vm_name': 'jimi',
                   'vm_name': 'jimi'}
    return driver_info


@mock.patch.object(time, 'sleep', lambda *_: None)
class oVirtDriverTestCase(db_base.DbTestCase):

    def setUp(self):
        super(oVirtDriverTestCase, self).setUp()
        mgr_utils.mock_the_extension_manager(driver='fake_ovirt_fake')
        self.driver = driver_factory.get_driver('fake_ovirt_fake')
        self.node = obj_utils.create_test_node(self.context,
                                               driver='fake_ovirt_fake',
                                               driver_info=_ovirt_info())
        self.port = obj_utils.create_test_port(self.context,
                                               node_id=self.node.id)

    def test__parse_parameters(self):
        with task_manager.acquire(
                self.context, self.node.uuid, shared=True) as task:
            params = ovirt_power._parse_driver_info(task.node)
            self.assertEqual('127.0.1.1', params['host'])
            self.assertEqual('jhendrix@internal', params['user'])
            self.assertEqual('changeme', params['password'])

    def test_get_properties(self):
        expected = ovirt_power.PROPERTIES
        with task_manager.acquire(
                self.context, self.node.uuid, shared=True) as task:
            self.assertEqual(expected, task.driver.get_properties())

    def test_get_power_state(self):
        with task_manager.acquire(
                self.context, self.node.uuid, shared=True) as task:
            task.node.power_state = states.POWER_ON
            pstate = task.driver.power.get_power_state(task)
            self.assertEqual(states.POWER_ON, pstate)

    def test_get_power_state_nostate(self):
        with task_manager.acquire(
                self.context, self.node.uuid, shared=True) as task:
            task.node.power_state = states.NOSTATE
            pstate = task.driver.power.get_power_state(task)
            self.assertEqual(states.POWER_OFF, pstate)

    @mock.patch.object(ovirt_power.oVirtPower, 'set_power_state',
                       autospec=True, spec_set=True)
    def test_set_power_state_power_on(self, mock_power):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.power.set_power_state(task, states.POWER_ON)
            mock_power.assert_called_once_with(task.driver.power, task,
                                               states.POWER_ON)

    @mock.patch.object(ovirt_power.LOG, 'info', autospec=True, spec_set=True)
    @mock.patch.object(ovirt_power.oVirtPower, 'set_power_state',
                       autospec=True, spec_set=True)
    def test_set_power_state_power_off(self, mock_power, mock_log):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.power.set_power_state(task, states.POWER_OFF)
            mock_power.assert_called_once_with(task.driver.power, task,
                                               states.POWER_OFF)

    @mock.patch.object(ovirt_power.oVirtPower, 'set_power_state',
                       autospec=True, spec_set=True)
    def test_set_power_state_power_fail(self, mock_magic):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(ironic_exception.InvalidParameterValue,
                              task.driver.power.set_power_state,
                              task, 'wrong-state')

    @mock.patch.object(ovirt_power.LOG, 'info', autospec=True, spec_set=True)
    @mock.patch.object(ovirt_power.oVirtPower, 'set_power_state',
                       autospec=True, spec_set=True)
    def test_reboot(self, mock_power, mock_log):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.power.reboot(task)
            mock_log.assert_called_once_with(mock.ANY, self.node.uuid)
            mock_power.assert_called_once_with(task.driver.power, task,
                                               states.POWER_ON)

    def test_get_supported_power_states(self):
        with task_manager.acquire(
                self.context, self.node.uuid, shared=True) as task:
            pstate = task.driver.power.get_supported_power_states(task)
            self.assertEqual([states.POWER_ON, states.POWER_OFF, states.REBOOT],
                             pstate)
