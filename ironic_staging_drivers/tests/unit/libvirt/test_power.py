# Copyright (c) 2016 Mirantis, Inc.
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

"""Test class for Ironic libvirt driver."""


import tempfile

import mock

from ironic.common import boot_devices
from ironic.common import exception
from ironic.common import states
from ironic.conductor import task_manager
from ironic.drivers import utils as driver_utils
from ironic.tests.unit.db import base as db_base
from ironic.tests.unit.objects import utils as obj_utils

from ironic_staging_drivers.common import exception as isd_exc
from ironic_staging_drivers.libvirt import power


def _get_test_libvirt_driver_info(auth_type='ssh_key'):
    if auth_type == 'ssh_key':
        return {
            'libvirt_uri': 'qemu+ssh://test@test/',
            'ssh_key_filename': '/test/key/file'
        }
    elif auth_type == 'sasl':
        return {
            'libvirt_uri': 'test+tcp://localhost:5000/test',
            'sasl_username': 'admin',
            'sasl_password': 'admin'
        }
    elif auth_type == 'no_uri':
        return {'ssh_key_filename': '/test/key/file'}
    elif auth_type == 'socket':
        return {'libvirt_uri': 'qemu+unix:///system?'
                               'socket=/opt/libvirt/run/libvirt-sock'}

    return{
        'libvirt_uri': 'qemu+ssh://test@test/',
        'ssh_key_filename': '/test/key/file',
        'sasl_username': 'admin',
        'sasl_password': 'admin'
    }


class FakeLibvirtDomain(object):
    def __init__(self, uuid=None):
        self.uuid = uuid

    def name(self):
        return 'test_libvirt_domain'

    def XMLDesc(self, boot_dev=power._BOOT_DEVICES_MAP[boot_devices.PXE]):
        return(
            """<domain type='qemu' id='4'>
                <name>test_libvirt_domain</name>
                <uuid>1be26c0b-03f2-4d2e-ae87-c02d7f33c123</uuid>
                <bootloader>/usr/bin/pygrub</bootloader>
                <os>
                    <type arch='x86_64' machine='pc-1.0'>hvm</type>
                    <boot dev='%(boot_dev)s'/>
                    <bios useserial='yes'/>
                </os>
                <memory>512000</memory>
                <vcpu>1</vcpu>
                <on_poweroff>destroy</on_poweroff>
                <on_reboot>restart</on_reboot>
                <on_crash>restart</on_crash>
                <devices>
                    <interface type='bridge'>
                        <source bridge='br0'/>
                        <mac address='00:16:3e:49:1d:11'/>
                        <script path='vif-bridge'/>
                    </interface>
                    <graphics type='vnc' port='5900'/>
                    <console tty='/dev/pts/4'/>
                    <interface type='network'>
                        <mac address='52:54:00:5c:b7:df'/>
                        <source network='brbm'/>
                        <virtualport type='openvswitch'>
                        <parameters interfaceid='5c20239f'/>
                        </virtualport>
                        <model type='e1000'/>
                    </interface>
                </devices>
            </domain>""") % {'boot_dev': boot_dev}


class FakeConnection(object):
    def listAllDomains(self):
        return [FakeLibvirtDomain()]


class BaseLibvirtTest(db_base.DbTestCase):
    def setUp(self):
        super(BaseLibvirtTest, self).setUp()
        self.config(enabled_hardware_types=['staging-libvirt'],
                    enabled_power_interfaces=['staging-libvirt'],
                    enabled_management_interfaces=['staging-libvirt'])


