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

"""Test class for AMT Deploy methods."""

from ironic.common import boot_devices
from ironic.common import states
from ironic.conductor import task_manager
from ironic.drivers.modules import iscsi_deploy
from ironic.tests.unit.conductor import mgr_utils
from ironic.tests.unit.db import base as db_base
from ironic.tests.unit.objects import utils as obj_utils
import mock

from ironic_staging_drivers.amt import management as amt_mgmt
from ironic_staging_drivers.tests.unit.amt import utils as test_utils

INFO_DICT = test_utils.get_test_amt_info()


class AMTISCSIDeployTestCase(db_base.DbTestCase):

    def setUp(self):
        super(AMTISCSIDeployTestCase, self).setUp()
        mgr_utils.mock_the_extension_manager(driver="pxe_amt_iscsi")
        self.node = obj_utils.create_test_node(
            self.context, driver='pxe_amt_iscsi', driver_info=INFO_DICT)

    @mock.patch.object(amt_mgmt.AMTManagement, 'ensure_next_boot_device',
                       spec_set=True, autospec=True)
    @mock.patch.object(iscsi_deploy.ISCSIDeploy, 'continue_deploy',
                       spec_set=True, autospec=True)
    def test_continue_deploy_netboot(self, mock_continue, mock_ensure):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.node.provision_state = states.DEPLOYWAIT
            task.node.target_provision_state = states.ACTIVE
            task.node.instance_info['capabilities'] = {
                "boot_option": "netboot"
            }
            task.driver.deploy.continue_deploy(task)
            mock_ensure.assert_called_with(
                task.driver.management, task.node, boot_devices.PXE)
            mock_continue.assert_called_once_with(
                task.driver.deploy, task)

    @mock.patch.object(amt_mgmt.AMTManagement, 'ensure_next_boot_device',
                       spec_set=True, autospec=True)
    @mock.patch.object(iscsi_deploy.ISCSIDeploy, 'continue_deploy',
                       spec_set=True, autospec=True)
    def test_continue_deploy_localboot(self, mock_continue, mock_ensure):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.node.provision_state = states.DEPLOYWAIT
            task.node.target_provision_state = states.ACTIVE
            task.node.instance_info['capabilities'] = {"boot_option": "local"}
            task.driver.deploy.continue_deploy(task,)
            self.assertFalse(mock_ensure.called)
            mock_continue.assert_called_once_with(
                task.driver.deploy, task)
