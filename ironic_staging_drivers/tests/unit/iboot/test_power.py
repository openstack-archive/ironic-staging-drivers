# Copyright 2014 Red Hat, Inc.
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

"""Test class for iBoot PDU driver module."""

import types

import mock

from ironic.common import exception as ironic_exception
from ironic.common import states
from ironic.conductor import task_manager
from ironic.drivers.modules import fake
from ironic.tests.unit.db import base as db_base
from ironic.tests.unit.objects import utils as obj_utils

from ironic_staging_drivers.iboot import power as iboot_power


INFO_DICT = {
    'iboot_address': '1.2.3.4',
    'iboot_username': 'admin',
    'iboot_password': 'fake',
}


class IBootPrivateMethodTestCase(db_base.DbTestCase):

    def setUp(self):
        super(IBootPrivateMethodTestCase, self).setUp()
        self.config(max_retry=0, group='iboot')
        self.config(retry_interval=0, group='iboot')

    def test__parse_driver_info_good(self):
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=INFO_DICT)
        info = iboot_power._parse_driver_info(node)
        self.assertIsNotNone(info.get('address'))
        self.assertIsNotNone(info.get('username'))
        self.assertIsNotNone(info.get('password'))
        self.assertIsNotNone(info.get('port'))
        self.assertIsNotNone(info.get('relay_id'))

    def test__parse_driver_info_good_with_explicit_port(self):
        info = dict(INFO_DICT)
        info['iboot_port'] = '1234'
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=info)
        info = iboot_power._parse_driver_info(node)
        self.assertEqual(1234, info.get('port'))

    def test__parse_driver_info_good_with_explicit_relay_id(self):
        info = dict(INFO_DICT)
        info['iboot_relay_id'] = '2'
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=info)
        info = iboot_power._parse_driver_info(node)
        self.assertEqual(2, info.get('relay_id'))

    def test__parse_driver_info_missing_address(self):
        info = dict(INFO_DICT)
        del info['iboot_address']
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=info)
        self.assertRaises(ironic_exception.MissingParameterValue,
                          iboot_power._parse_driver_info,
                          node)

    def test__parse_driver_info_missing_username(self):
        info = dict(INFO_DICT)
        del info['iboot_username']
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=info)
        self.assertRaises(ironic_exception.MissingParameterValue,
                          iboot_power._parse_driver_info,
                          node)

    def test__parse_driver_info_missing_password(self):
        info = dict(INFO_DICT)
        del info['iboot_password']
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=info)
        self.assertRaises(ironic_exception.MissingParameterValue,
                          iboot_power._parse_driver_info,
                          node)

    def test__parse_driver_info_bad_port(self):
        info = dict(INFO_DICT)
        info['iboot_port'] = 'not-integer'
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=info)
        self.assertRaises(ironic_exception.InvalidParameterValue,
                          iboot_power._parse_driver_info,
                          node)

    def test__parse_driver_info_bad_relay_id(self):
        info = dict(INFO_DICT)
        info['iboot_relay_id'] = 'not-integer'
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=info)
        self.assertRaises(ironic_exception.InvalidParameterValue,
                          iboot_power._parse_driver_info,
                          node)

    @mock.patch.object(iboot_power, '_get_connection', autospec=True)
    def test__power_status_on(self, mock_get_conn):
        mock_connection = mock.MagicMock(spec_set=['get_relays'])
        mock_connection.get_relays.return_value = [True]
        mock_get_conn.return_value = mock_connection
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=INFO_DICT)
        info = iboot_power._parse_driver_info(node)

        status = iboot_power._power_status(info)

        self.assertEqual(states.POWER_ON, status)
        mock_get_conn.assert_called_once_with(info)
        mock_connection.get_relays.assert_called_once_with()

    @mock.patch.object(iboot_power, '_get_connection', autospec=True)
    def test__power_status_off(self, mock_get_conn):
        mock_connection = mock.MagicMock(spec_set=['get_relays'])
        mock_connection.get_relays.return_value = [False]
        mock_get_conn.return_value = mock_connection
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=INFO_DICT)
        info = iboot_power._parse_driver_info(node)

        status = iboot_power._power_status(info)

        self.assertEqual(states.POWER_OFF, status)
        mock_get_conn.assert_called_once_with(info)
        mock_connection.get_relays.assert_called_once_with()

    @mock.patch.object(iboot_power, '_get_connection', autospec=True)
    def test__power_status_ironic_exception(self, mock_get_conn):
        mock_connection = mock.MagicMock(spec_set=['get_relays'])
        mock_connection.get_relays.return_value = None
        mock_get_conn.return_value = mock_connection
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=INFO_DICT)
        info = iboot_power._parse_driver_info(node)

        status = iboot_power._power_status(info)
        self.assertEqual(states.ERROR, status)
        mock_get_conn.assert_called_once_with(info)
        mock_connection.get_relays.assert_called_once_with()

    @mock.patch.object(iboot_power, '_get_connection', autospec=True)
    def test__power_status_ironic_exception_type_error(self, mock_get_conn):
        mock_connection = mock.MagicMock(spec_set=['get_relays'])
        side_effect = TypeError("Surprise!")
        mock_connection.get_relays.side_effect = side_effect

        mock_get_conn.return_value = mock_connection
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=INFO_DICT)
        info = iboot_power._parse_driver_info(node)

        status = iboot_power._power_status(info)
        self.assertEqual(states.ERROR, status)
        mock_get_conn.assert_called_once_with(info)
        mock_connection.get_relays.assert_called_once_with()

    @mock.patch.object(iboot_power, '_get_connection', autospec=True)
    def test__power_status_ironic_exception_index_error(self, mock_get_conn):
        mock_connection = mock.MagicMock(spec_set=['get_relays'])
        side_effect = IndexError("Gotcha!")
        mock_connection.get_relays.side_effect = side_effect

        mock_get_conn.return_value = mock_connection
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=INFO_DICT)
        info = iboot_power._parse_driver_info(node)
        status = iboot_power._power_status(info)
        self.assertEqual(states.ERROR, status)

        mock_get_conn.assert_called_once_with(info)
        mock_connection.get_relays.assert_called_once_with()

    @mock.patch.object(iboot_power, '_get_connection', autospec=True)
    def test__power_status_error(self, mock_get_conn):
        mock_connection = mock.MagicMock(spec_set=['get_relays'])
        mock_connection.get_relays.return_value = list()
        mock_get_conn.return_value = mock_connection
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=INFO_DICT)
        info = iboot_power._parse_driver_info(node)

        status = iboot_power._power_status(info)

        self.assertEqual(states.ERROR, status)
        mock_get_conn.assert_called_once_with(info)
        mock_connection.get_relays.assert_called_once_with()

    @mock.patch.object(iboot_power, '_get_connection', autospec=True)
    def test__power_status_retries(self, mock_get_conn):
        self.config(max_retry=1, group='iboot')

        mock_connection = mock.MagicMock(spec_set=['get_relays'])
        side_effect = TypeError("Surprise!")
        mock_connection.get_relays.side_effect = side_effect

        mock_get_conn.return_value = mock_connection
        node = obj_utils.create_test_node(
            self.context,
            driver='fake_iboot_fake',
            driver_info=INFO_DICT)
        info = iboot_power._parse_driver_info(node)

        status = iboot_power._power_status(info)
        self.assertEqual(states.ERROR, status)
        mock_get_conn.assert_called_once_with(info)
        self.assertEqual(2, mock_connection.get_relays.call_count)


