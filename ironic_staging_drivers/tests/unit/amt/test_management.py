#
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
Test class for AMT ManagementInterface
"""

from ironic.common import boot_devices
from ironic.common import exception as ironic_exception
from ironic.conductor import task_manager
import mock
from oslo_config import cfg

from ironic_staging_drivers.amt import common as amt_common
from ironic_staging_drivers.amt import management as amt_mgmt
from ironic_staging_drivers.amt import resource_uris
from ironic_staging_drivers.common import exception
from ironic_staging_drivers.tests.unit.amt import pywsman_mocks_specs \
    as mock_specs
from ironic_staging_drivers.tests.unit.amt import utils as test_utils

CONF = cfg.CONF


@mock.patch.object(amt_common, 'pywsman', spec_set=mock_specs.PYWSMAN_SPEC)
class AMTManagementInteralMethodsTestCase(test_utils.BaseAMTTest):

    @mock.patch.object(amt_common, 'awake_amt_interface', spec_set=True,
                       autospec=True)
    def test__set_boot_device_order(self, mock_aw, mock_client_pywsman):
        namespace = resource_uris.CIM_BootConfigSetting
        device = boot_devices.PXE
        result_xml = test_utils.build_soap_xml([{'ReturnValue': '0'}],
                                               namespace)
        mock_xml = test_utils.mock_wsman_root(result_xml)
        mock_pywsman = mock_client_pywsman.Client.return_value
        mock_pywsman.invoke.return_value = mock_xml

        amt_mgmt._set_boot_device_order(self.node, device)

        mock_pywsman.invoke.assert_called_once_with(
            mock.ANY, namespace, 'ChangeBootOrder', mock.ANY)
        self.assertTrue(mock_aw.called)

    @mock.patch.object(amt_common, 'awake_amt_interface', spec_set=True,
                       autospec=True)
    def test__set_boot_device_order_fail(self, mock_aw, mock_client_pywsman):
        namespace = resource_uris.CIM_BootConfigSetting
        device = boot_devices.PXE
        result_xml = test_utils.build_soap_xml([{'ReturnValue': '2'}],
                                               namespace)
        mock_xml = test_utils.mock_wsman_root(result_xml)
        mock_pywsman = mock_client_pywsman.Client.return_value
        mock_pywsman.invoke.return_value = mock_xml

        self.assertRaises(exception.AMTFailure,
                          amt_mgmt._set_boot_device_order, self.node, device)
        mock_pywsman.invoke.assert_called_once_with(
            mock.ANY, namespace, 'ChangeBootOrder', mock.ANY)

        mock_pywsman = mock_client_pywsman.Client.return_value
        mock_pywsman.invoke.return_value = None

        self.assertRaises(exception.AMTConnectFailure,
                          amt_mgmt._set_boot_device_order, self.node, device)
        self.assertTrue(mock_aw.called)

    @mock.patch.object(amt_common, 'awake_amt_interface', spec_set=True,
                       autospec=True)
    def test__enable_boot_config(self, mock_aw, mock_client_pywsman):
        namespace = resource_uris.CIM_BootService
        result_xml = test_utils.build_soap_xml([{'ReturnValue': '0'}],
                                               namespace)
        mock_xml = test_utils.mock_wsman_root(result_xml)
        mock_pywsman = mock_client_pywsman.Client.return_value
        mock_pywsman.invoke.return_value = mock_xml

        amt_mgmt._enable_boot_config(self.node)

        mock_pywsman.invoke.assert_called_once_with(
            mock.ANY, namespace, 'SetBootConfigRole', mock.ANY)
        self.assertTrue(mock_aw.called)

    @mock.patch.object(amt_common, 'awake_amt_interface', spec_set=True,
                       autospec=True)
    def test__enable_boot_config_fail(self, mock_aw, mock_client_pywsman):
        namespace = resource_uris.CIM_BootService
        result_xml = test_utils.build_soap_xml([{'ReturnValue': '2'}],
                                               namespace)
        mock_xml = test_utils.mock_wsman_root(result_xml)
        mock_pywsman = mock_client_pywsman.Client.return_value
        mock_pywsman.invoke.return_value = mock_xml

        self.assertRaises(exception.AMTFailure,
                          amt_mgmt._enable_boot_config, self.node)
        mock_pywsman.invoke.assert_called_once_with(
            mock.ANY, namespace, 'SetBootConfigRole', mock.ANY)

        mock_pywsman = mock_client_pywsman.Client.return_value
        mock_pywsman.invoke.return_value = None

        self.assertRaises(exception.AMTConnectFailure,
                          amt_mgmt._enable_boot_config, self.node)
        self.assertTrue(mock_aw.called)


class AMTManagementTestCase(test_utils.BaseAMTTest):

    def test_get_properties(self):
        expected = amt_common.COMMON_PROPERTIES
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            self.assertEqual(expected, task.driver.management.get_properties())

    @mock.patch.object(amt_common, 'parse_driver_info', spec_set=True,
                       autospec=True)
    def test_validate(self, mock_drvinfo):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            task.driver.management.validate(task)
            mock_drvinfo.assert_called_once_with(task.node)

    @mock.patch.object(amt_common, 'parse_driver_info', spec_set=True,
                       autospec=True)
    def test_validate_fail(self, mock_drvinfo):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            mock_drvinfo.side_effect = iter(
                [ironic_exception.InvalidParameterValue('x')])
            self.assertRaises(ironic_exception.InvalidParameterValue,
                              task.driver.management.validate,
                              task)

    def test_get_supported_boot_devices(self):
        expected = [boot_devices.PXE, boot_devices.DISK, boot_devices.CDROM]
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            self.assertEqual(
                sorted(expected),
                sorted(task.driver.management.
                       get_supported_boot_devices(task)))

    def test_set_boot_device_one_time(self):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.management.set_boot_device(task, 'pxe')
            self.assertEqual('pxe',
                             task.node.driver_internal_info["amt_boot_device"])
            self.assertFalse(
                task.node.driver_internal_info["amt_boot_persistent"])

    def test_set_boot_device_persistent(self):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.management.set_boot_device(task, 'pxe',
                                                   persistent=True)
            self.assertEqual('pxe',
                             task.node.driver_internal_info["amt_boot_device"])
            self.assertTrue(
                task.node.driver_internal_info["amt_boot_persistent"])

    def test_set_boot_device_fail(self):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(ironic_exception.InvalidParameterValue,
                              task.driver.management.set_boot_device,
                              task, 'fake-device')

    @mock.patch.object(amt_mgmt, '_enable_boot_config', spec_set=True,
                       autospec=True)
    @mock.patch.object(amt_mgmt, '_set_boot_device_order', spec_set=True,
                       autospec=True)
    def test_ensure_next_boot_device_one_time(self, mock_sbdo, mock_ebc):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            device = boot_devices.PXE
            task.node.driver_internal_info['amt_boot_device'] = 'pxe'
            task.driver.management.ensure_next_boot_device(task.node, device)
            self.assertEqual('disk',
                             task.node.driver_internal_info["amt_boot_device"])
            self.assertTrue(
                task.node.driver_internal_info["amt_boot_persistent"])
            mock_sbdo.assert_called_once_with(task.node, device)
            mock_ebc.assert_called_once_with(task.node)

    @mock.patch.object(amt_mgmt, '_enable_boot_config', spec_set=True,
                       autospec=True)
    @mock.patch.object(amt_mgmt, '_set_boot_device_order', spec_set=True,
                       autospec=True)
    def test_ensure_next_boot_device_persistent(self, mock_sbdo, mock_ebc):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            device = boot_devices.PXE
            task.node.driver_internal_info['amt_boot_device'] = 'pxe'
            task.node.driver_internal_info['amt_boot_persistent'] = True
            task.driver.management.ensure_next_boot_device(task.node, device)
            self.assertEqual('pxe',
                             task.node.driver_internal_info["amt_boot_device"])
            self.assertTrue(
                task.node.driver_internal_info["amt_boot_persistent"])
            mock_sbdo.assert_called_once_with(task.node, device)
            mock_ebc.assert_called_once_with(task.node)

    def test_get_boot_device(self):
        expected = {'boot_device': boot_devices.DISK, 'persistent': True}
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            self.assertEqual(expected,
                             task.driver.management.get_boot_device(task))

    def test_get_sensor_data(self):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            self.assertRaises(NotImplementedError,
                              task.driver.management.get_sensors_data,
                              task)
