# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ironic.common import dhcp_factory
from ironic.common import exception
from ironic.common import states
from ironic.common import utils as com_utils
from ironic.conductor import task_manager
from ironic.conductor import utils
from ironic.drivers.modules import deploy_utils
from ironic.drivers.modules import fake
from ironic.drivers.modules import pxe
from ironic.tests.unit.conductor import mgr_utils
from ironic.tests.unit.db import base as db_base
from ironic.tests.unit.objects import utils as object_utils
from ironic_lib import utils as irlib_utils
import mock
from oslo_concurrency import processutils
import six

from ironic_staging_drivers.ansible import deploy as ansible_deploy


INSTANCE_INFO = {
    'image_source': 'fake-image',
    'image_url': 'http://image',
    'image_checksum': 'checksum',
    'image_disk_format': 'qcow2',
    'root_mb': 5120,
    'swap_mb': 0,
    'ephemeral_mb': 0
}

DRIVER_INFO = {
    'deploy_kernel': 'glance://deploy_kernel_uuid',
    'deploy_ramdisk': 'glance://deploy_ramdisk_uuid',
    'ansible_deploy_username': 'test',
    'ansible_deploy_key_file': '/path/key',
}
DRIVER_INTERNAL_INFO = {
    'ansible_cleaning_ip': '127.0.0.1',
    'is_whole_disk_image': True,
    'clean_steps': []
}