class IBootDriverTestCase(db_base.DbTestCase):

    def setUp(self):
        super(IBootDriverTestCase, self).setUp()
        self.config(max_retry=0, group='iboot')
        self.config(retry_interval=0, group='iboot')
        self.config(reboot_delay=0, group='iboot')
        self.config(enabled_hardware_types=['staging-iboot'],
                    enabled_power_interfaces=['staging-iboot'])
        self.node = obj_utils.create_test_node(
            self.context,
            driver='staging-iboot',
            driver_info=INFO_DICT)
        self.info = iboot_power._parse_driver_info(self.node)

    def test_get_properties(self):
        expected = iboot_power.COMMON_PROPERTIES
        with task_manager.acquire(
                self.context, self.node.uuid, shared=True) as task:
            # Remove properties from the boot and deploy interfaces
            task.driver.boot = fake.FakeBoot()
            task.driver.deploy = fake.FakeDeploy()
            self.assertEqual(expected, task.driver.get_properties())

    @mock.patch.object(iboot_power.LOG, 'warning')
    @mock.patch.object(iboot_power, '_power_status', autospec=True)
    @mock.patch.object(iboot_power, '_switch', autospec=True)
    def test_set_power_state_good(self, mock_switch, mock_power_status,
                                  mock_log):
        mock_power_status.return_value = states.POWER_ON

        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.power.set_power_state(task, states.POWER_ON)

        # ensure functions were called with the valid parameters
        mock_switch.assert_called_once_with(self.info, True)
        mock_power_status.assert_called_once_with(self.info)
        self.assertFalse(mock_log.called)

    @mock.patch.object(iboot_power.LOG, 'warning')
    @mock.patch.object(iboot_power, '_power_status', autospec=True)
    @mock.patch.object(iboot_power, '_switch', autospec=True)
    def test_set_power_state_timeout(self, mock_switch, mock_power_status,
                                     mock_log):
        mock_power_status.return_value = states.POWER_ON

        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.power.set_power_state(task, states.POWER_ON,
                                              timeout=22)

        # ensure functions were called with the valid parameters
        mock_switch.assert_called_once_with(self.info, True)
        mock_power_status.assert_called_once_with(self.info)
        self.assertTrue(mock_log.called)

    @mock.patch.object(iboot_power, '_power_status', autospec=True)
    @mock.patch.object(iboot_power, '_switch', autospec=True)
    def test_set_power_state_bad(self, mock_switch, mock_power_status):
        mock_power_status.return_value = states.POWER_OFF

        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(ironic_exception.PowerStateFailure,
                              task.driver.power.set_power_state,
                              task, states.POWER_ON)

        # ensure functions were called with the valid parameters
        mock_switch.assert_called_once_with(self.info, True)
        mock_power_status.assert_called_once_with(self.info)

    @mock.patch.object(iboot_power, '_power_status', autospec=True)
    @mock.patch.object(iboot_power, '_switch', autospec=True)
    def test_set_power_state_retry(self, mock_switch, mock_power_status):
        self.config(max_retry=2, group='iboot')
        mock_power_status.return_value = states.POWER_OFF

        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(ironic_exception.PowerStateFailure,
                              task.driver.power.set_power_state,
                              task, states.POWER_ON)

        # ensure functions were called with the valid parameters
        mock_switch.assert_called_once_with(self.info, True)
        # 1 + 2 retries
        self.assertEqual(3, mock_power_status.call_count)

    @mock.patch.object(iboot_power, '_power_status', autospec=True)
    @mock.patch.object(iboot_power, '_switch', autospec=True)
    def test_set_power_state_invalid_parameter(self, mock_switch,
                                               mock_power_status):
        mock_power_status.return_value = states.POWER_ON

        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(ironic_exception.InvalidParameterValue,
                              task.driver.power.set_power_state,
                              task, states.NOSTATE)

    @mock.patch.object(iboot_power.LOG, 'warning')
    @mock.patch.object(iboot_power, '_sleep_switch',
                       spec_set=types.FunctionType)
    @mock.patch.object(iboot_power, '_power_status', autospec=True)
    @mock.patch.object(iboot_power, '_switch', spec_set=types.FunctionType)
    def test_reboot_good(self, mock_switch, mock_power_status,
                         mock_sleep_switch, mock_log):
        self.config(reboot_delay=3, group='iboot')
        manager = mock.MagicMock(spec_set=['switch', 'sleep'])
        mock_power_status.return_value = states.POWER_ON

        manager.attach_mock(mock_switch, 'switch')
        manager.attach_mock(mock_sleep_switch, 'sleep')
        expected = [mock.call.switch(self.info, False),
                    mock.call.sleep(3),
                    mock.call.switch(self.info, True)]

        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.power.reboot(task)

        self.assertEqual(expected, manager.mock_calls)
        self.assertFalse(mock_log.called)

    @mock.patch.object(iboot_power.LOG, 'warning')
    @mock.patch.object(iboot_power, '_sleep_switch',
                       spec_set=types.FunctionType)
    @mock.patch.object(iboot_power, '_power_status', autospec=True)
    @mock.patch.object(iboot_power, '_switch', spec_set=types.FunctionType)
    def test_reboot_good_timeout(self, mock_switch, mock_power_status,
                                 mock_sleep_switch, mock_log):
        self.config(reboot_delay=3, group='iboot')
        manager = mock.MagicMock(spec_set=['switch', 'sleep'])
        mock_power_status.return_value = states.POWER_ON

        manager.attach_mock(mock_switch, 'switch')
        manager.attach_mock(mock_sleep_switch, 'sleep')
        expected = [mock.call.switch(self.info, False),
                    mock.call.sleep(3),
                    mock.call.switch(self.info, True)]

        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.power.reboot(task, timeout=12)

        self.assertEqual(expected, manager.mock_calls)
        self.assertTrue(mock_log.called)

    @mock.patch.object(iboot_power, '_sleep_switch',
                       spec_set=types.FunctionType)
    @mock.patch.object(iboot_power, '_power_status', autospec=True)
    @mock.patch.object(iboot_power, '_switch', spec_set=types.FunctionType)
    def test_reboot_bad(self, mock_switch, mock_power_status,
                        mock_sleep_switch):
        self.config(reboot_delay=3, group='iboot')
        manager = mock.MagicMock(spec_set=['switch', 'sleep'])
        mock_power_status.return_value = states.POWER_OFF

        manager.attach_mock(mock_switch, 'switch')
        manager.attach_mock(mock_sleep_switch, 'sleep')
        expected = [mock.call.switch(self.info, False),
                    mock.call.sleep(3),
                    mock.call.switch(self.info, True)]

        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(ironic_exception.PowerStateFailure,
                              task.driver.power.reboot, task)

        self.assertEqual(expected, manager.mock_calls)

    @mock.patch.object(iboot_power, '_power_status', autospec=True)
    @mock.patch.object(iboot_power, '_get_connection', autospec=True)
    def test__switch_retries(self, mock_get_conn, mock_power_status):
        self.config(max_retry=1, group='iboot')
        mock_power_status.return_value = states.POWER_ON

        mock_connection = mock.MagicMock(spec_set=['switch'])
        side_effect = TypeError("Surprise!")
        mock_connection.switch.side_effect = side_effect
        mock_get_conn.return_value = mock_connection

        iboot_power._switch(self.info, False)
        self.assertEqual(2, mock_connection.switch.call_count)

    @mock.patch.object(iboot_power, '_power_status', autospec=True)
    def test_get_power_state(self, mock_power_status):
        mock_power_status.return_value = states.POWER_ON

        with task_manager.acquire(self.context, self.node.uuid) as task:
            state = task.driver.power.get_power_state(task)
            self.assertEqual(state, states.POWER_ON)

        # ensure functions were called with the valid parameters
        mock_power_status.assert_called_once_with(self.info)

    @mock.patch.object(iboot_power, '_parse_driver_info', autospec=True)
    def test_validate_good(self, parse_drv_info_mock):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            task.driver.power.validate(task)
        self.assertEqual(1, parse_drv_info_mock.call_count)

    @mock.patch.object(iboot_power, '_parse_driver_info', autospec=True)
    def test_validate_fails(self, parse_drv_info_mock):
        side_effect = ironic_exception.InvalidParameterValue("Bad input")
        parse_drv_info_mock.side_effect = side_effect
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            self.assertRaises(ironic_exception.InvalidParameterValue,
                              task.driver.power.validate, task)
        self.assertEqual(1, parse_drv_info_mock.call_count)
