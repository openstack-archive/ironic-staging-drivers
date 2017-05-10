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

    def __init__(self):
        super(AnsibleDeployPassthru, self).__init__()
        self.parsed = self._parse_yamls()

    def get_properties(self):
        return {}

    def validate(self, task, method, **kwargs):
        pass

    def _load_yamls(self):
        all_yamls = (glob.glob(os.path.join(CONF.ansible.playbooks_path,
                                            '*.yaml')) +
                     glob.glob(os.path.join(CONF.ansible.playbooks_path,
                                            '*.yml')))
        all_parsed = {}
        for name in all_yamls:
            with open(name) as f:
                all_parsed[os.path.basename(name)] = yaml.safe_load(f)
        return all_parsed

    def _parse_yamls(self):
        all_parsed = self._load_yamls()
        resp = []
        for name, value in all_parsed.items():
            if all('interface' in i for i in value):
                # we've got a clean steps config
                # TODO(pas-ha) add meaningfull description for clean steps
                # from parsed file
                resp.append({'name': name,
                             'type': "clean steps config",
                             'description': ''})
                continue
            if any('hosts' in i for i in value):
                # we've got an Ansible playbook
                # report only those that are executed against real ironic nodes
                play_names = [i.get('name', '') for i in value
                              if i.get('hosts') == 'ironic']
                if play_names:
                    desc = '; '.join(filter(bool, play_names))
                    resp.append({'name': name,
                                 'type': 'ansible playbook',
                                 'description': desc})
        return {"ansible_files": resp}

    @base.passthru(['POST', 'GET'], async=False, require_exclusive_lock=False,
                   description='List files available to set as driver props')
    def list_ansible_files(self, task, **kwargs):
        if kwargs['http_method'] == 'POST':
            self.parsed = self._parse_yamls()
        return self.parsed
