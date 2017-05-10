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
Ansible deploy driver vendor extension
"""

import glob
import os

from ironic.conf import CONF
from ironic.drivers import base
import yaml


class AnsibleDeployPassthru(base.VendorInterface):

    def get_properties(self):
        return {}

    def validate(self, task, method, **kwargs):
        # TODO(pas-ha) fail if _parse_yamls() is empty
        pass

    def _parse_yamls(self):
        ansible_files = {}
        all_yamls = (glob.glob(os.path.join(CONF.ansible.playbooks_path,
                                            '*.yaml')) +
                     glob.glob(os.path.join(CONF.ansible.playbooks_path,
                                            '*.yml')))
        for name in all_yamls:
            with open(name) as f:
                parsed = yaml.safe_load(f)
                if not isinstance(parsed, list):
                    # NOTE(pas-ha) both ansible playbooks and clean steps
                    # configs must be lists, skip those YAMLs that aren't
                    continue
                if all('interface' in i for i in parsed):
                    # we've got a clean steps config
                    # basically return it as is to report all available clean
                    # steps, their descriptions and associated playbook tags
                    ansible_files[os.path.basename(name)] = {
                        'type': "clean steps config",
                        'description': parsed}
                    continue
                if any('hosts' in i for i in parsed):
                    # we've got an Ansible playbook
                    # report only those that are executed against ironic nodes
                    play_names = [i.get('name', '') for i in parsed
                                  if i.get('hosts') == 'ironic']
                    if play_names:
                        desc = '; '.join(filter(bool, play_names))
                        ansible_files[os.path.basename(name)] = {
                            'type': 'ansible playbook',
                            'description': desc}
        return ansible_files

    @base.passthru(['POST'], async=False, require_exclusive_lock=False,
                   description='List files available to set as driver props')
    def list_ansible_files(self, task, **kwargs):
        return {"ansible_files": self._parse_yamls()}
