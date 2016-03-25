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
Tests for Intel NM policies commands
"""

import tempfile

from ironic.common import exception
from ironic.tests import base

from ironic_staging_drivers.intel_nm import nm_commands as commands


@commands._handle_parsing_error
def fake_parse(fake_data):
    return fake_data


@commands._handle_parsing_error
def fake_parse_exc(d):
    raise IndexError()


class ParsingErrorDecoratorTestCase(base.TestCase):

    def test_parse_no_errors(self):
        self.assertEqual('foo', fake_parse('foo'))

    def test_parse_handled_exception(self):
        self.assertRaises(exception.IPMIFailure, fake_parse_exc, 'foo')


class IntelNMPoliciesCommandTestCase(base.TestCase):

    def test_set_policy(self):
        policy = {'domain_id': 'platform', 'enable': True, 'policy_id': 123,
                  'policy_trigger': 'temperature',
                  'cpu_power_correction': 'auto', 'storage': 'persistent',
                  'action': 'alert', 'power_domain': 'primary',
                  'target_limit': 1000, 'correction_time': 2000,
                  'trigger_limit': 100, 'reporting_period': 600}
        expected = ['0x2E', '0xC1', '0x57', '0x01', '0x00', '0x10', '0x7B',
                    '0x11', '0x00', '0xe8', '0x03', '0xd0', '0x07', '0x00',
                    '0x00', '0x64', '0x00', '0x58', '0x02']
        result = commands.set_policy(policy)
        self.assertEqual(expected, result)

    def test_set_policy_with_defaults(self):
        policy = {'domain_id': 'platform', 'enable': True, 'policy_id': 123,
                  'policy_trigger': 'none', 'action': 'alert',
                  'power_domain': 'primary', 'target_limit': 1000,
                  'correction_time': 2000, 'reporting_period': 600}
        expected = ['0x2E', '0xC1', '0x57', '0x01', '0x00', '0x10', '0x7B',
                    '0x10', '0x00', '0xe8', '0x03', '0xd0', '0x07', '0x00',
                    '0x00', '0x00', '0x00', '0x58', '0x02']
        result = commands.set_policy(policy)
        self.assertEqual(expected, result)

    def test_set_policy_boot(self):
        policy = {'domain_id': 'platform', 'enable': True, 'policy_id': 123,
                  'policy_trigger': 'boot', 'cpu_power_correction': 'auto',
                  'storage': 'persistent', 'action': 'alert',
                  'power_domain': 'primary',
                  'target_limit': {'boot_mode': 'power', 'cores_disabled': 2},
                  'trigger_limit': 100, 'reporting_period': 600}
        expected = ['0x2E', '0xC1', '0x57', '0x01', '0x00', '0x10', '0x7B',
                    '0x14', '0x00', '0x04', '0x00', '0x00', '0x00', '0x00',
                    '0x00', '0x00', '0x00', '0x58', '0x02']
        result = commands.set_policy(policy)
        self.assertEqual(expected, result)

    def test_set_policy_suspend(self):
        suspend = {'domain_id': 'platform', 'policy_id': 123,
                   'periods': [{'start': 20, 'stop': 100,
                                'days': ['monday', 'tuesday']},
                               {'start': 30, 'stop': 150,
                                'days': ['friday', 'sunday']}]}
        result = commands.set_policy_suspend(suspend)
        expected = ['0x2E', '0xC5', '0x57', '0x01', '0x00', '0x00', '0x7B',
                    '0x02', '0x14', '0x64', '0x03', '0x1E', '0x96', '0x50']
        self.assertEqual(expected, result)

    def test_get_capabilities(self):
        cap_data = {'domain_id': 'platform', 'policy_trigger': 'none',
                    'power_domain': 'primary'}
        result = commands.get_capabilities(cap_data)
        expected = ['0x2E', '0xC9', '0x57', '0x01', '0x00', '0x00', '0x10']
        self.assertEqual(expected, result)

    def test_control_policies(self):
        control_data = {'scope': 'policy', 'enable': True,
                        'domain_id': 'platform', 'policy_id': 123}
        result = commands.control_policies(control_data)
        expected = ['0x2E', '0xC0', '0x57', '0x01', '0x00', '0x05', '0x00',
                    '0x7B']
        self.assertEqual(expected, result)

    def test_get_policy(self):
        data = {'domain_id': 'platform', 'policy_id': 123}
        result = commands.get_policy(data)
        expected = ['0x2E', '0xC2', '0x57', '0x01', '0x00', '0x00', '0x7B']
        self.assertEqual(expected, result)

    def test_remove_policy(self):
        data = {'domain_id': 'platform', 'policy_id': 123}
        expected = (['0x2E', '0xC1', '0x57', '0x01', '0x00', '0x00', '0x7B'] +
                    ['0x00'] * 12)
        result = commands.remove_policy(data)
        self.assertEqual(expected, result)

    def test_get_policy_suspend(self):
        data = {'domain_id': 'platform', 'policy_id': 123}
        expected = ['0x2E', '0xC6', '0x57', '0x01', '0x00', '0x00', '0x7B']
        result = commands.get_policy_suspend(data)
        self.assertEqual(expected, result)

    def test_remove_policy_suspend(self):
        data = {'domain_id': 'platform', 'policy_id': 123}
        expected = ['0x2E', '0xC5', '0x57', '0x01', '0x00', '0x00', '0x7B',
                    '0x00']
        result = commands.remove_policy_suspend(data)
        self.assertEqual(expected, result)

    def test_get_version(self):
        result = commands.get_version(None)
        expected = ['0x2E', '0xCA', '0x57', '0x01', '0x00']
        self.assertEqual(expected, result)

    def test_parse_policy(self):
        raw_data = ['0x00', '0x00', '0x00', '0x70', '0x00', '0x00', '0x02',
                    '0xFF', '0x00', '0x01', '0x02', '0x00', '0x01', '0x20',
                    '0x40', '0x01']
        expected = {'action': 'alert', 'correction_time': 131328,
                    'cpu_power_correction': 'auto', 'created_by_nm': True,
                    'domain_id': 'platform', 'enabled': True,
                    'global_enabled': True, 'per_domain_enabled': True,
                    'policy_trigger': 'none', 'power_domain': 'primary',
                    'power_policy': False, 'reporting_period': 320,
                    'storage': 'persistent', 'target_limit': 65282,
                    'trigger_limit': 8193}

        result = commands.parse_policy(raw_data)
        self.assertEqual(expected, result)

    def test_parse_policy_invalid_length(self):
        raw_data = ['0x00', '0x00', '0x00', '0x70', '0x00', '0x00', '0x02',
                    '0xFF', '0x00', '0x01', '0x02', '0x00', '0x01', '0x20']
        self.assertRaises(exception.IPMIFailure, commands.parse_policy,
                          raw_data)

    def test_parse_policy_corrupted_data(self):
        raw_data = ['0x00', '0x00', '0x00', '0x7F', '0x00', '0x00', '0x02',
                    '0xFF', '0x00', '0x01', '0x02', '0x00', '0x01', '0x20',
                    '0x40', '0x01']
        self.assertRaises(exception.IPMIFailure, commands.parse_policy,
                          raw_data)

    def test_parse_policy_conversion_error(self):
        raw_data = ['0x00', '0x00', '0x00', 'boo', '0x00', '0x00', '0x02',
                    '0xFF', '0x00', '0x01', '0x02', '0x00', '0x01', '0x20',
                    '0x40', '0x01']
        self.assertRaises(exception.IPMIFailure, commands.parse_policy,
                          raw_data)

    def test_parse_policy_suspend(self):
        raw_data = ['0x00', '0x00', '0x00', '0x02', '0x08', '0x18', '0x03',
                    '0x20', '0x50', '0x18']
        expected = [{'days': ['monday', 'tuesday'], 'start': 8, 'stop': 24},
                    {'days': ['thursday', 'friday'], 'start': 32, 'stop': 80}]
        result = commands.parse_policy_suspend(raw_data)
        self.assertEqual(expected, result)

    def test_parse_policy_suspend_invalid_lenght(self):
        raw_data = ['0x00', '0x00', '0x00', '0x22', '0x08', '0x18', '0x03']
        self.assertRaises(exception.IPMIFailure, commands.parse_policy_suspend,
                          raw_data)

    def test_parse_policy_suspend_conversion_error(self):
        raw_data = ['0x00', '0x00', '0x00', '0x02', 'boo', '0x18', '0x03',
                    '0x20', '0x50', '0x18']
        self.assertRaises(exception.IPMIFailure, commands.parse_policy_suspend,
                          raw_data)

    def test_parse_capabilities(self):
        raw_data = ['0x00', '0x00', '0x00', '0x10', '0x00', '0x10', '0x00',
                    '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00',
                    '0x80', '0x00', '0x00', '0x00', '0x00', '0x80', '0x00']
        expected = {'domain_id': 'platform', 'max_correction_time': 8388608,
                    'max_limit_value': 4096, 'max_policies': 16,
                    'max_reporting_period': 32768, 'min_correction_time': 0,
                    'min_limit_value': 0, 'min_reporting_period': 0,
                    'power_domain': 'primary'}
        result = commands.parse_capabilities(raw_data)
        self.assertEqual(expected, result)

    def test_parse_capabilities_invalid_lenght(self):
        raw_data = ['0x00', '0x00', '0x00', '0x10', '0x00', '0x10', '0x00']
        self.assertRaises(exception.IPMIFailure, commands.parse_capabilities,
                          raw_data)

    def test_parse_capabilities_corrupted_data(self):
        raw_data = ['0x00', '0x00', '0x00', '0x10', '0x00', '0x10', '0x00',
                    '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00',
                    '0x80', '0x00', '0x00', '0x00', '0x00', '0x80', '0xFF']
        self.assertRaises(exception.IPMIFailure, commands.parse_capabilities,
                          raw_data)

    def test_parse_capabilities_conversion_error(self):
        raw_data = ['0x00', '0x00', '0x00', '0x10', '0x00', '0x10', '0x00',
                    '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00',
                    '0x80', '0x00', '0x00', '0x00', 'boo', '0x80', '0x00']
        self.assertRaises(exception.IPMIFailure, commands.parse_capabilities,
                          raw_data)

    def test_parse_version(self):
        raw_data = ['0x00', '0x00', '0x00', '0x05', '0x03', '0x07', '0x01',
                    '0x02']
        expected = {'firmware': '1.2', 'ipmi': '3.0', 'nm': '3.0',
                    'patch': '7'}
        result = commands.parse_version(raw_data)
        self.assertEqual(expected, result)

    def test_parse_version_invalid_lenght(self):
        raw_data = ['0x00', '0x00', '0x00', '0x05', '0x03', '0x07', '0x01']
        self.assertRaises(exception.IPMIFailure, commands.parse_version,
                          raw_data)

    def test_parse_version_conversion_error(self):
        raw_data = ['0x00', '0x00', '0x00', '0x05', '0x03', '0x07', '0x01',
                    'boo']
        self.assertRaises(exception.IPMIFailure, commands.parse_version,
                          raw_data)

    def test_reset_statistics_global(self):
        data = {'scope': 'global', 'domain_id': 'platform'}
        expected = ['0x2E', '0xC7', '0x57', '0x01', '0x00', '0x00', '0x00',
                    '0x00']
        result = commands.reset_statistics(data)
        self.assertEqual(expected, result)

    def test_reset_statistics_policy(self):
        data = {'scope': 'policy', 'domain_id': 'platform', 'policy_id': 111}
        expected = ['0x2E', '0xC7', '0x57', '0x01', '0x00', '0x01', '0x00',
                    '0x6F']
        result = commands.reset_statistics(data)
        self.assertEqual(expected, result)

    def test_reset_statistics_parameter(self):
        data = {'scope': 'global', 'parameter_name': 'response_time'}
        expected = ['0x2E', '0xC7', '0x57', '0x01', '0x00', '0x1C', '0x00',
                    '0x00']
        result = commands.reset_statistics(data)
        self.assertEqual(expected, result)

    def test_get_statistics_global(self):
        data = {'scope': 'global', 'domain_id': 'platform',
                'parameter_name': 'power'}
        expected = ['0x2E', '0xC8', '0x57', '0x01', '0x00', '0x01', '0x00',
                    '0x00']
        result = commands.get_statistics(data)
        self.assertEqual(expected, result)

    def test_get_statistics_global_without_domain(self):
        data = {'scope': 'global', 'parameter_name': 'response_time'}
        expected = ['0x2E', '0xC8', '0x57', '0x01', '0x00', '0x1C', '0x00',
                    '0x00']
        result = commands.get_statistics(data)
        self.assertEqual(expected, result)

    def test_get_statistics_policy(self):
        data = {'scope': 'policy', 'domain_id': 'platform', 'policy_id': 111,
                'parameter_name': 'power'}
        expected = ['0x2E', '0xC8', '0x57', '0x01', '0x00', '0x11', '0x00',
                    '0x6F']
        result = commands.get_statistics(data)
        self.assertEqual(expected, result)

    def test_parse_statistics(self):
        raw_data = ['0x00', '0x00', '0x00', '0x80', '0x00', '0x20', '0x00',
                    '0xF0', '0x00', '0x60', '0x00', '0x00', '0x01', '0x20',
                    '0x40', '0x01', '0x01', '0x00', '0x00', '0xF0']
        expected = {'activation_state': True, 'administrative_enabled': True,
                    'average_value': 96, 'current_value': 128,
                    'domain_id': 'platform', 'maximum_value': 240,
                    'measurement_state': True, 'minimum_value': 32,
                    'operational_state': True, 'reporting_period': 257,
                    'timestamp': '2004-02-03T20:13:52'}

        result = commands.parse_statistics(raw_data)
        self.assertEqual(expected, result)

    def test_parse_statistics_invalid_timestamp(self):
        raw_data = ['0x00', '0x00', '0x00', '0x80', '0x00', '0x20', '0x00',
                    '0xF0', '0x00', '0x60', '0x00', '0xFF', '0xFF', '0xFF',
                    '0xFF', '0x01', '0x01', '0x00', '0x00', '0xF0']
        result = commands.parse_statistics(raw_data)
        self.assertEqual(commands._INVALID_TIME, result['timestamp'])


class ParsingFromFileTestCase(base.TestCase):

    def setUp(self):
        super(ParsingFromFileTestCase, self).setUp()
        self.temp_file = tempfile.NamedTemporaryFile().name

    def test_parsing_found(self):
        data = b'\x00\xFF\x00\xFF\x57\x01\x00\x0D\x01\x6A\xB2\x00\xFF'
        with open(self.temp_file, 'wb') as f:
            f.write(data)
        result = commands.parse_slave_and_channel(self.temp_file)
        self.assertEqual(('0x6a', '0x0b'), result)

    def test_parsing_not_found(self):
        data = b'\x00\xFF\x00\xFF\x52\x01\x80\x0D\x01\x6A\xB7\x00\xFF'
        with open(self.temp_file, 'wb') as f:
            f.write(data)
        result = commands.parse_slave_and_channel(self.temp_file)
        self.assertIsNone(result)