class LibvirtValidateParametersTestCase(BaseLibvirtTest):

    def test__parse_driver_info_good_ssh_key(self):
        d_info = _get_test_libvirt_driver_info('ssh_key')
        key_path = tempfile.mkdtemp() + '/test.key'
        with open(key_path, 'wt'):
            d_info['ssh_key_filename'] = key_path
            node = obj_utils.get_test_node(
                self.context,
                driver='staging-libvirt',
                driver_info=d_info)

            info = power._parse_driver_info(node)

        self.assertEqual('qemu+ssh://test@test/', info.get('libvirt_uri'))
        self.assertEqual(key_path, info.get('ssh_key_filename'))
        self.assertEqual(node['uuid'], info.get('uuid'))

    def test__parse_driver_info_no_ssh_key(self):
        node = obj_utils.get_test_node(
            self.context,
            driver='staging-libvirt',
            driver_info=_get_test_libvirt_driver_info('ssh_key'))

        self.assertRaises(exception.InvalidParameterValue,
                          power._parse_driver_info,
                          node)

    def test__parse_driver_info_good_sasl_cred(self):
        node = obj_utils.get_test_node(
            self.context,
            driver='staging-libvirt',
            driver_info=_get_test_libvirt_driver_info('sasl'))

        info = power._parse_driver_info(node)

        self.assertEqual('test+tcp://localhost:5000/test',
                         info.get('libvirt_uri'))
        self.assertEqual('admin', info.get('sasl_username'))
        self.assertEqual('admin', info.get('sasl_password'))
        self.assertEqual(node['uuid'], info.get('uuid'))

    def test__parse_driver_info_sasl_and_ssh_key(self):
        node = obj_utils.get_test_node(
            self.context,
            driver='staging-libvirt',
            driver_info=_get_test_libvirt_driver_info('ssh_sasl'))

        self.assertRaises(exception.InvalidParameterValue,
                          power._parse_driver_info,
                          node)