class TestAnsibleMethods(db_base.DbTestCase):
    def setUp(self):
        super(TestAnsibleMethods, self).setUp()
        mgr_utils.mock_the_extension_manager(driver='fake_ansible')
        node = {
            'driver': 'fake_ansible',
            'instance_info': INSTANCE_INFO,
            'driver_info': DRIVER_INFO,
            'driver_internal_info': DRIVER_INTERNAL_INFO,
        }
        self.node = object_utils.create_test_node(self.context, **node)

    def test__parse_ansible_driver_info(self):
        playbook, user, key = ansible_deploy._parse_ansible_driver_info(
            self.node, 'deploy')
        self.assertEqual(ansible_deploy.DEFAULT_PLAYBOOKS['deploy'], playbook)
        self.assertEqual('test', user)
        self.assertEqual('/path/key', key)

    def test__parse_ansible_driver_info_no_playbook(self):
        self.assertRaises(exception.IronicException,
                          ansible_deploy._parse_ansible_driver_info,
                          self.node, 'test')

    def test__get_node_ip_dhcp(self):
        dhcp_provider_mock = mock.Mock()
        dhcp_factory.DHCPFactory._dhcp_provider = dhcp_provider_mock
        dhcp_provider_mock.get_ip_addresses.return_value = ['ip']
        with task_manager.acquire(self.context, self.node.uuid) as task:
            ansible_deploy._get_node_ip_dhcp(task)
            dhcp_provider_mock.get_ip_addresses.assert_called_once_with(
                task)

    def test__get_node_ip_dhcp_no_ip(self):
        dhcp_provider_mock = mock.Mock()
        dhcp_factory.DHCPFactory._dhcp_provider = dhcp_provider_mock
        dhcp_provider_mock.get_ip_addresses.return_value = []
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(exception.FailedToGetIPAddressOnPort,
                              ansible_deploy._get_node_ip_dhcp, task)

    def test__get_node_ip_dhcp_multiple_ip(self):
        # self.config(group='ansible', use_ramdisk_callback=False)
        # di_info = self.node.driver_internal_info
        # di_info.pop('ansible_cleaning_ip')
        # self.node.driver_internal_info = di_info
        # self.node.save()
        dhcp_provider_mock = mock.Mock()
        dhcp_factory.DHCPFactory._dhcp_provider = dhcp_provider_mock
        dhcp_provider_mock.get_ip_addresses.return_value = ['ip1', 'ip2']
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(exception.InstanceDeployFailure,
                              ansible_deploy._get_node_ip_dhcp, task)

    def test__get_node_ip_heartbeat(self):
        di_info = self.node.driver_internal_info
        di_info['agent_url'] = 'http://1.2.3.4:5678'
        self.node.driver_internal_info = di_info
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertEqual('1.2.3.4',
                             ansible_deploy._get_node_ip_heartbeat(task))

    @mock.patch.object(ansible_deploy, '_get_node_ip_heartbeat',
                       return_value='127.0.0.1', autospec=True)
    @mock.patch.object(ansible_deploy, '_get_node_ip_dhcp',
                       return_value='127.0.0.1', autospec=True)
    def test__get_node_ip_callback(self, ip_dhcp_mock, ip_agent_mock):
        self.config(group='ansible', use_ramdisk_callback=True)
        with task_manager.acquire(self.context, self.node.uuid) as task:
            res = ansible_deploy._get_node_ip(task)
            self.assertEqual(0, ip_dhcp_mock.call_count)
            ip_agent_mock.assert_called_once_with(task)
            self.assertEqual('127.0.0.1', res)

    @mock.patch.object(ansible_deploy, '_get_node_ip_heartbeat',
                       return_value='127.0.0.1', autospec=True)
    @mock.patch.object(ansible_deploy, '_get_node_ip_dhcp',
                       return_value='127.0.0.1', autospec=True)
    def test__get_node_ip_no_callback(self, ip_dhcp_mock, ip_agent_mock):
        self.config(group='ansible', use_ramdisk_callback=False)
        with task_manager.acquire(self.context, self.node.uuid) as task:
            res = ansible_deploy._get_node_ip(task)
            self.assertEqual(0, ip_agent_mock.call_count)
            ip_dhcp_mock.assert_called_once_with(task)
            self.assertEqual('127.0.0.1', res)

    @mock.patch.object(com_utils, 'execute', return_value=('out', 'err'),
                       autospec=True)
    def test__run_playbook(self, execute_mock):
        self.config(group='ansible', playbooks_path='/path/to/playbooks')
        self.config(group='ansible', config_file_path='/path/to/config')
        self.config(group='ansible', verbosity=3)
        self.config(group='ansible', ansible_extra_args='--timeout=100')
        extra_vars = {'foo': 'bar'}

        ansible_deploy._run_playbook('deploy', extra_vars, '/path/to/key',
                                     tags=['spam'], notags=['ham'])

        execute_mock.assert_called_once_with(
            'env', 'ANSIBLE_CONFIG=/path/to/config',
            'ansible-playbook', '/path/to/playbooks/deploy', '-i',
            ansible_deploy.INVENTORY_FILE, '-e', '{"ironic": {"foo": "bar"}}',
            '--tags=spam', '--skip-tags=ham',
            '--private-key=/path/to/key', '-vvv', '--timeout=100')

    @mock.patch.object(com_utils, 'execute', return_value=('out', 'err'),
                       autospec=True)
    def test__run_playbook_default_verbosity_nodebug(self, execute_mock):
        self.config(group='ansible', playbooks_path='/path/to/playbooks')
        self.config(group='ansible', config_file_path='/path/to/config')
        self.config(debug=False)
        extra_vars = {'foo': 'bar'}

        ansible_deploy._run_playbook('deploy', extra_vars, '/path/to/key')

        execute_mock.assert_called_once_with(
            'env', 'ANSIBLE_CONFIG=/path/to/config',
            'ansible-playbook', '/path/to/playbooks/deploy', '-i',
            ansible_deploy.INVENTORY_FILE, '-e', '{"ironic": {"foo": "bar"}}',
            '--private-key=/path/to/key')

    @mock.patch.object(com_utils, 'execute', return_value=('out', 'err'),
                       autospec=True)
    def test__run_playbook_default_verbosity_debug(self, execute_mock):
        self.config(group='ansible', playbooks_path='/path/to/playbooks')
        self.config(group='ansible', config_file_path='/path/to/config')
        self.config(debug=True)
        extra_vars = {'foo': 'bar'}

        ansible_deploy._run_playbook('deploy', extra_vars, '/path/to/key')

        execute_mock.assert_called_once_with(
            'env', 'ANSIBLE_CONFIG=/path/to/config',
            'ansible-playbook', '/path/to/playbooks/deploy', '-i',
            ansible_deploy.INVENTORY_FILE, '-e', '{"ironic": {"foo": "bar"}}',
            '--private-key=/path/to/key', '-vvvv')

    @mock.patch.object(com_utils, 'execute',
                       side_effect=processutils.ProcessExecutionError(
                           description='VIKINGS!'),
                       autospec=True)
    def test__run_playbook_fail(self, execute_mock):
        self.config(group='ansible', playbooks_path='/path/to/playbooks')
        self.config(group='ansible', config_file_path='/path/to/config')
        self.config(debug=False)
        extra_vars = {'foo': 'bar'}

        exc = self.assertRaises(exception.InstanceDeployFailure,
                                ansible_deploy._run_playbook,
                                'deploy', extra_vars, '/path/to/key')
        self.assertIn('VIKINGS!', six.text_type(exc))
        execute_mock.assert_called_once_with(
            'env', 'ANSIBLE_CONFIG=/path/to/config',
            'ansible-playbook', '/path/to/playbooks/deploy', '-i',
            ansible_deploy.INVENTORY_FILE, '-e', '{"ironic": {"foo": "bar"}}',
            '--private-key=/path/to/key')

    def test__parse_partitioning_info_root_msdos(self):
        expected_info = {
            'partition_info': {
                'label': 'msdos',
                'partitions': [
                    {'unit': 'MiB',
                     'size': INSTANCE_INFO['root_mb'],
                     'name': 'root',
                     'flags': {'boot': 'yes'}}
                ]}}

        i_info = ansible_deploy._parse_partitioning_info(self.node)

        self.assertEqual(expected_info, i_info)

    def test__parse_partitioning_info_all_gpt(self):
        in_info = dict(INSTANCE_INFO)
        in_info['swap_mb'] = 128
        in_info['ephemeral_mb'] = 256
        in_info['ephemeral_format'] = 'ext4'
        in_info['preserve_ephemeral'] = True
        in_info['configdrive'] = 'some-fake-user-data'
        in_info['capabilities'] = {'disk_label': 'gpt'}
        self.node.instance_info = in_info
        self.node.save()

        expected_info = {
            'partition_info': {
                'label': 'gpt',
                'ephemeral_format': 'ext4',
                'preserve_ephemeral': 'yes',
                'partitions': [
                    {'unit': 'MiB',
                     'size': 1,
                     'name': 'bios',
                     'flags': {'bios_grub': 'yes'}},
                    {'unit': 'MiB',
                     'size': 256,
                     'name': 'ephemeral',
                     'format': 'ext4'},
                    {'unit': 'MiB',
                     'size': 128,
                     'name': 'swap',
                     'format': 'linux-swap'},
                    {'unit': 'MiB',
                     'size': 64,
                     'name': 'configdrive',
                     'format': 'fat32'},
                    {'unit': 'MiB',
                     'size': INSTANCE_INFO['root_mb'],
                     'name': 'root'}
                ]}}

        i_info = ansible_deploy._parse_partitioning_info(self.node)

        self.assertEqual(expected_info, i_info)

    @mock.patch.object(ansible_deploy.images, 'download_size', autospec=True)
    def test__calculate_memory_req(self, image_mock):
        self.config(group='ansible', extra_memory=1)
        image_mock.return_value = 2000000  # < 2MiB

        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertEqual(2, ansible_deploy._calculate_memory_req(task))
            image_mock.assert_called_once_with(task.context, 'fake-image')

    def test__get_configdrive_path(self):
        self.config(tempdir='/path/to/tmpdir')
        self.assertEqual('/path/to/tmpdir/spam.cndrive',
                         ansible_deploy._get_configdrive_path('spam'))

    def test__prepare_extra_vars(self):
        host_list = [('fake-uuid', '1.2.3.4', 'spam', 'ham'),
                     ('other-uuid', '5.6.7.8', 'eggs', 'vikings')]
        ansible_vars = {"foo": "bar"}
        self.assertEqual(
            {"nodes": [
                {"name": "fake-uuid", "ip": '1.2.3.4',
                 "user": "spam", "extra": "ham"},
                {"name": "other-uuid", "ip": '5.6.7.8',
                 "user": "eggs", "extra": "vikings"}],
                "foo": "bar"},
            ansible_deploy._prepare_extra_vars(host_list, ansible_vars))

    def test__parse_root_device_hints(self):
        hints = {"wwn": "fake wwn", "size": "12345", "rotational": True}
        expected = {"wwn": "fake wwn", "size": 12345, "rotational": True}
        props = self.node.properties
        props['root_device'] = hints
        self.node.properties = props
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertEqual(
                expected, ansible_deploy._parse_root_device_hints(task.node))

    def test__parse_root_device_hints_fail_advanced(self):
        hints = {"wwn": "s!= fake wwn",
                 "size": ">= 12345",
                 "name": "<or> spam <or> ham",
                 "rotational": True}
        expected = {"wwn": "s!= fake%20wwn",
                    "name": "<or> spam <or> ham",
                    "size": ">= 12345"}
        props = self.node.properties
        props['root_device'] = hints
        self.node.properties = props
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid) as task:
            exc = self.assertRaises(
                exception.InvalidParameterValue,
                ansible_deploy._parse_root_device_hints, task.node)
            for key, value in expected.items():
                self.assertIn(six.text_type(key), six.text_type(exc))
                self.assertIn(six.text_type(value), six.text_type(exc))

    @mock.patch.object(ansible_deploy, '_calculate_memory_req', autospec=True,
                       return_value=2000)
    def test__prepare_variables(self, mem_req_mock):
        expected = {"image": {"url": "http://image",
                              "source": "fake-image",
                              "mem_req": 2000,
                              "disk_format": "qcow2",
                              "checksum": "md5:checksum"}}
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertEqual(expected,
                             ansible_deploy._prepare_variables(task))

    @mock.patch.object(ansible_deploy, '_calculate_memory_req', autospec=True,
                       return_value=2000)
    def test__prepare_variables_root_device_hints(self, mem_req_mock):
        props = self.node.properties
        props['root_device'] = {"wwn": "fake-wwn"}
        self.node.properties = props
        self.node.save()
        expected = {"image": {"url": "http://image",
                              "source": "fake-image",
                              "mem_req": 2000,
                              "disk_format": "qcow2",
                              "checksum": "md5:checksum"},
                    "root_device_hints": {"wwn": "fake-wwn"}}
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertEqual(expected,
                             ansible_deploy._prepare_variables(task))

    @mock.patch.object(ansible_deploy, '_calculate_memory_req', autospec=True,
                       return_value=2000)
    def test__prepare_variables_noglance(self, mem_req_mock):
        i_info = self.node.instance_info
        i_info['image_checksum'] = 'sha256:checksum'
        self.node.instance_info = i_info
        self.node.save()
        expected = {"image": {"url": "http://image",
                              "source": "fake-image",
                              "mem_req": 2000,
                              "disk_format": "qcow2",
                              "checksum": "sha256:checksum"}}
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertEqual(expected,
                             ansible_deploy._prepare_variables(task))

    @mock.patch.object(ansible_deploy, '_calculate_memory_req', autospec=True,
                       return_value=2000)
    def test__prepare_variables_configdrive_url(self, mem_req_mock):
        i_info = self.node.instance_info
        i_info['configdrive'] = 'http://configdrive_url'
        self.node.instance_info = i_info
        self.node.save()
        expected = {"image": {"url": "http://image",
                              "source": "fake-image",
                              "mem_req": 2000,
                              "disk_format": "qcow2",
                              "checksum": "md5:checksum"},
                    'configdrive': {'type': 'url',
                                    'location': 'http://configdrive_url'}}
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertEqual(expected,
                             ansible_deploy._prepare_variables(task))

    @mock.patch.object(ansible_deploy, '_calculate_memory_req', autospec=True,
                       return_value=2000)
    def test__prepare_variables_configdrive_file(self, mem_req_mock):
        i_info = self.node.instance_info
        i_info['configdrive'] = 'fake-content'
        self.node.instance_info = i_info
        self.node.save()
        self.config(tempdir='/path/to/tmpfiles')
        expected = {"image": {"url": "http://image",
                              "source": "fake-image",
                              "mem_req": 2000,
                              "disk_format": "qcow2",
                              "checksum": "md5:checksum"},
                    'configdrive': {'type': 'file',
                                    'location': '/path/to/tmpfiles/%s.cndrive'
                                    % self.node.uuid}}
        with mock.patch.object(ansible_deploy, 'open', mock.mock_open(),
                               create=True) as open_mock:
            with task_manager.acquire(self.context, self.node.uuid) as task:
                self.assertEqual(expected,
                                 ansible_deploy._prepare_variables(task))
            open_mock.assert_has_calls((
                mock.call('/path/to/tmpfiles/%s.cndrive' % self.node.uuid,
                          'w'),
                mock.call().__enter__(),
                mock.call().write('fake-content'),
                mock.call().__exit__(None, None, None)))

    def test__validate_clean_steps(self):
        steps = [{"interface": "deploy",
                  "name": "foo",
                  "args": {"spam": {"required": True, "value": "ham"}}},
                 {"name": "bar",
                  "interface": "deploy"}]
        self.assertIsNone(ansible_deploy._validate_clean_steps(
            steps, self.node.uuid))

    def test__validate_clean_steps_missing(self):
        steps = [{"name": "foo",
                  "interface": "deploy",
                  "args": {"spam": {"value": "ham"},
                           "ham": {"required": True}}},
                 {"name": "bar"},
                 {"interface": "deploy"}]
        exc = self.assertRaises(exception.NodeCleaningFailure,
                                ansible_deploy._validate_clean_steps,
                                steps, self.node.uuid)
        self.assertIn("name foo, field ham.value", six.text_type(exc))
        self.assertIn("name bar, field interface", six.text_type(exc))
        self.assertIn("name undefined, field name", six.text_type(exc))

    def test__validate_clean_steps_names_not_unique(self):
        steps = [{"name": "foo",
                  "interface": "deploy"},
                 {"name": "foo",
                  "interface": "deploy"}]
        exc = self.assertRaises(exception.NodeCleaningFailure,
                                ansible_deploy._validate_clean_steps,
                                steps, self.node.uuid)
        self.assertIn("unique names", six.text_type(exc))

    @mock.patch.object(ansible_deploy.yaml, 'safe_load', autospec=True)
    def test__get_clean_steps(self, load_mock):
        steps = [{"interface": "deploy",
                  "name": "foo",
                  "args": {"spam": {"required": True, "value": "ham"}}},
                 {"name": "bar",
                  "interface": "deploy",
                  "priority": 100}]
        load_mock.return_value = steps
        expected = [{"interface": "deploy",
                     "step": "foo",
                     "priority": 10,
                     "abortable": False,
                     "argsinfo": {"spam": {"required": True}},
                     "args": {"spam": "ham"}},
                    {"interface": "deploy",
                     "step": "bar",
                     "priority": 100,
                     "abortable": False,
                     "argsinfo": {},
                     "args": {}}]
        d_info = self.node.driver_info
        d_info['ansible_clean_steps_config'] = 'custom_clean'
        self.node.driver_info = d_info
        self.node.save()
        self.config(group='ansible', playbooks_path='/path/to/playbooks')

        with mock.patch.object(ansible_deploy, 'open', mock.mock_open(),
                               create=True) as open_mock:
            self.assertEqual(
                expected,
                ansible_deploy._get_clean_steps(
                    self.node, interface="deploy",
                    override_priorities={"foo": 10}))
            open_mock.assert_has_calls((
                mock.call('/path/to/playbooks/custom_clean'),))
            load_mock.assert_called_once_with(
                open_mock().__enter__.return_value)


