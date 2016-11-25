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

import json
import os

from ironic.common import dhcp_factory
from ironic.common import exception
from ironic.common import image_service
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
from oslo_config import cfg

from ironic_staging_drivers.ansible import deploy as ansible_deploy

CONF = cfg.CONF


INSTANCE_INFO = {
    'image_source': 'fake-image',
    'image_url': 'http://image',
    'image_checksum': 'checksum',
    'image_disk_format': 'qcow2',
    'root_gb': 5,
}

DRIVER_INFO = {
    'deploy_kernel': 'glance://deploy_kernel_uuid',
    'deploy_ramdisk': 'glance://deploy_ramdisk_uuid',
    'ansible_deploy_username': 'test',
    'ansible_deploy_key_file': '/path/key',
}
DRIVER_INTERNAL_INFO = {
    'ansible_cleaning_ip': 'http://127.0.0.1/',
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

    @mock.patch.object(image_service, 'GlanceImageService', autospec=True)
    def test_build_instance_info_for_deploy_glance_image(self, glance_mock):
        i_info = self.node.instance_info
        i_info['image_source'] = '733d1c44-a2ea-414b-aca7-69decf20d810'
        self.node.instance_info = i_info
        self.node.save()

        image_info = {'checksum': 'aa', 'disk_format': 'qcow2'}
        glance_mock.return_value.show = mock.Mock(spec_set=[],
                                                  return_value=image_info)

        with task_manager.acquire(
                self.context, self.node.uuid) as task:

            ansible_deploy.build_instance_info_for_deploy(task)

            glance_mock.assert_called_once_with(version=2,
                                                context=task.context)
            glance_mock.return_value.show.assert_called_once_with(
                self.node.instance_info['image_source'])
            glance_mock.return_value.swift_temp_url.assert_called_once_with(
                image_info)

    @mock.patch.object(image_service.HttpImageService, 'validate_href',
                       autospec=True)
    def test_build_instance_info_for_deploy_nonglance_image(
            self, validate_href_mock):
        i_info = self.node.instance_info
        driver_internal_info = self.node.driver_internal_info
        i_info['image_source'] = 'http://image-ref'
        i_info['image_checksum'] = 'aa'
        i_info['root_gb'] = 10
        driver_internal_info['is_whole_disk_image'] = True
        self.node.instance_info = i_info
        self.node.driver_internal_info = driver_internal_info
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            info = ansible_deploy.build_instance_info_for_deploy(task)

            self.assertEqual(self.node.instance_info['image_source'],
                             info['image_url'])
            validate_href_mock.assert_called_once_with(
                mock.ANY, 'http://image-ref')

    @mock.patch.object(image_service.HttpImageService, 'validate_href',
                       autospec=True)
    def test_build_instance_info_for_deploy_nonsupported_image(
            self, validate_href_mock):
        validate_href_mock.side_effect = iter(
            [exception.ImageRefValidationFailed(
                image_href='file://img.qcow2', reason='fail')])
        i_info = self.node.instance_info
        i_info['image_source'] = 'file://img.qcow2'
        i_info['image_checksum'] = 'aa'
        self.node.instance_info = i_info
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(
                exception.ImageRefValidationFailed,
                ansible_deploy.build_instance_info_for_deploy, task)

    def test__get_node_ip(self):
        dhcp_provider_mock = mock.Mock()
        dhcp_factory.DHCPFactory._dhcp_provider = dhcp_provider_mock
        dhcp_provider_mock.get_ip_addresses.return_value = ['ip']
        with task_manager.acquire(self.context, self.node.uuid) as task:
            ansible_deploy._get_node_ip(task)
            dhcp_provider_mock.get_ip_addresses.assert_called_once_with(
                task)

    def test__get_node_ip_no_ip(self):
        dhcp_provider_mock = mock.Mock()
        dhcp_factory.DHCPFactory._dhcp_provider = dhcp_provider_mock
        dhcp_provider_mock.get_ip_addresses.return_value = []
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(exception.FailedToGetIPAddressOnPort,
                              ansible_deploy._get_node_ip, task)

    def test__get_node_ip_multiple_ip(self):
        dhcp_provider_mock = mock.Mock()
        dhcp_factory.DHCPFactory._dhcp_provider = dhcp_provider_mock
        dhcp_provider_mock.get_ip_addresses.return_value = ['ip1', 'ip2']
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(exception.InstanceDeployFailure,
                              ansible_deploy._get_node_ip, task)

    @mock.patch.object(utils, 'node_power_action', autospec=True)
    @mock.patch.object(fake.FakePower, 'get_power_state',
                       return_value=states.POWER_OFF)
    def test__reboot_and_finish_deploy(self, get_pow_state_mock,
                                       power_action_mock):
        self.config(group='ansible',
                    post_deploy_get_power_state_retry_interval=0)

        with task_manager.acquire(self.context, self.node.uuid) as task:
            ansible_deploy._reboot_and_finish_deploy(task)
            get_pow_state_mock.assert_called_once_with(task)
            power_action_mock.assert_called_once_with(task, states.POWER_ON)

    @mock.patch.object(utils, 'node_power_action', autospec=True)
    @mock.patch.object(fake.FakePower, 'get_power_state',
                       return_value=states.POWER_ON)
    def test__reboot_and_finish_deploy_retry(self, get_pow_state_mock,
                                             power_action_mock):
        self.config(group='ansible',
                    post_deploy_get_power_state_retry_interval=0)

        with task_manager.acquire(self.context, self.node.uuid) as task:
            ansible_deploy._reboot_and_finish_deploy(task)
            get_pow_state_mock.assert_called_with(task)
            self.assertEqual(
                CONF.ansible.post_deploy_get_power_state_retries + 1,
                len(get_pow_state_mock.mock_calls))
            expected_power_calls = [((task, states.POWER_OFF),),
                                    ((task, states.POWER_ON),)]
            self.assertEqual(expected_power_calls,
                             power_action_mock.call_args_list)

    @mock.patch.object(com_utils, 'execute', return_value=('out', 'err'),
                       autospec=True)
    @mock.patch.object(os.path, 'join', return_value='/path/to/playbook',
                       autospec=True)
    def test__run_playbook(self, path_join_mock, execute_mock):
        extra_vars = {"ironic_nodes": [{"name": self.node["uuid"],
                      "ip": "127.0.0.1", "user": "test"}]}

        ansible_deploy._run_playbook('deploy', extra_vars, '/path/to/key')

        execute_mock.assert_called_once_with(
            'env', 'ANSIBLE_CONFIG=%s' % CONF.ansible.config_file_path,
            'ansible-playbook', '/path/to/playbook', '-i',
            ansible_deploy.INVENTORY_FILE, '-e', json.dumps(extra_vars),
            '--private-key=/path/to/key', '-vvvv')

    @mock.patch.object(com_utils, 'execute', return_value=('out', 'err'),
                       autospec=True)
    @mock.patch.object(os.path, 'join', return_value='/path/to/playbook',
                       autospec=True)
    def test__run_playbook_tags(self, path_join_mock, execute_mock):
        extra_vars = {"ironic_nodes": [{"name": self.node["uuid"],
                      "ip": "127.0.0.1", "user": "test"}]}

        ansible_deploy._run_playbook('deploy', extra_vars, '/path/to/key',
                                     tags=['wait'])

        execute_mock.assert_called_once_with(
            'env', 'ANSIBLE_CONFIG=%s' % CONF.ansible.config_file_path,
            'ansible-playbook', '/path/to/playbook', '-i',
            ansible_deploy.INVENTORY_FILE, '-e', json.dumps(extra_vars),
            '--tags=wait', '--private-key=/path/to/key', '-vvvv')

    @mock.patch.object(deploy_utils, 'check_for_missing_params',
                       autospec=True)
    def test__parse_partitioning_info(self, check_missing_param_mock):
        expected_info = {
            'ironic_partitions':
                [{'boot': 'yes', 'swap': 'no',
                  'size_mib': 1024 * INSTANCE_INFO['root_gb'],
                  'name': 'root'}]}

        i_info = ansible_deploy._parse_partitioning_info(self.node)

        check_missing_param_mock.assert_called_once_with(
            expected_info, mock.ANY)
        self.assertEqual(expected_info, i_info)

    @mock.patch.object(deploy_utils, 'check_for_missing_params',
                       autospec=True)
    def test__parse_partitioning_info_swap(self, check_missing_param_mock):
        in_info = dict(INSTANCE_INFO)
        in_info['swap_mb'] = 128
        self.node.instance_info = in_info
        self.node.save()

        expected_info = {
            'ironic_partitions':
                [{'boot': 'yes', 'swap': 'no',
                  'size_mib': 1024 * INSTANCE_INFO['root_gb'],
                  'name': 'root'},
                 {'boot': 'no', 'swap': 'yes',
                  'size_mib': 128, 'name': 'swap'}]}

        i_info = ansible_deploy._parse_partitioning_info(self.node)

        check_missing_param_mock.assert_called_once_with(
            expected_info, mock.ANY)
        self.assertEqual(expected_info, i_info)

    @mock.patch.object(deploy_utils, 'check_for_missing_params',
                       autospec=True)
    def test__parse_partitioning_info_invalid_param(self,
                                                    check_missing_param_mock):
        in_info = dict(INSTANCE_INFO)
        in_info['root_gb'] = 'five'
        self.node.instance_info = in_info
        self.node.save()

        self.assertRaises(exception.InvalidParameterValue,
                          ansible_deploy._parse_partitioning_info,
                          self.node)

    @mock.patch.object(pxe.PXEBoot, 'clean_up_ramdisk')
    @mock.patch.object(ansible_deploy, '_reboot_and_finish_deploy',
                       autospec=True)
    @mock.patch.object(utils, 'node_set_boot_device', autospec=True)
    @mock.patch.object(ansible_deploy, '_run_playbook', autospec=True)
    @mock.patch.object(ansible_deploy, '_prepare_extra_vars', autospec=True)
    @mock.patch.object(ansible_deploy, '_parse_ansible_driver_info',
                       return_value=('test_pl', 'test_u', 'test_k'),
                       autospec=True)
    @mock.patch.object(ansible_deploy, '_parse_partitioning_info',
                       autospec=True)
    @mock.patch.object(ansible_deploy, '_prepare_variables', autospec=True)
    def test__deploy(self, prepare_vars_mock, parse_part_info_mock,
                     parse_dr_info_mock, prepare_extra_mock,
                     run_playbook_mock, set_boot_device_mock,
                     finish_deploy_mock, clean_ramdisk_mock):
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
            ansible_deploy._deploy(task, '127.0.0.1')

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
            set_boot_device_mock.assert_called_once_with(
                task, 'disk', persistent=True)
            finish_deploy_mock.assert_called_once_with(task)
            clean_ramdisk_mock.assert_called_once_with(task)

    @mock.patch.object(pxe.PXEBoot, 'clean_up_ramdisk')
    @mock.patch.object(ansible_deploy, '_reboot_and_finish_deploy',
                       autospec=True)
    @mock.patch.object(utils, 'node_set_boot_device', autospec=True)
    @mock.patch.object(ansible_deploy, '_run_playbook', autospec=True)
    @mock.patch.object(ansible_deploy, '_prepare_extra_vars', autospec=True)
    @mock.patch.object(ansible_deploy, '_parse_ansible_driver_info',
                       return_value=('test_pl', 'test_u', 'test_k'),
                       autospec=True)
    @mock.patch.object(ansible_deploy, '_parse_partitioning_info',
                       autospec=True)
    @mock.patch.object(ansible_deploy, '_prepare_variables', autospec=True)
    def test__deploy_iwdi(self, prepare_vars_mock, parse_part_info_mock,
                          parse_dr_info_mock, prepare_extra_mock,
                          run_playbook_mock, set_boot_device_mock,
                          finish_deploy_mock, clean_ramdisk_mock):
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
            ansible_deploy._deploy(task, '127.0.0.1')

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
                notags=['wait', 'parted'])
            set_boot_device_mock.assert_called_once_with(
                task, 'disk', persistent=True)
            finish_deploy_mock.assert_called_once_with(task)
            clean_ramdisk_mock.assert_called_once_with(task)


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
        self.assertEqual(ansible_deploy.COMMON_PROPERTIES,
                         self.driver.get_properties())

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

    @mock.patch.object(ansible_deploy, '_deploy', autospec=True)
    @mock.patch.object(ansible_deploy, '_get_node_ip',
                       return_value='127.0.0.1', autospec=True)
    @mock.patch.object(utils, 'node_power_action', autospec=True)
    def test_deploy_done(self, power_mock, get_ip_mock, deploy_mock):
        self.config(group='ansible', use_ramdisk_callback=False)
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=False) as task:
            driver_return = self.driver.deploy(task)
            self.assertEqual(driver_return, states.DEPLOYDONE)
            power_mock.assert_called_once_with(task, states.REBOOT)
            get_ip_mock.assert_called_once_with(task)
            deploy_mock.assert_called_once_with(task, '127.0.0.1')

    @mock.patch.object(utils, 'node_power_action', autospec=True)
    def test_tear_down(self, power_mock):
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=False) as task:
            driver_return = self.driver.tear_down(task)
            power_mock.assert_called_once_with(task, states.POWER_OFF)
            self.assertEqual(driver_return, states.DELETED)

    @mock.patch('ironic.drivers.modules.deploy_utils.build_agent_options',
                return_value={'op1': 'test1'}, autospec=True)
    @mock.patch.object(ansible_deploy, 'build_instance_info_for_deploy',
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
                task, interface='deploy',
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
                task, interface='deploy',
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

        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.driver.execute_clean_step(task, step)

            parse_driver_info_mock.assert_called_once_with(
                task.node, action='clean')
            prepare_extra_mock.assert_called_once_with(
                ironic_nodes['ironic_nodes'])
            run_playbook_mock.assert_called_once_with(
                'test_pl', ironic_nodes, 'test_k', tags=['clean'])

    @mock.patch.object(ansible_deploy, '_run_playbook', autospec=True)
    @mock.patch.object(ansible_deploy, '_parse_ansible_driver_info',
                       return_value=('test_pl', 'test_u', 'test_k'),
                       autospec=True)
    def test_execute_clean_step_no_ip(self, parse_driver_info_mock,
                                      run_playbook_mock):

        step = {'priority': 10, 'interface': 'deploy',
                'step': 'erase_devices', 'tags': ['clean']}
        driver_internal_info = dict(DRIVER_INTERNAL_INFO)
        del driver_internal_info['ansible_cleaning_ip']
        self.node.driver_internal_info = driver_internal_info
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(exception.NodeCleaningFailure,
                              self.driver.execute_clean_step, task, step)

            parse_driver_info_mock.assert_called_once_with(
                task.node, action='clean')
            self.assertFalse(run_playbook_mock.called)

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
    @mock.patch.object(ansible_deploy, '_get_node_ip',
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
            self.assertEqual(None, state)

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

    @mock.patch.object(ansible_deploy, 'LOG', autospec=True)
    def test_heartbeat_not_wait_state(self, log_mock):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.driver.heartbeat(task, 'http://127.0.0.1')
            log_mock.warning.assert_called_once_with(
                mock.ANY, {'node': task.node['uuid'],
                           'state': task.node['provision_state']})

    @mock.patch.object(ansible_deploy, 'LOG', autospec=True)
    @mock.patch.object(ansible_deploy, '_deploy', autospec=True)
    def test_heartbeat_deploy_wait(self, deploy_mock, log_mock):
        self.node['provision_state'] = states.DEPLOYWAIT
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.process_event = mock.Mock()

            self.driver.heartbeat(task, 'http://127.0.0.1')

            deploy_mock.assert_called_once_with(task, '127.0.0.1')
            log_mock.info.assert_called_once_with(mock.ANY, task.node['uuid'])
            self.assertEqual([mock.call('resume'), mock.call('done')],
                             task.process_event.mock_calls)

    @mock.patch.object(deploy_utils, 'set_failed_state', autospec=True)
    @mock.patch.object(ansible_deploy, 'LOG', autospec=True)
    @mock.patch.object(ansible_deploy, '_deploy',
                       side_effect=Exception('Boo'), autospec=True)
    def test_heartbeat_deploy_wait_fail(self, deploy_mock, log_mock,
                                        set_fail_state_mock):
        self.node['provision_state'] = states.DEPLOYWAIT
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.process_event = mock.Mock()

            self.driver.heartbeat(task, 'http://127.0.0.1')

            deploy_mock.assert_called_once_with(task, '127.0.0.1')
            log_mock.exception.assert_called_once_with(mock.ANY)
            self.assertEqual([mock.call('resume')],
                             task.process_event.mock_calls)
            set_fail_state_mock.assert_called_once_with(task, mock.ANY,
                                                        collect_logs=False)

    @mock.patch.object(ansible_deploy, '_notify_conductor_resume_clean',
                       autospec=True)
    def test_heartbeat_clean_wait(self, notify_resume_clean_mock):
        self.node['provision_state'] = states.CLEANWAIT
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.process_event = mock.Mock()

            self.driver.heartbeat(task, 'http://127.0.0.1')

            notify_resume_clean_mock.assert_called_once_with(task)

    @mock.patch.object(ansible_deploy, '_notify_conductor_resume_clean',
                       side_effect=Exception('Boo'), autospec=True)
    @mock.patch.object(utils, 'cleaning_error_handler', autospec=True)
    def test_heartbeat_clean_wait_fail(self, cleaning_error_mock,
                                       notify_resume_clean_mock):
        self.node['provision_state'] = states.CLEANWAIT
        self.node.save()

        with task_manager.acquire(self.context, self.node.uuid) as task:
            task.process_event = mock.Mock()

            self.driver.heartbeat(task, 'http://127.0.0.1')

            notify_resume_clean_mock.assert_called_once_with(task)
            cleaning_error_mock.assert_called_once_with(task, mock.ANY)

    @mock.patch.object(ansible_deploy, '_notify_conductor_resume_clean',
                       autospec=True)
    @mock.patch.object(ansible_deploy, '_deploy', autospec=True)
    @mock.patch.object(ansible_deploy, 'LOG', autospec=True)
    def test_heartbeat_maintenance(self, log_mock, deploy_mock,
                                   notify_clean_resume_mock):
        self.node['maintenance'] = True
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.driver.heartbeat(task, 'http://127.0.0.1')

        self.node['provision_state'] = states.CLEANWAIT
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.driver.heartbeat(task, 'http://127.0.0.1')

        self.node['provision_state'] = states.DEPLOYWAIT
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.driver.heartbeat(task, 'http://127.0.0.1')

        self.assertFalse(log_mock.warning.called)
        self.assertFalse(deploy_mock.called)
        self.assertFalse(notify_clean_resume_mock.called)
