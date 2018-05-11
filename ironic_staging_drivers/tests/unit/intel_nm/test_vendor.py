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

"""
Tests for Intel NM vendor interface
"""

import os

from ironic.common import exception
from ironic.conductor import task_manager
from ironic.drivers.modules import ipmitool
from ironic.tests.unit.db import base as db_base
from ironic.tests.unit.objects import utils as obj_utils
from ironic_lib import utils as ironic_utils
import mock
from oslo_config import cfg

from ironic_staging_drivers.intel_nm import nm_commands
from ironic_staging_drivers.intel_nm import nm_vendor


CONF = cfg.CONF

_MAIN_IDS = {'domain_id': 'platform', 'policy_id': 111}

_POLICY = {'domain_id': 'platform', 'enable': True, 'policy_id': 111,
           'policy_trigger': 'none', 'action': 'alert',
           'power_domain': 'primary', 'target_limit': 100,
           'correction_time': 200, 'reporting_period': 600}

_SUSPEND = {'domain_id': 'platform', 'policy_id': 121,
            'periods': [{'start': 10, 'stop': 30, 'days': ['monday']}]}

_GET_CAP = {'domain_id': 'platform', 'policy_trigger': 'none',
            'power_domain': 'primary'}

_CONTROL = {'scope': 'global', 'enable': True}

_STATISTICS = {'scope': 'global', 'domain_id': 'platform',
               'parameter_name': 'response_time'}

_VENDOR_METHODS_DATA = {'get_nm_policy': _MAIN_IDS,
                        'remove_nm_policy': _MAIN_IDS,
                        'get_nm_policy_suspend': _MAIN_IDS,
                        'remove_nm_policy_suspend': _MAIN_IDS,
                        'set_nm_policy': _POLICY,
                        'set_nm_policy_suspend': _SUSPEND,
                        'get_nm_capabilities': _GET_CAP,
                        'control_nm_policy': _CONTROL,
                        'get_nm_statistics': _STATISTICS,
                        'reset_nm_statistics': _STATISTICS}