class LibvirtPrivateMethodsTestCase(BaseLibvirtTest):

    @mock.patch.object(power.libvirt, 'openAuth', autospec=True)
    def test__get_libvirt_connection_sasl_auth(self, libvirt_open_mock):
        node = obj_utils.get_test_node(
            self.context,
            driver='staging-libvirt',
            driver_info=_get_test_libvirt_driver_info('sasl'))
        power._get_libvirt_connection(node['driver_info'])

        libvirt_open_mock.assert_called_once_with(
            'test+tcp://localhost:5000/test',
            [[power.libvirt.VIR_CRED_AUTHNAME,
              power.libvirt.VIR_CRED_PASSPHRASE],
             mock.ANY,  # Inline cred function
             None], 0)

    @mock.patch.object(power.libvirt, 'open', autospec=True)
    def test__get_libvirt_connection_ssh(self, libvirt_open_mock):
        node = obj_utils.get_test_node(
            self.context,
            driver='staging-libvirt',
            driver_info=_get_test_libvirt_driver_info('ssh_key'))
        power._get_libvirt_connection(node['driver_info'])

        libvirt_open_mock.assert_called_once_with(
            'qemu+ssh://test@test/?keyfile=/test/key/file&no_verify=1')

    @mock.patch.object(power.libvirt, 'open', autospec=True)
    def test__get_libvirt_connection_socket(self, libvirt_open_mock):
        node = obj_utils.get_test_node(
            self.context,
            driver='staging-libvirt',
            driver_info=_get_test_libvirt_driver_info('socket'))
        power._get_libvirt_connection(node['driver_info'])

        libvirt_open_mock.assert_called_once_with(
            'qemu+unix:///system?socket=/opt/libvirt/run/libvirt-sock')

    @mock.patch.object(power.libvirt, 'open',
                       side_effect=power.libvirt.libvirtError('Error'))
    def test__get_libvirt_connection_error_conn(self, libvirt_open_mock):
        node = obj_utils.get_test_node(
            self.context,
            driver='staging-libvirt',
            driver_info=_get_test_libvirt_driver_info('socket'))
        self.assertRaises(isd_exc.LibvirtError,
                          power._get_libvirt_connection,
                          node['driver_info'])

    @mock.patch.object(power.libvirt, 'open',
                       return_value=None)
    def test__get_libvirt_connection_error_none_conn(self, libvirt_open_mock):
        node = obj_utils.get_test_node(
            self.context,
            driver='staging-libvirt',
            driver_info=_get_test_libvirt_driver_info('socket'))
        self.assertRaises(isd_exc.LibvirtError,
                          power._get_libvirt_connection,
                          node['driver_info'])

    @mock.patch.object(power, '_get_libvirt_connection',
                       return_value=FakeConnection())
    def test__get_domain_by_macs(self, libvirt_conn_mock):
        self.config(enabled_drivers=["staging-libvirt"])
        node = obj_utils.create_test_node(
            self.context,
            driver='staging-libvirt',
            driver_info=_get_test_libvirt_driver_info('socket'))
        obj_utils.create_test_port(self.context,
                                   node_id=node.id,
                                   address='00:16:3e:49:1d:11')

        with task_manager.acquire(self.context, node.uuid,
                                  shared=True) as task:
            domain = power._get_domain_by_macs(task)

        self.assertEqual('test_libvirt_domain', domain.name())

    @mock.patch.object(power, '_get_libvirt_connection',
                       return_value=FakeConnection())
    def test__get_domain_by_macs_not_found(self, libvirt_conn_mock):
        self.config(enabled_drivers=["staging-libvirt"])
        node = obj_utils.create_test_node(
            self.context,
            driver='staging-libvirt',
            driver_info=_get_test_libvirt_driver_info('socket'))
        obj_utils.create_test_port(self.context,
                                   node_id=node.id,
                                   address='00:17:3a:50:12:12')

        with task_manager.acquire(self.context, node.uuid,
                                  shared=True) as task:

            self.assertRaises(exception.NodeNotFound,
                              power._get_domain_by_macs, task)

    def test__get_power_state_on(self):
        domain_mock = mock.Mock()
        domain_mock.isActive = mock.MagicMock(return_value=True)

        state = power._get_power_state(domain_mock)

        domain_mock.isActive.assert_called_once_with()
        self.assertEqual(states.POWER_ON, state)

    def test__get_power_state_off(self):
        domain_mock = mock.Mock()
        domain_mock.isActive = mock.Mock(return_value=False)

        state = power._get_power_state(domain_mock)

        domain_mock.isActive.assert_called_once_with()
        self.assertEqual(states.POWER_OFF, state)

    def test__get_power_state_error(self):
        domain_mock = mock.Mock()
        domain_mock.isActive = mock.MagicMock(
            side_effect=power.libvirt.libvirtError('Test'))

        self.assertRaises(isd_exc.LibvirtError,
                          power._get_power_state,
                          domain_mock)

    @mock.patch.object(power, '_power_off', autospec=True)
    @mock.patch.object(power, '_power_on', return_value=states.POWER_ON)
    def test__power_cycle(self, power_on_mock, power_off_mock):
        power._power_cycle('fake domain')

        power_on_mock.assert_called_once_with('fake domain')
        power_off_mock.assert_called_once_with('fake domain')

    @mock.patch.object(power, '_power_off', autospec=True)
    @mock.patch.object(power, '_power_on', return_value=states.POWER_OFF)
    def test__power_cycle_failure(self, power_on_mock, power_off_mock):
        self.assertRaises(exception.PowerStateFailure,
                          power._power_cycle,
                          'fake domain')
        power_off_mock.assert_called_once_with('fake domain')

    @mock.patch.object(power, '_power_off', autospec=True)
    @mock.patch.object(power, '_power_on',
                       side_effect=power.libvirt.libvirtError('Test'))
    def test__power_cycle_error_conn(self, power_on_mock, power_off_mock):
        self.assertRaises(isd_exc.LibvirtError,
                          power._power_cycle,
                          'fake domain')
        power_off_mock.assert_called_once_with('fake domain')

    @mock.patch.object(power, '_get_power_state',
                       return_value=states.POWER_ON)
    def test__power_on_on(self, get_power_mock):
        state = power._power_on('fake domain')

        get_power_mock.assert_called_once_with('fake domain')
        self.assertEqual(states.POWER_ON, state)

    @mock.patch.object(power, '_get_power_state',
                       side_effect=[states.POWER_OFF, states.POWER_ON])
    def test__power_on_off(self, get_power_mock):
        domain_mock = mock.Mock()
        domain_mock.create = mock.Mock()

        state = power._power_on(domain_mock)

        get_power_mock.assert_called_with(domain_mock)
        domain_mock.create.assert_called_once_with()
        self.assertEqual(states.POWER_ON, state)

    @mock.patch.object(power, '_get_power_state',
                       side_effect=[states.POWER_OFF, states.POWER_OFF])
    def test__power_on_error_state(self, get_power_mock):
        domain_mock = mock.Mock()
        domain_mock.create = mock.Mock()

        state = power._power_on(domain_mock)

        get_power_mock.assert_called_with(domain_mock)
        domain_mock.create.assert_called_once_with()
        self.assertEqual(states.ERROR, state)

    @mock.patch.object(power, '_get_power_state',
                       return_value=states.POWER_OFF)
    def test__power_on_error(self, get_power_mock):
        domain_mock = mock.Mock()
        domain_mock.create = mock.Mock(
            side_effect=power.libvirt.libvirtError('Test'))

        self.assertRaises(isd_exc.LibvirtError,
                          power._power_on,
                          domain_mock)
        get_power_mock.assert_called_with(domain_mock)

    @mock.patch.object(power, '_get_power_state',
                       return_value=states.POWER_OFF)
    def test__power_off_off(self, get_power_mock):
        state = power._power_off('fake domain')

        get_power_mock.assert_called_once_with('fake domain')
        self.assertEqual(states.POWER_OFF, state)

    @mock.patch.object(power, '_get_power_state',
                       side_effect=[states.POWER_ON, states.POWER_OFF])
    def test__power_off_on(self, get_power_mock):
        domain_mock = mock.Mock()
        domain_mock.destroy = mock.Mock()

        state = power._power_off(domain_mock)

        get_power_mock.assert_called_with(domain_mock)
        domain_mock.destroy.assert_called_once_with()
        self.assertEqual(states.POWER_OFF, state)

    @mock.patch.object(power, '_get_power_state',
                       side_effect=[states.POWER_ON, states.POWER_ON])
    def test__power_off_error_state(self, get_power_mock):
        domain_mock = mock.Mock()
        domain_mock.destroy = mock.Mock()

        state = power._power_off(domain_mock)

        get_power_mock.assert_called_with(domain_mock)
        domain_mock.destroy.assert_called_once_with()
        self.assertEqual(states.ERROR, state)

    @mock.patch.object(power, '_get_power_state',
                       return_value=states.POWER_ON)
    def test__power_off_error(self, get_power_mock):
        domain_mock = mock.Mock()
        domain_mock.destroy = mock.Mock(
            side_effect=power.libvirt.libvirtError('Test'))

        self.assertRaises(isd_exc.LibvirtError,
                          power._power_off,
                          domain_mock)
        get_power_mock.assert_called_with(domain_mock)

    def test__get_boot_device(self):
        domain = FakeLibvirtDomain()

        boot_dev = power._get_boot_device(domain)

        self.assertEqual(power._BOOT_DEVICES_MAP[boot_devices.PXE],
                         boot_dev)

    def test__set_boot_device(self):
        conn = mock.Mock(defineXML=mock.Mock())
        domain = FakeLibvirtDomain()

        power._set_boot_device(
            conn, domain, power._BOOT_DEVICES_MAP[boot_devices.DISK])

        conn.defineXML.assert_called_once_with(mock.ANY)

    def test__set_boot_device_error(self):
        conn = mock.Mock(defineXML=mock.Mock(
            side_effect=power.libvirt.libvirtError('Test')))
        domain = FakeLibvirtDomain()

        self.assertRaises(isd_exc.LibvirtError,
                          power._set_boot_device,
                          conn, domain,
                          power._BOOT_DEVICES_MAP[boot_devices.DISK])


