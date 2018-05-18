# Copyright 2017 Red Hat, Inc.
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
class OVirtDriverTestCase(db_base.DbTestCase):

    def setUp(self):
        super(OVirtDriverTestCase, self).setUp()
        self.config(enabled_power_interfaces='staging-ovirt',
                    enabled_management_interfaces='staging-ovirt',
                    enabled_hardware_types=['staging-ovirt'])
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

    @mock.patch.object(ovirt_power, "sdk", create=True)
    def test_getvm_nounicode(self, sdk):
        self.node['driver_info']['ovirt_address'] = u'127.0.0.1'
        driver_info = ovirt_power._parse_driver_info(self.node)

        ovirt_power._getvm(driver_info)
        ovirt_power.sdk.Connection.assert_called_with(
            ca_file=None, insecure='False', password='changeme',
            url=b'https://127.0.0.1/ovirt-engine/api',
            username='jhendrix@internal'
        )
        url = ovirt_power.sdk.Connection.mock_calls[0][-1]['url']
        self.assertEqual(type(b''), type(url))

    @mock.patch.object(ovirt_power, "sdk", create=True)
    def test_getvm_unicode(self, sdk):
        self.node['driver_info']['ovirt_address'] = u'host\u20141'
        driver_info = ovirt_power._parse_driver_info(self.node)

        ovirt_power._getvm(driver_info)
        ovirt_power.sdk.Connection.assert_called_with(
            ca_file=None, insecure='False', password='changeme',
            url=u'https://host\u20141/ovirt-engine/api',
            username='jhendrix@internal'
        )
        url = ovirt_power.sdk.Connection.mock_calls[0][-1]['url']
        self.assertEqual(type(u''), type(url))

    def test_get_properties(self):
        expected = list(ovirt_power.PROPERTIES.keys())
        with task_manager.acquire(
                self.context, self.node.uuid, shared=False) as task:
            driver_properties = [prop for prop in task.driver.get_properties()
                                 if prop in expected]
            self.assertEqual(sorted(expected), sorted(driver_properties))

    @mock.patch.object(ovirt_power.OVirtPower, 'set_power_state',
                       autospec=True, spec_set=True)
    def test_set_power_state_power_on(self, mock_power):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.power.set_power_state(task, states.POWER_ON)
            mock_power.assert_called_once_with(task.driver.power, task,
                                               states.POWER_ON)

    @mock.patch.object(ovirt_power.OVirtPower, 'set_power_state',
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

    @mock.patch.object(ovirt_power.OVirtManagement, 'get_boot_device',
                       return_value='hd')
    def test_get_boot_device(self, mock_management):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            boot_dev = task.driver.management.get_boot_device(task)
            self.assertEqual('hd', boot_dev)

    @mock.patch.object(ovirt_power.OVirtManagement, 'set_boot_device',
                       autospec=True, spec_set=True)
    def test_set_boot_device(self, mock_power):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.management.set_boot_device(task, boot_devices.DISK)
            mock_power.assert_called_once_with(task.driver.management, task,
                                               boot_devices.DISK)

    @mock.patch.object(ovirt_power, '_getvm')
    def test_set_reboot_when_down(self, mock_vm):
        mock_vm.return_value.get.return_value.status.value = 'down'

        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.power.reboot(task)
            mock_vm.return_value.start.assert_called_once()

    @mock.patch.object(ovirt_power, '_getvm')
    def test_set_reboot_when_up(self, mock_vm):
        mock_vm.return_value.get.return_value.status.value = 'up'

        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.power.reboot(task)
            mock_vm.return_value.reboot.assert_called_once()