class TestAnsibleDeploy(db_base.DbTestCase):
    def setUp(self):
        super(TestAnsibleDeploy, self).setUp()
        mgr_utils.mock_the_extension_manager(driver='fake_ansible')
        self.driver = ansible_deploy.AnsibleDeploy()
        node = {
            'driver': 'fake_ansible',
            'instance_info': INSTANCE_INFO,
            'driver_info': DRIVER_INFO,
            'driver_internal_info': DRIVER_INTERNAL_INFO,
        }
        self.node = object_utils.create_test_node(self.context, **node)

    def test_get_properties(self):
        self.assertEqual(
            set(list(ansible_deploy.COMMON_PROPERTIES) +
                ['deploy_forces_oob_reboot']),
            set(self.driver.get_properties()))

    @mock.patch.object(deploy_utils, 'check_for_missing_params',
                       autospec=True)
    @mock.patch.object(pxe.PXEBoot, 'validate', autospec=True)
    def test_validate(self, pxe_boot_validate_mock, check_params_mock):
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=False) as task:
            self.driver.validate(task)
            pxe_boot_validate_mock.assert_called_once_with(
                task.driver.boot, task)
            check_params_mock.assert_called_once_with(
                {'instance_info.image_source': INSTANCE_INFO['image_source']},
                mock.ANY)

    @mock.patch.object(deploy_utils, 'get_boot_option',
                       return_value='netboot', autospec=True)
    @mock.patch.object(pxe.PXEBoot, 'validate', autospec=True)
    def test_validate_not_iwdi_netboot(self, pxe_boot_validate_mock,
                                       get_boot_mock):
        driver_internal_info = dict(DRIVER_INTERNAL_INFO)
        driver_internal_info['is_whole_disk_image'] = False
        self.node.driver_internal_info = driver_internal_info
        self.node.save()

        with task_manager.acquire(
                self.context, self.node['uuid'], shared=False) as task:
            self.assertRaises(exception.InvalidParameterValue,
                              self.driver.validate, task)
            pxe_boot_validate_mock.assert_called_once_with(
                task.driver.boot, task)
            get_boot_mock.assert_called_once_with(task.node)

    @mock.patch.object(utils, 'node_power_action', autospec=True)
    def test_deploy_wait(self, power_mock):
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=False) as task:
            driver_return = self.driver.deploy(task)
            self.assertEqual(driver_return, states.DEPLOYWAIT)
            power_mock.assert_called_once_with(task, states.REBOOT)

    @mock.patch.object(ansible_deploy, '_get_node_ip_dhcp',
                       return_value='127.0.0.1', autospec=True)
    @mock.patch.object(utils, 'node_power_action', autospec=True)
    def test_deploy_no_callback(self, power_mock, get_ip_mock):
        self.config(group='ansible', use_ramdisk_callback=False)
        with mock.patch.multiple(self.driver,
                                 _ansible_deploy=mock.DEFAULT,
                                 reboot_to_instance=mock.DEFAULT) as moks:
            with task_manager.acquire(
                    self.context, self.node['uuid'], shared=False) as task:
                driver_return = self.driver.deploy(task)
                self.assertEqual(driver_return, states.DEPLOYDONE)
                power_mock.assert_called_once_with(task, states.REBOOT)
                get_ip_mock.assert_called_once_with(task)
                moks['_ansible_deploy'].assert_called_once_with(task,
                                                                '127.0.0.1')
                moks['reboot_to_instance'].assert_called_once_with(task)

    @mock.patch.object(deploy_utils, 'set_failed_state', autospec=True)
    @mock.patch.object(ansible_deploy, '_get_node_ip_dhcp',
                       return_value='127.0.0.1', autospec=True)
    @mock.patch.object(utils, 'node_power_action', autospec=True)
    def test_deploy_no_callback_fail(self, power_mock, get_ip_mock, fail_mock):
        self.config(group='ansible', use_ramdisk_callback=False)
        with mock.patch.object(self.driver, '_ansible_deploy',
                               side_effect=ansible_deploy.PlaybookNotFound(
                                   'deploy')):
            with task_manager.acquire(
                    self.context, self.node.uuid, shared=False) as task:
                self.driver.deploy(task)
                self.driver._ansible_deploy.assert_called_once_with(
                    task, '127.0.0.1')
                fail_mock.assert_called_once_with(task, mock.ANY,
                                                  collect_logs=False)

    @mock.patch.object(utils, 'node_power_action', autospec=True)
    def test_tear_down(self, power_mock):
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=False) as task:
            driver_return = self.driver.tear_down(task)
            power_mock.assert_called_once_with(task, states.POWER_OFF)
            self.assertEqual(driver_return, states.DELETED)

    @mock.patch('ironic.drivers.modules.deploy_utils.build_agent_options',
                return_value={'op1': 'test1'}, autospec=True)
    @mock.patch('ironic.drivers.modules.deploy_utils.'
                'build_instance_info_for_deploy',
                return_value={'test': 'test'}, autospec=True)
    @mock.patch.object(pxe.PXEBoot, 'prepare_ramdisk')
    def test_prepare(self, pxe_prepare_ramdisk_mock,
                     build_instance_info_mock, build_options_mock):
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=False) as task:
            task.node.provision_state = states.DEPLOYING

            self.driver.prepare(task)

            build_instance_info_mock.assert_called_once_with(task)
            build_options_mock.assert_called_once_with(task.node)
            pxe_prepare_ramdisk_mock.assert_called_once_with(
                task, {'op1': 'test1'})

        self.node.refresh()
        self.assertEqual('test', self.node.instance_info['test'])

    @mock.patch.object(ansible_deploy, '_get_configdrive_path',
                       return_value='/path/test', autospec=True)
    @mock.patch.object(irlib_utils, 'unlink_without_raise', autospec=True)
    @mock.patch.object(pxe.PXEBoot, 'clean_up_ramdisk')
    def test_clean_up(self, pxe_clean_up_mock, unlink_mock,
                      get_cfdrive_path_mock):
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=False) as task:
            self.driver.clean_up(task)
            pxe_clean_up_mock.assert_called_once_with(task)
            get_cfdrive_path_mock.assert_called_once_with(self.node['uuid'])
            unlink_mock.assert_called_once_with('/path/test')

    @mock.patch.object(ansible_deploy, '_get_clean_steps', autospec=True)
    def test_get_clean_steps(self, get_clean_steps_mock):
        mock_steps = [{'priority': 10, 'interface': 'deploy',
                       'step': 'erase_devices'},
                      {'priority': 99, 'interface': 'deploy',
                       'step': 'erase_devices_metadata'},
                      ]
        get_clean_steps_mock.return_value = mock_steps
        with task_manager.acquire(self.context, self.node.uuid) as task:
            steps = self.driver.get_clean_steps(task)
            get_clean_steps_mock.assert_called_once_with(
                task.node, interface='deploy',
                override_priorities={
                    'erase_devices': None,
                    'erase_devices_metadata': None})
        self.assertEqual(mock_steps, steps)

    @mock.patch.object(ansible_deploy, '_get_clean_steps', autospec=True)
    def test_get_clean_steps_priority(self, mock_get_clean_steps):
        self.config(erase_devices_priority=9, group='deploy')
        self.config(erase_devices_metadata_priority=98, group='deploy')
        mock_steps = [{'priority': 9, 'interface': 'deploy',
                       'step': 'erase_devices'},
                      {'priority': 98, 'interface': 'deploy',
                       'step': 'erase_devices_metadata'},
                      ]
        mock_get_clean_steps.return_value = mock_steps

        with task_manager.acquire(self.context, self.node.uuid) as task:
            steps = self.driver.get_clean_steps(task)
            mock_get_clean_steps.assert_called_once_with(
                task.node, interface='deploy',
                override_priorities={'erase_devices': 9,
                                     'erase_devices_metadata': 98})
        self.assertEqual(mock_steps, steps)

    @mock.patch.object(ansible_deploy, '_run_playbook', autospec=True)
    @mock.patch.object(ansible_deploy, '_prepare_extra_vars', autospec=True)
    @mock.patch.object(ansible_deploy, '_parse_ansible_driver_info',
                       return_value=('test_pl', 'test_u', 'test_k'),
                       autospec=True)
    def test_execute_clean_step(self, parse_driver_info_mock,
                                prepare_extra_mock, run_playbook_mock):

        step = {'priority': 10, 'interface': 'deploy',
                'step': 'erase_devices', 'args': {'tags': ['clean']}}
        ironic_nodes = {
            'ironic_nodes': [(self.node['uuid'],
                              DRIVER_INTERNAL_INFO['ansible_cleaning_ip'],
                              'test_u', {})]}
        prepare_extra_mock.return_value = ironic_nodes
        di_info = self.node.driver_internal_info
        di_info['agent_url'] = 'http://127.0.0.1'
        self.node.driver_internal_info = di_info
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.driver.execute_clean_step(task, step)

            parse_driver_info_mock.assert_called_once_with(
                task.node, action='clean')
            prepare_extra_mock.assert_called_once_with(
                ironic_nodes['ironic_nodes'])
            run_playbook_mock.assert_called_once_with(
                'test_pl', ironic_nodes, 'test_k', tags=['clean'])

    @mock.patch.object(ansible_deploy, '_parse_ansible_driver_info',
                       return_value=('test_pl', 'test_u', 'test_k'),
                       autospec=True)
    @mock.patch.object(utils, 'cleaning_error_handler', autospec=True)
    @mock.patch.object(ansible_deploy, '_run_playbook', autospec=True)
    @mock.patch.object(ansible_deploy, 'LOG', autospec=True)
    def test_execute_clean_step_no_success_log(
            self, log_mock, run_mock, utils_mock, parse_driver_info_mock):

        run_mock.side_effect = exception.InstanceDeployFailure('Boom')
        step = {'priority': 10, 'interface': 'deploy',
                'step': 'erase_devices', 'args': {'tags': ['clean']}}
        di_info = self.node.driver_internal_info
        di_info['agent_url'] = 'http://127.0.0.1'
        self.node.driver_internal_info = di_info
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.driver.execute_clean_step(task, step)
            log_mock.error.assert_called_once_with(
                mock.ANY, {'node': task.node['uuid'],
                           'step': 'erase_devices'})
            utils_mock.assert_called_once_with(task, 'Boom')
            self.assertFalse(log_mock.info.called)

    @mock.patch.object(ansible_deploy, '_run_playbook', autospec=True)
    @mock.patch.object(utils, 'set_node_cleaning_steps', autospec=True)
    @mock.patch.object(utils, 'node_power_action', autospec=True)
    @mock.patch('ironic.drivers.modules.deploy_utils.build_agent_options',
                return_value={'op1': 'test1'}, autospec=True)
    @mock.patch.object(pxe.PXEBoot, 'prepare_ramdisk')
    def test_prepare_cleaning_callback(
            self, prepare_ramdisk_mock, buid_options_mock, power_action_mock,
            set_node_cleaning_steps, run_playbook_mock):
        step = {'priority': 10, 'interface': 'deploy',
                'step': 'erase_devices', 'tags': ['clean']}
        driver_internal_info = dict(DRIVER_INTERNAL_INFO)
        driver_internal_info['clean_steps'] = [step]
        self.node.driver_internal_info = driver_internal_info
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.network.add_cleaning_network = mock.Mock()

            state = self.driver.prepare_cleaning(task)

            set_node_cleaning_steps.assert_called_once_with(task)
            task.driver.network.add_cleaning_network.assert_called_once_with(
                task)
            buid_options_mock.assert_called_once_with(task.node)
            prepare_ramdisk_mock.assert_called_once_with(
                task, {'op1': 'test1'})
            power_action_mock.assert_called_once_with(task, states.REBOOT)
            self.assertFalse(run_playbook_mock.called)
            self.assertEqual(states.CLEANWAIT, state)

    @mock.patch.object(utils, 'set_node_cleaning_steps', autospec=True)
    def test_prepare_cleaning_callback_no_steps(self,
                                                set_node_cleaning_steps):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.network.add_cleaning_network = mock.Mock()

            self.driver.prepare_cleaning(task)

            set_node_cleaning_steps.assert_called_once_with(task)
            self.assertFalse(task.driver.network.add_cleaning_network.called)

    @mock.patch.object(ansible_deploy, '_prepare_extra_vars', autospec=True)
    @mock.patch.object(ansible_deploy, '_parse_ansible_driver_info',
                       return_value=('test_pl', 'test_u', 'test_k'),
                       autospec=True)
    @mock.patch.object(ansible_deploy, '_get_node_ip_dhcp',
                       return_value='127.0.0.1', autospec=True)
    @mock.patch.object(ansible_deploy, '_run_playbook', autospec=True)
    @mock.patch.object(utils, 'node_power_action', autospec=True)
    @mock.patch('ironic.drivers.modules.deploy_utils.build_agent_options',
                return_value={'op1': 'test1'}, autospec=True)
    @mock.patch.object(pxe.PXEBoot, 'prepare_ramdisk')
    def test_prepare_cleaning(self, prepare_ramdisk_mock, buid_options_mock,
                              power_action_mock, run_playbook_mock,
                              get_ip_mock, parse_driver_info_mock,
                              prepare_extra_mock):
        self.config(group='ansible', use_ramdisk_callback=False)
        ironic_nodes = {
            'ironic_nodes': [(self.node['uuid'],
                              '127.0.0.1',
                              'test_u', {})]}
        prepare_extra_mock.return_value = ironic_nodes

        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.network.add_cleaning_network = mock.Mock()

            state = self.driver.prepare_cleaning(task)

            task.driver.network.add_cleaning_network.assert_called_once_with(
                task)
            buid_options_mock.assert_called_once_with(task.node)
            prepare_ramdisk_mock.assert_called_once_with(
                task, {'op1': 'test1'})
            power_action_mock.assert_called_once_with(task, states.REBOOT)
            get_ip_mock.assert_called_once_with(task)
            parse_driver_info_mock.assert_called_once_with(
                task.node, action='clean')
            prepare_extra_mock.assert_called_once_with(
                ironic_nodes['ironic_nodes'])
            run_playbook_mock.assert_called_once_with(
                'test_pl', ironic_nodes, 'test_k', tags=['wait'])
            self.assertIsNone(state)

    @mock.patch.object(utils, 'node_power_action', autospec=True)
    @mock.patch.object(pxe.PXEBoot, 'clean_up_ramdisk')
    def test_tear_down_cleaning(self, clean_ramdisk_mock, power_action_mock):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.driver.network.remove_cleaning_network = mock.Mock()

            self.driver.tear_down_cleaning(task)

            power_action_mock.assert_called_once_with(task, states.POWER_OFF)
            clean_ramdisk_mock.assert_called_once_with(task)
            (task.driver.network.remove_cleaning_network
                .assert_called_once_with(task))

    @mock.patch.object(ansible_deploy, '_run_playbook', autospec=True)
    @mock.patch.object(ansible_deploy, '_prepare_extra_vars', autospec=True)
    @mock.patch.object(ansible_deploy, '_parse_ansible_driver_info',
                       return_value=('test_pl', 'test_u', 'test_k'),
                       autospec=True)
    @mock.patch.object(ansible_deploy, '_parse_partitioning_info',
                       autospec=True)
    @mock.patch.object(ansible_deploy, '_prepare_variables', autospec=True)
    def test__ansible_deploy(self, prepare_vars_mock, parse_part_info_mock,
                             parse_dr_info_mock, prepare_extra_mock,
                             run_playbook_mock):
        ironic_nodes = {
            'ironic_nodes': [(self.node['uuid'],
                              DRIVER_INTERNAL_INFO['ansible_cleaning_ip'],
                              'test_u')]}
        prepare_extra_mock.return_value = ironic_nodes
        _vars = {
            'url': 'image_url',
            'checksum': 'aa'}
        prepare_vars_mock.return_value = _vars

        driver_internal_info = dict(DRIVER_INTERNAL_INFO)
        driver_internal_info['is_whole_disk_image'] = False
        self.node.driver_internal_info = driver_internal_info
        self.node.extra = {'ham': 'spam'}
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.driver._ansible_deploy(task, '127.0.0.1')

            prepare_vars_mock.assert_called_once_with(task)
            parse_part_info_mock.assert_called_once_with(task.node)
            parse_dr_info_mock.assert_called_once_with(task.node)
            prepare_extra_mock.assert_called_once_with(
                [(self.node['uuid'], '127.0.0.1', 'test_u', {'ham': 'spam'})],
                variables=_vars)
            run_playbook_mock.assert_called_once_with(
                'test_pl', {'ironic_nodes': [
                    (self.node['uuid'],
                     DRIVER_INTERNAL_INFO['ansible_cleaning_ip'],
                     'test_u')]}, 'test_k',
                notags=['wait'])

    @mock.patch.object(ansible_deploy, '_run_playbook', autospec=True)
    @mock.patch.object(ansible_deploy, '_prepare_extra_vars', autospec=True)
    @mock.patch.object(ansible_deploy, '_parse_ansible_driver_info',
                       return_value=('test_pl', 'test_u', 'test_k'),
                       autospec=True)
    @mock.patch.object(ansible_deploy, '_parse_partitioning_info',
                       autospec=True)
    @mock.patch.object(ansible_deploy, '_prepare_variables', autospec=True)
    def test__ansible_deploy_iwdi(self, prepare_vars_mock,
                                  parse_part_info_mock, parse_dr_info_mock,
                                  prepare_extra_mock, run_playbook_mock):
        ironic_nodes = {
            'ironic_nodes': [(self.node['uuid'],
                              DRIVER_INTERNAL_INFO['ansible_cleaning_ip'],
                              'test_u')]}
        prepare_extra_mock.return_value = ironic_nodes
        _vars = {
            'url': 'image_url',
            'checksum': 'aa'}
        prepare_vars_mock.return_value = _vars
        driver_internal_info = self.node.driver_internal_info
        driver_internal_info['is_whole_disk_image'] = True
        self.node.driver_internal_info = driver_internal_info
        self.node.extra = {'ham': 'spam'}
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.driver._ansible_deploy(task, '127.0.0.1')

            prepare_vars_mock.assert_called_once_with(task)
            self.assertFalse(parse_part_info_mock.called)
            parse_dr_info_mock.assert_called_once_with(task.node)
            prepare_extra_mock.assert_called_once_with(
                [(self.node['uuid'], '127.0.0.1', 'test_u', {'ham': 'spam'})],
                variables=_vars)
            run_playbook_mock.assert_called_once_with(
                'test_pl', {'ironic_nodes': [
                    (self.node['uuid'],
                     DRIVER_INTERNAL_INFO['ansible_cleaning_ip'],
                     'test_u')]}, 'test_k',
                notags=['wait'])

    @mock.patch.object(fake.FakePower, 'get_power_state',
                       return_value=states.POWER_OFF)
    @mock.patch.object(utils, 'node_power_action', autospec=True)
    def test_reboot_and_finish_deploy_force_reboot(self, power_action_mock,
                                                   get_pow_state_mock):
        d_info = self.node.driver_info
        d_info['deploy_forces_oob_reboot'] = True
        self.node.driver_info = d_info
        self.node.save()
        self.config(group='ansible',
                    post_deploy_get_power_state_retry_interval=0)
        self.node.provision_state = states.DEPLOYING
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            with mock.patch.object(task.driver, 'network') as net_mock:
                self.driver.reboot_and_finish_deploy(task)
                net_mock.remove_provisioning_network.assert_called_once_with(
                    task)
                net_mock.configure_tenant_networks.assert_called_once_with(
                    task)
            expected_power_calls = [((task, states.POWER_OFF),),
                                    ((task, states.POWER_ON),)]
            self.assertEqual(expected_power_calls,
                             power_action_mock.call_args_list)
        get_pow_state_mock.assert_not_called()

    @mock.patch.object(ansible_deploy, '_run_playbook', autospec=True)
    @mock.patch.object(utils, 'node_power_action', autospec=True)
    @mock.patch.object(fake.FakePower, 'get_power_state',
                       return_value=states.POWER_ON)
    def test_reboot_and_finish_deploy_soft_poweroff_retry(self,
                                                          get_pow_state_mock,
                                                          power_action_mock,
                                                          ansible_mock):
        self.config(group='ansible',
                    post_deploy_get_power_state_retry_interval=0)
        self.config(group='ansible',
                    post_deploy_get_power_state_retries=1)
        self.node.provision_state = states.DEPLOYING
        di_info = self.node.driver_internal_info
        di_info['agent_url'] = 'http://127.0.0.1'
        self.node.driver_internal_info = di_info
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            with mock.patch.object(task.driver, 'network') as net_mock:
                self.driver.reboot_and_finish_deploy(task)
                net_mock.remove_provisioning_network.assert_called_once_with(
                    task)
                net_mock.configure_tenant_networks.assert_called_once_with(
                    task)
            power_action_mock.assert_has_calls(
                [mock.call(task, states.POWER_OFF),
                    mock.call(task, states.POWER_ON)])
            get_pow_state_mock.assert_called_with(task)
            self.assertEqual(2, len(get_pow_state_mock.mock_calls))
            expected_power_calls = [((task, states.POWER_OFF),),
                                    ((task, states.POWER_ON),)]
            self.assertEqual(expected_power_calls,
                             power_action_mock.call_args_list)
            ansible_mock.assert_called_once_with('shutdown.yaml',
                                                 mock.ANY, mock.ANY)

    @mock.patch.object(ansible_deploy, '_get_node_ip_heartbeat', autospec=True,
                       return_value='1.2.3.4')
    def test_continue_deploy(self, getip_mock):
        self.node.provision_state = states.DEPLOYWAIT
        self.node.target_provision_state = states.ACTIVE
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid) as task:
            with mock.patch.multiple(self.driver, autospec=True,
                                     _ansible_deploy=mock.DEFAULT,
                                     reboot_to_instance=mock.DEFAULT):
                self.driver.continue_deploy(task)
                getip_mock.assert_called_once_with(task)
                self.driver._ansible_deploy.assert_called_once_with(
                    task, '1.2.3.4')
                self.driver.reboot_to_instance.assert_called_once_with(task)
            self.assertEqual(states.ACTIVE, task.node.target_provision_state)
            self.assertEqual(states.DEPLOYING, task.node.provision_state)

    @mock.patch.object(utils, 'node_set_boot_device', autospec=True)
    def test_reboot_to_instance(self, bootdev_mock):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            with mock.patch.object(self.driver, 'reboot_and_finish_deploy',
                                   autospec=True):
                task.driver.boot = mock.Mock()
                self.driver.reboot_to_instance(task)
                bootdev_mock.assert_called_once_with(task, 'disk',
                                                     persistent=True)
                self.driver.reboot_and_finish_deploy.assert_called_once_with(
                    task)
                task.driver.boot.clean_up_ramdisk.assert_called_once_with(
                    task)
