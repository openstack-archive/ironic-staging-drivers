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
Test class for AMT Common
"""
import time

from ironic.common import exception as ironic_exception
from ironic.common import utils
from ironic.tests import base
import mock
from oslo_concurrency import processutils
from oslo_config import cfg

from ironic_staging_drivers.amt import common as amt_common
from ironic_staging_drivers.amt import resource_uris
from ironic_staging_drivers.common import exception
from ironic_staging_drivers.tests.unit.amt import pywsman_mocks_specs \
    as mock_specs
from ironic_staging_drivers.tests.unit.amt import utils as test_utils

CONF = cfg.CONF
INFO_DICT = test_utils.get_test_amt_info()


class AMTCommonMethodsTestCase(test_utils.BaseAMTTest):

    def test_parse_driver_info(self):
        info = amt_common.parse_driver_info(self.node)

        self.assertIsNotNone(info.get('address'))
        self.assertIsNotNone(info.get('username'))
        self.assertIsNotNone(info.get('password'))
        self.assertIsNotNone(info.get('protocol'))
        self.assertIsNotNone(info.get('uuid'))

    def test_parse_driver_info_missing_address(self):
        del self.node.driver_info['amt_address']

        self.assertRaises(ironic_exception.MissingParameterValue,
                          amt_common.parse_driver_info, self.node)

    def test_parse_driver_info_missing_username(self):
        del self.node.driver_info['amt_username']

        self.assertRaises(ironic_exception.MissingParameterValue,
                          amt_common.parse_driver_info, self.node)

    def test_parse_driver_info_missing_password(self):
        del self.node.driver_info['amt_password']
        self.assertRaises(ironic_exception.MissingParameterValue,
                          amt_common.parse_driver_info, self.node)

    def test_parse_driver_info_missing_protocol(self):
        del self.node.driver_info['amt_protocol']
        info = amt_common.parse_driver_info(self.node)
        self.assertEqual('http', info.get('protocol'))

    def test_parse_driver_info_wrong_protocol(self):
        self.node.driver_info['amt_protocol'] = 'fake-protocol'
        self.assertRaises(ironic_exception.InvalidParameterValue,
                          amt_common.parse_driver_info, self.node)

    @mock.patch.object(amt_common, 'Client', spec_set=True, autospec=True)
    def test_get_wsman_client(self, mock_client):
        info = amt_common.parse_driver_info(self.node)
        amt_common.get_wsman_client(self.node)
        options = {'address': info['address'],
                   'protocol': info['protocol'],
                   'username': info['username'],
                   'password': info['password']}

        mock_client.assert_called_once_with(**options)

    def test_xml_find(self):
        namespace = 'http://fake'
        value = 'fake_value'
        test_xml = test_utils.build_soap_xml([{'test_element': value}],
                                             namespace)
        mock_doc = test_utils.mock_wsman_root(test_xml)

        result = amt_common.xml_find(mock_doc, namespace, 'test_element')
        self.assertEqual(value, result.text)

    def test_xml_find_fail(self):
        mock_doc = None
        self.assertRaises(exception.AMTConnectFailure,
                          amt_common.xml_find,
                          mock_doc, 'namespace', 'test_element')


@mock.patch.object(amt_common, 'pywsman', spec_set=mock_specs.PYWSMAN_SPEC)
class AMTCommonClientTestCase(base.TestCase):
    def setUp(self):
        super(AMTCommonClientTestCase, self).setUp()
        self.info = {key[4:]: INFO_DICT[key] for key in INFO_DICT.keys()}

    def test_wsman_get(self, mock_client_pywsman):
        namespace = resource_uris.CIM_AssociatedPowerManagementService
        result_xml = test_utils.build_soap_xml([{'PowerState':
                                                 '2'}],
                                               namespace)
        mock_doc = test_utils.mock_wsman_root(result_xml)
        mock_pywsman = mock_client_pywsman.Client.return_value
        mock_pywsman.get.return_value = mock_doc
        client = amt_common.Client(**self.info)

        client.wsman_get(namespace)
        mock_pywsman.get.assert_called_once_with(mock.ANY, namespace)

    def test_wsman_get_fail(self, mock_client_pywsman):
        namespace = amt_common._SOAP_ENVELOPE
        result_xml = test_utils.build_soap_xml([{'Fault': 'fault'}],
                                               namespace)
        mock_doc = test_utils.mock_wsman_root(result_xml)
        mock_pywsman = mock_client_pywsman.Client.return_value
        mock_pywsman.get.return_value = mock_doc
        client = amt_common.Client(**self.info)

        self.assertRaises(exception.AMTFailure, client.wsman_get, namespace)
        mock_pywsman.get.assert_called_once_with(mock.ANY, namespace)

    def test_wsman_invoke(self, mock_client_pywsman):
        namespace = resource_uris.CIM_BootSourceSetting
        result_xml = test_utils.build_soap_xml([{'ReturnValue':
                                                 '0'}],
                                               namespace)
        mock_doc = test_utils.mock_wsman_root(result_xml)
        mock_pywsman = mock_client_pywsman.Client.return_value
        mock_pywsman.invoke.return_value = mock_doc
        method = 'ChangeBootOrder'
        options = mock.Mock(spec_set=[])
        client = amt_common.Client(**self.info)
        doc = None
        client.wsman_invoke(options, namespace, method, doc)
        mock_pywsman.invoke.assert_called_once_with(options, namespace, method)
        doc = 'fake-input'
        client.wsman_invoke(options, namespace, method, doc)
        mock_pywsman.invoke.assert_called_with(options, namespace, method, doc)

    def test_wsman_invoke_fail(self, mock_client_pywsman):
        namespace = resource_uris.CIM_BootSourceSetting
        result_xml = test_utils.build_soap_xml([{'ReturnValue':
                                                 '2'}],
                                               namespace)
        mock_doc = test_utils.mock_wsman_root(result_xml)
        mock_pywsman = mock_client_pywsman.Client.return_value
        mock_pywsman.invoke.return_value = mock_doc
        method = 'fake-method'
        options = mock.Mock(spec_set=[])

        client = amt_common.Client(**self.info)

        self.assertRaises(exception.AMTFailure,
                          client.wsman_invoke,
                          options, namespace, method)
        mock_pywsman.invoke.assert_called_once_with(options, namespace, method)


class AwakeAMTInterfaceTestCase(test_utils.BaseAMTTest):
    def setUp(self):
        super(AwakeAMTInterfaceTestCase, self).setUp()
        amt_common.AMT_AWAKE_CACHE = {}

    @mock.patch.object(utils, 'execute', spec_set=True, autospec=True)
    def test_awake_amt_interface(self, mock_ex):
        amt_common.awake_amt_interface(self.node)
        expected_args = ['ping', '-i', 0.2, '-c', 5, '1.2.3.4']
        mock_ex.assert_called_once_with(*expected_args)

    @mock.patch.object(utils, 'execute', spec_set=True, autospec=True)
    def test_awake_amt_interface_fail(self, mock_ex):
        mock_ex.side_effect = processutils.ProcessExecutionError('x')
        self.assertRaises(exception.AMTConnectFailure,
                          amt_common.awake_amt_interface,
                          self.node)

    @mock.patch.object(utils, 'execute', spec_set=True, autospec=True)
    def test_awake_amt_interface_in_cache_time(self, mock_ex):
        amt_common.AMT_AWAKE_CACHE[self.node.uuid] = time.time()
        amt_common.awake_amt_interface(self.node)
        self.assertFalse(mock_ex.called)

    @mock.patch.object(utils, 'execute', spec_set=True, autospec=True)
    def test_awake_amt_interface_disable(self, mock_ex):
        CONF.set_override('awake_interval', 0, 'amt_driver')
        amt_common.awake_amt_interface(self.node)
        self.assertFalse(mock_ex.called)

    def test_out_range_protocol(self):
        self.assertRaises(ValueError, cfg.CONF.set_override,
                          'protocol', 'fake', 'amt_driver')
