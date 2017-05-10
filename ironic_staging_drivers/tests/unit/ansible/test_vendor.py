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

import os

from ironic.conductor import task_manager
from ironic.tests.unit.conductor import mgr_utils
from ironic.tests.unit.db import base as db_base
from ironic.tests.unit.objects import utils as object_utils

DRIVER_INFO = {
    'ansible_deploy_playbook': 'fake_deploy.yaml',
    'ansible_clean_playbook': 'fake_clean.yml',
    'ansible_shutdown_playbook': 'fake_shutdown.yaml',
    'ansible_deploy_clean_steps_config': 'fake_clean_steps.yml'
}


class AnsibleVendorTestCase(db_base.DbTestCase):

    def setUp(self):
        super(AnsibleVendorTestCase, self).setUp()
        mgr_utils.mock_the_extension_manager(driver='fake_ansible')
        node = {
            'driver': 'fake_ansible',
            'driver_info': DRIVER_INFO,
        }
        self.node = object_utils.create_test_node(self.context, **node)

    def test_list_ansible_files(self):
        self.config(group='ansible',
                    playbooks_path=os.path.join(
                        os.path.dirname(__file__), 'fake_playbooks'))
        # check that:
        # - not-list YAMLs are skipped
        # - ansible playbooks w/o 'ironic' host are skipped
        # - plays for non-'ironic' hosts are not reported
        # - clean steps config is returned as-is
        expected = {"ansible_files": {
            'fake_deploy.yaml': {
                'type': 'ansible playbook',
                'description': 'fake deploy playbook'},
            'fake_clean.yml': {
                'type': 'ansible playbook',
                'description': 'fake clean playbook'},
            'fake_shutdown.yaml': {
                'type': 'ansible playbook',
                'description': 'fake shutdown playbook'},
            'fake_clean_steps.yml': {
                'type': 'clean steps config',
                'description': "[{'interface': 'spam', 'ham': 'eggs'}, "
                               "{'interface': 'foo', 'bar': 'baz'}]"},
        }}
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertEqual(expected,
                             task.driver.vendor.list_ansible_files(task))