class LibvirtPowerTestCase(BaseLibvirtTest):

    def setUp(self):
        super(LibvirtPowerTestCase, self).setUp()
        self.node = obj_utils.create_test_node(
            self.context,
            driver='staging-libvirt',
            driver_info=_get_test_libvirt_driver_info('sasl'))
        obj_utils.create_test_port(self.context,
                                   node_id=self.node.id,
                                   address='52:54:00:5c:b7:df')

    def test_get_properties(self):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            properties = task.driver.management.get_properties()

            self.assertIn('libvirt_uri', properties)
            self.assertIn('sasl_username', properties)
            self.assertIn('sasl_password', properties)
            self.assertIn('ssh_key_filename', properties)

    @mock.patch.object(driver_utils, 'get_node_mac_addresses', autospec=True)
    def test_validate(self, get_node_macs_mock):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.power.validate(task)

            get_node_macs_mock.assert_called_once_with(task)

    @mock.patch.object(power.driver_utils,
                       'get_node_mac_addresses', autospec=True)
    def test_validate_conn_miss_mac(self, get_node_mac_mock):
        get_node_mac_mock.return_value = None

        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.MissingParameterValue,
                              task.driver.power.validate,
                              task)
            get_node_mac_mock.assert_called_once_with(task)

    @mock.patch.object(power, '_get_power_state', autospec=True)
    @mock.patch.object(power, '_get_domain_by_macs', autospec=True)
    def test_get_power_state(self, get_domain_mock, get_power_state):
        domain = FakeLibvirtDomain()
        get_domain_mock.return_value = domain

        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.power.get_power_state(task)

            get_domain_mock.assert_called_once_with(task)
            get_power_state.assert_called_once_with(domain)

    @mock.patch.object(power.LOG, 'warning')
    @mock.patch.object(power, '_power_on', autospec=True)
    @mock.patch.object(power, '_get_domain_by_macs', autospec=True)
    def test_set_power_state_on(self, get_domain_mock, power_on_mock,
                                log_mock):
        domain = FakeLibvirtDomain()
        get_domain_mock.return_value = domain
        power_on_mock.return_value = states.POWER_ON

        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.power.set_power_state(task, states.POWER_ON)

            get_domain_mock.assert_called_once_with(task)
            power_on_mock.assert_called_once_with(domain)
            self.assertFalse(log_mock.called)

    @mock.patch.object(power.LOG, 'warning')
    @mock.patch.object(power, '_power_on', autospec=True)
    @mock.patch.object(power, '_get_domain_by_macs', autospec=True)
    def test_set_power_state_on_timeout(self, get_domain_mock, power_on_mock,
                                        log_mock):
        domain = FakeLibvirtDomain()
        get_domain_mock.return_value = domain
        power_on_mock.return_value = states.POWER_ON

        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.power.set_power_state(task, states.POWER_ON,
                                              timeout=42)

            get_domain_mock.assert_called_once_with(task)
            power_on_mock.assert_called_once_with(domain)
            self.assertTrue(log_mock.called)

    @mock.patch.object(power, '_power_off', autospec=True)
    @mock.patch.object(power, '_get_domain_by_macs', autospec=True)
    def test_set_power_state_off(self, get_domain_mock, power_off_mock):
        domain = FakeLibvirtDomain()
        get_domain_mock.return_value = domain
        power_off_mock.return_value = states.POWER_OFF

        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.power.set_power_state(task, states.POWER_OFF)

            get_domain_mock.assert_called_once_with(task)
            power_off_mock.assert_called_once_with(domain)

    @mock.patch.object(power, '_power_on', autospec=True)
    @mock.patch.object(power, '_get_domain_by_macs', autospec=True)
    def test_set_power_state_on_failure(self, get_domain_mock,
                                        power_on_mock):
        domain = FakeLibvirtDomain()
        get_domain_mock.return_value = domain
        power_on_mock.return_value = states.POWER_OFF

        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.PowerStateFailure,
                              task.driver.power.set_power_state,
                              task, states.POWER_ON)

            get_domain_mock.assert_called_once_with(task)
            power_on_mock.assert_called_once_with(domain)

    @mock.patch.object(power, '_get_domain_by_macs', autospec=True)
    def test_set_power_state_invalid_state(self, get_domain_mock):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.InvalidParameterValue,
                              task.driver.power.set_power_state,
                              task, 'wrong_state')

            get_domain_mock.assert_called_once_with(task)