class IntelNMPassthruTestCase(db_base.DbTestCase):

    def setUp(self):
        super(IntelNMPassthruTestCase, self).setUp()
        self.config(enabled_hardware_types=['staging-nm'],
                    enabled_vendor_interfaces=['staging-nm'],
                    enabled_power_interfaces=['ipmitool'],
                    enabled_management_interfaces=['ipmitool'])
        self.node = obj_utils.create_test_node(self.context,
                                               driver='staging-nm')
        self.temp_filename = os.path.join(CONF.tempdir, self.node.uuid +
                                          '.sdr')

    @mock.patch.object(ironic_utils, 'unlink_without_raise', spec_set=True,
                       autospec=True)
    @mock.patch.object(ipmitool, 'send_raw', spec_set=True, autospec=True)
    @mock.patch.object(ipmitool, 'dump_sdr', spec_set=True, autospec=True)
    @mock.patch.object(nm_commands, 'parse_slave_and_channel', spec_set=True,
                       autospec=True)
    def test__get_nm_address_detected(self, parse_mock, dump_mock, raw_mock,
                                      unlink_mock):
        parse_mock.return_value = ('0x0A', '0x0B')
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            ret = nm_vendor._get_nm_address(task)
            self.assertEqual(('0x0B', '0x0A'), ret)
            self.node.refresh()
            internal_info = self.node.driver_internal_info
            self.assertEqual('0x0A', internal_info['intel_nm_address'])
            self.assertEqual('0x0B', internal_info['intel_nm_channel'])
            parse_mock.assert_called_once_with(self.temp_filename)
            dump_mock.assert_called_once_with(task, self.temp_filename)
            unlink_mock.assert_called_once_with(self.temp_filename)
            raw_mock.assert_called_once_with(task, mock.ANY)

    @mock.patch.object(ironic_utils, 'unlink_without_raise', spec_set=True,
                       autospec=True)
    @mock.patch.object(ipmitool, 'send_raw', spec_set=True, autospec=True)
    @mock.patch.object(ipmitool, 'dump_sdr', spec_set=True, autospec=True)
    @mock.patch.object(nm_commands, 'parse_slave_and_channel', spec_set=True,
                       autospec=True)
    def test__get_nm_address_already_detected(self, parse_mock, dump_mock,
                                              raw_mock, unlink_mock):
        internal_info = self.node.driver_internal_info
        internal_info['intel_nm_channel'] = '0x0B'
        internal_info['intel_nm_address'] = '0x0A'
        self.node.driver_internal_info = internal_info
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            ret = nm_vendor._get_nm_address(task)
            self.assertEqual(('0x0B', '0x0A'), ret)
        self.assertFalse(parse_mock.called)
        self.assertFalse(dump_mock.called)
        self.assertFalse(raw_mock.called)
        self.assertFalse(unlink_mock.called)

    @mock.patch.object(ironic_utils, 'unlink_without_raise', spec_set=True,
                       autospec=True)
    @mock.patch.object(ipmitool, 'send_raw', spec_set=True, autospec=True)
    @mock.patch.object(ipmitool, 'dump_sdr', spec_set=True, autospec=True)
    @mock.patch.object(nm_commands, 'parse_slave_and_channel', spec_set=True,
                       autospec=True)
    def test__get_nm_address_not_detected(self, parse_mock, dump_mock,
                                          raw_mock, unlink_mock):
        parse_mock.return_value = None
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.IPMIFailure, nm_vendor._get_nm_address,
                              task)
            self.node.refresh()
            internal_info = self.node.driver_internal_info
            self.assertEqual(False, internal_info['intel_nm_address'])
            self.assertEqual(False, internal_info['intel_nm_channel'])
            parse_mock.assert_called_once_with(self.temp_filename)
            dump_mock.assert_called_once_with(task, self.temp_filename)
            unlink_mock.assert_called_once_with(self.temp_filename)
            self.assertFalse(raw_mock.called)

    @mock.patch.object(ironic_utils, 'unlink_without_raise', spec_set=True,
                       autospec=True)
    @mock.patch.object(ipmitool, 'send_raw', spec_set=True, autospec=True)
    @mock.patch.object(ipmitool, 'dump_sdr', spec_set=True, autospec=True)
    @mock.patch.object(nm_commands, 'parse_slave_and_channel', spec_set=True,
                       autospec=True)
    def test__get_nm_address_raw_fail(self, parse_mock, dump_mock, raw_mock,
                                      unlink_mock):
        parse_mock.return_value = ('0x0A', '0x0B')
        raw_mock.side_effect = exception.IPMIFailure('raw error')
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.IPMIFailure, nm_vendor._get_nm_address,
                              task)
            self.node.refresh()
            internal_info = self.node.driver_internal_info
            self.assertEqual(False, internal_info['intel_nm_address'])
            self.assertEqual(False, internal_info['intel_nm_channel'])
            parse_mock.assert_called_once_with(self.temp_filename)
            dump_mock.assert_called_once_with(task, self.temp_filename)
            unlink_mock.assert_called_once_with(self.temp_filename)
            raw_mock.assert_called_once_with(task, mock.ANY)

    @mock.patch.object(ironic_utils, 'unlink_without_raise', spec_set=True,
                       autospec=True)
    @mock.patch.object(ipmitool, 'send_raw', spec_set=True, autospec=True)
    @mock.patch.object(ipmitool, 'dump_sdr', spec_set=True, autospec=True)
    @mock.patch.object(nm_commands, 'parse_slave_and_channel', spec_set=True,
                       autospec=True)
    def test__get_nm_address_already_not_detected(self, parse_mock, dump_mock,
                                                  raw_mock, unlink_mock):
        internal_info = self.node.driver_internal_info
        internal_info['intel_nm_channel'] = False
        internal_info['intel_nm_address'] = False
        self.node.driver_internal_info = internal_info
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.IPMIFailure, nm_vendor._get_nm_address,
                              task)
        self.assertFalse(parse_mock.called)
        self.assertFalse(dump_mock.called)
        self.assertFalse(raw_mock.called)
        self.assertFalse(unlink_mock.called)

    @mock.patch.object(ipmitool, 'send_raw', spec_set=True, autospec=True)
    @mock.patch.object(nm_vendor, '_get_nm_address', spec_set=True,
                       autospec=True)
    def test__execute_nm_command(self, addr_mock, raw_mock):
        addr_mock.return_value = ('0x0A', '0x0B')
        raw_mock.return_value = ('0x03 0x04', '')
        fake_data = {'foo': 'bar'}
        fake_command = mock.MagicMock()
        fake_parse = mock.MagicMock()
        fake_command.return_value = ('0x01', '0x02')
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            nm_vendor._execute_nm_command(task, fake_data, fake_command,
                                          fake_parse)
            self.assertEqual('single', task.node.driver_info['ipmi_bridging'])
            self.assertEqual('0x0A',
                             task.node.driver_info['ipmi_target_channel'])
            self.assertEqual('0x0B',
                             task.node.driver_info['ipmi_target_address'])
            fake_command.assert_called_once_with(fake_data)
            raw_mock.assert_called_once_with(task, '0x01 0x02')
            fake_parse.assert_called_once_with(['0x03', '0x04'])

    @mock.patch.object(ipmitool, 'send_raw', spec_set=True, autospec=True)
    @mock.patch.object(nm_vendor, '_get_nm_address', spec_set=True,
                       autospec=True)
    def test__execute_nm_command_no_parse(self, addr_mock, raw_mock):
        addr_mock.return_value = ('0x0A', '0x0B')
        fake_data = {'foo': 'bar'}
        fake_command = mock.MagicMock()
        fake_command.return_value = ('0x01', '0x02')
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            nm_vendor._execute_nm_command(task, fake_data, fake_command)
            self.assertEqual('single', task.node.driver_info['ipmi_bridging'])
            self.assertEqual('0x0A',
                             task.node.driver_info['ipmi_target_channel'])
            self.assertEqual('0x0B',
                             task.node.driver_info['ipmi_target_address'])
            fake_command.assert_called_once_with(fake_data)
            raw_mock.assert_called_once_with(task, '0x01 0x02')

    def test_validate_json(self):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            for method, data in _VENDOR_METHODS_DATA.items():
                task.driver.vendor.validate(task, method, 'fake', **data)

    def test_validate_json_error(self):
        fake_data = {'foo': 'bar'}
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            for method in _VENDOR_METHODS_DATA:
                self.assertRaises(exception.InvalidParameterValue,
                                  task.driver.vendor.validate, task, method,
                                  'fake', **fake_data)

    def test_validate_control_no_domain(self):
        data = {'scope': 'domain', 'enable': True}
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.MissingParameterValue,
                              task.driver.vendor.validate, task,
                              'control_nm_policy', 'fake', **data)

    def test_validate_control_no_policy(self):
        data = {'scope': 'policy', 'enable': True, 'domain_id': 'platform'}
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.MissingParameterValue,
                              task.driver.vendor.validate, task,
                              'control_nm_policy', 'fake', **data)

    def test_validate_policy_boot(self):
        data = _POLICY.copy()
        del data['correction_time']
        data['policy_trigger'] = 'boot'
        data['target_limit'] = {'boot_mode': 'power', 'cores_disabled': 2}
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.validate(task, 'set_nm_policy', 'fake', **data)

    def test_validate_policy_boot_error(self):
        data = _POLICY.copy()
        data['policy_trigger'] = 'boot'
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.InvalidParameterValue,
                              task.driver.vendor.validate, task,
                              'set_nm_policy', 'fake', **data)

    def test_validate_policy_no_correction_time(self):
        data = _POLICY.copy()
        del data['correction_time']
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.MissingParameterValue,
                              task.driver.vendor.validate, task,
                              'set_nm_policy', 'fake', **data)

    def test_validate_statistics_no_policy(self):
        data = {'scope': 'policy', 'domain_id': 'platform'}
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.MissingParameterValue,
                              task.driver.vendor.validate, task,
                              'reset_nm_statistics', 'fake', **data)

    def test_validate_statistics_no_domain(self):
        data = {'scope': 'global', 'parameter_name': 'power'}
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.InvalidParameterValue,
                              task.driver.vendor.validate, task,
                              'get_nm_statistics', 'fake', **data)

    def test_reset_statistics_invalid_parameter(self):
        data = {'scope': 'global', 'domain_id': 'platform',
                'parameter_name': 'power'}
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.InvalidParameterValue,
                              task.driver.vendor.validate, task,
                              'reset_nm_statistics', 'fake', **data)

    def test_get_statistics_no_parameter(self):
        data = {'scope': 'global', 'domain_id': 'platform'}
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.MissingParameterValue,
                              task.driver.vendor.validate, task,
                              'get_nm_statistics', 'fake', **data)

    def test_get_statistics_invalid_parameter(self):
        data = {'scope': 'policy', 'domain_id': 'platform', 'policy_id': 111,
                'parameter_name': 'response_time'}
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.InvalidParameterValue,
                              task.driver.vendor.validate, task,
                              'get_nm_statistics', 'fake', **data)

    @mock.patch.object(nm_vendor, '_execute_nm_command', spec_set=True,
                       autospec=True)
    def test_control_nm_policy(self, mock_exec):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.control_nm_policy(task)
            mock_exec.assert_called_once_with(task, {},
                                              nm_commands.control_policies)

    @mock.patch.object(nm_vendor, '_execute_nm_command', spec_set=True,
                       autospec=True)
    def test_set_nm_policy(self, mock_exec):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.set_nm_policy(task)
            mock_exec.assert_called_once_with(task, {},
                                              nm_commands.set_policy)

    @mock.patch.object(nm_vendor, '_execute_nm_command', spec_set=True,
                       autospec=True)
    def test_get_nm_policy(self, mock_exec):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.get_nm_policy(task)
            mock_exec.assert_called_once_with(task, {},
                                              nm_commands.get_policy,
                                              nm_commands.parse_policy)

    @mock.patch.object(nm_vendor, '_execute_nm_command', spec_set=True,
                       autospec=True)
    def test_remove_nm_policy(self, mock_exec):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.remove_nm_policy(task)
            mock_exec.assert_called_once_with(task, {},
                                              nm_commands.remove_policy)

    @mock.patch.object(nm_vendor, '_execute_nm_command', spec_set=True,
                       autospec=True)
    def test_set_nm_policy_suspend(self, mock_exec):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.set_nm_policy_suspend(task)
            mock_exec.assert_called_once_with(task, {},
                                              nm_commands.set_policy_suspend)

    @mock.patch.object(nm_vendor, '_execute_nm_command', spec_set=True,
                       autospec=True)
    def test_get_nm_policy_suspend(self, mock_exec):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.get_nm_policy_suspend(task)
            mock_exec.assert_called_once_with(task, {},
                                              nm_commands.get_policy_suspend,
                                              nm_commands.parse_policy_suspend)

    @mock.patch.object(nm_vendor, '_execute_nm_command', spec_set=True,
                       autospec=True)
    def test_remove_nm_policy_suspend(self, mock_exec):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.remove_nm_policy_suspend(task)
            mock_exec.assert_called_once_with(task, {},
                                              nm_commands.remove_policy_suspend
                                              )

    @mock.patch.object(nm_vendor, '_execute_nm_command', spec_set=True,
                       autospec=True)
    def test_get_nm_capabilities(self, mock_exec):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.get_nm_capabilities(task)
            mock_exec.assert_called_once_with(task, {},
                                              nm_commands.get_capabilities,
                                              nm_commands.parse_capabilities)

    @mock.patch.object(nm_vendor, '_execute_nm_command', spec_set=True,
                       autospec=True)
    def test_get_nm_version(self, mock_exec):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.get_nm_version(task)
            mock_exec.assert_called_once_with(task, {},
                                              nm_commands.get_version,
                                              nm_commands.parse_version)

    @mock.patch.object(nm_vendor, '_execute_nm_command', spec_set=True,
                       autospec=True)
    def test_get_nm_statistics(self, mock_exec):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.get_nm_statistics(task)
            mock_exec.assert_called_once_with(task, {},
                                              nm_commands.get_statistics,
                                              nm_commands.parse_statistics)

    @mock.patch.object(nm_vendor, '_execute_nm_command', spec_set=True,
                       autospec=True)
    def test_reset_nm_statistics(self, mock_exec):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.reset_nm_statistics(task)
            mock_exec.assert_called_once_with(task, {},
                                              nm_commands.reset_statistics)
