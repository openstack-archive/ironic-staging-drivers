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

from oslo_config import cfg
from oslo_log import log as logging
import pbr.version

CONF = cfg.CONF
DOMAIN = 'ironic'

version_info = pbr.version.VersionInfo(DOMAIN)
LOG = logging.getLogger('ironic-ansible-deploy', project=DOMAIN,
                        version=version_info.release_string())
logging.register_options(CONF)
CONF.set_override('use_journal', True)

logging.setup(CONF, DOMAIN)


class CallbackModule(object):

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'ironic_journald'
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self, display=None):
        self.node = None

    def runner_msg_dict(self, result):
        self.node = result._host.get_name()
        name = result._task.get_name()
        res = str(result._result)
        return dict(node=self.node, name=name, res=res)

    def v2_playbook_on_task_start(self, task, is_conditional):
        # NOTE(pas-ha) I do not know (yet) how to obtain a ref to host
        # until first task is processed
        node = self.node or "Node"
        name = task.get_name()
        if name == 'setup':
            LOG.debug("Processing task %(name)s.", dict(name=name))
        else:
            LOG.debug("Processing task %(name)s on node %(node)s.",
                      dict(name=name, node=node))

    def v2_runner_on_failed(self, result, *args, **kwargs):
        LOG.error("Ansible task %(name)s failed on node %(node)s: %(res)s",
                  self.runner_msg_dict(result))

    def v2_runner_on_ok(self, result):
        msg_dict = self.runner_msg_dict(result)
        if msg_dict['name'] == 'setup':
            LOG.info("Ansible task 'setup' complete on node %(node)s",
                     msg_dict)
        else:
            LOG.info(
                "Ansible task %(name)s complete on node %(node)s: %(res)s",
                msg_dict)

    def v2_runner_on_unreachable(self, result):
        LOG.error("Node %(node)s was unreachable for Ansible task %(name)s: "
                  "%(res)s", self.runner_msg_dict(result))

    def v2_runner_on_async_poll(self, result):
        LOG.debug("Polled ansible task %(name)s for complete "
                  "on node %(node)s: %(res)s", self.runner_msg_dict(result))

    def v2_runner_on_async_ok(self, result):
        LOG.info("Async Ansible task %(name)s complete on node %(node)s: "
                 "%(res)s", self.runner_msg_dict(result))

    def v2_runner_on_async_failed(self, result):
        LOG.error("Async Ansible task %(name)s failed on node %(node)s: "
                  "%(res)s", self.runner_msg_dict(result))

    def v2_runner_on_skipped(self, result):
        LOG.debug("Ansible task %(name)s skipped on node %(node)s: %(res)s",
                  self.runner_msg_dict(result))