class LibvirtManagementTestCase(BaseLibvirtTest):

    def setUp(self):
        super(LibvirtManagementTestCase, self).setUp()
        self.node = obj_utils.create_test_node(
            self.context,
            driver='staging-libvirt',
            driver_info=_get_test_libvirt_driver_info('sasl'))
        obj_utils.create_test_port(self.context,
                                   node_id=self.node.id,
                                   address='52:54:00:5c:b7:df')

    def test_get_properties(self):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            properties = task.driver.management.get_properties()

            self.assertIn('libvirt_uri', properties)
            self.assertIn('sasl_username', properties)
            self.assertIn('sasl_password', properties)
            self.assertIn('ssh_key_filename', properties)

    def test_get_supported_boot_devices(self):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            devices = task.driver.management.get_supported_boot_devices(task)

            self.assertIn(boot_devices.PXE, devices)
            self.assertIn(boot_devices.DISK, devices)
            self.assertIn(boot_devices.CDROM, devices)

    @mock.patch.object(power, '_parse_driver_info', autospec=True)
    def test_validate(self, parse_info_mock):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:

            task.driver.management.validate(task)
            parse_info_mock.assert_called_once_with(task.node)

    @mock.patch.object(power, '_get_domain_by_macs',
                       return_value=FakeLibvirtDomain())
    def test_get_boot_device_ok(self, get_domain_mock):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            result = task.driver.management.get_boot_device(task)

            get_domain_mock.assert_called_once_with(task)

            self.assertEqual(power._BOOT_DEVICES_MAP[boot_devices.PXE],
                             result['boot_device'])
            self.assertIsNone(result['persistent'])

    @mock.patch.object(power, '_get_boot_device', return_value=None)
    @mock.patch.object(power, '_get_domain_by_macs', autospec=True)
    def test_get_boot_device_invalid(self, get_domain_mock, get_boot_dev_mock):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            result = task.driver.management.get_boot_device(task)

            self.assertIsNone(result['boot_device'])
            self.assertIsNone(result['persistent'])

    @mock.patch.object(power, '_set_boot_device', autospec=True)
    @mock.patch.object(power, '_get_libvirt_connection', autospec=True)
    @mock.patch.object(power, '_get_domain_by_macs', autospec=True)
    def test_set_boot_device_ok(self, get_domain_mock, get_conn_mock,
                                set_boot_dev_mock):
        fake_domain = FakeLibvirtDomain()
        get_domain_mock.return_value = fake_domain
        get_conn_mock.return_value = 'fake conn'

        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.management.set_boot_device(task, boot_devices.PXE)

            get_domain_mock.assert_called_once_with(task)
            get_conn_mock.assert_called_once_with(
                {'uuid': self.node.uuid,
                 'libvirt_uri': 'test+tcp://localhost:5000/test',
                 'sasl_password': 'admin',
                 'sasl_username': 'admin',
                 'ssh_key_filename': None})
            set_boot_dev_mock.assert_called_once_with(
                'fake conn', fake_domain,
                power._BOOT_DEVICES_MAP[boot_devices.PXE])

    @mock.patch.object(power, '_get_libvirt_connection', autospec=True)
    @mock.patch.object(power, '_get_domain_by_macs', autospec=True)
    def test_set_boot_device_wrong(self, get_domain_mock, get_conn_mock):
        fake_domain = FakeLibvirtDomain()
        get_domain_mock.return_value = fake_domain
        get_conn_mock.return_value = 'fake conn'

        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaises(exception.InvalidParameterValue,
                              task.driver.management.set_boot_device,
                              task, boot_devices.BIOS)

            get_domain_mock.assert_called_once_with(task)
            get_conn_mock.assert_called_once_with(
                {'uuid': self.node.uuid,
                 'libvirt_uri': 'test+tcp://localhost:5000/test',
                 'sasl_password': 'admin',
                 'sasl_username': 'admin',
                 'ssh_key_filename': None})
