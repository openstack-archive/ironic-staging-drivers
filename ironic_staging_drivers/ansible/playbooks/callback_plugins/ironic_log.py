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

import ConfigParser
import os

from oslo_config import cfg
from oslo_log import log as logging
import pbr.version

from ironic_staging_drivers.common import i18n

CONF = cfg.CONF
DOMAIN = 'ironic'

# parse callback plugin config and Ironic config, setup logging
basename = os.path.splitext(__file__)[0]
config = ConfigParser.ConfigParser()
ironic_config = None
ironic_log_file = None
try:
    config.readfp(open(basename + ".ini"))
    if config.has_option('ironic', 'config_file'):
        ironic_config = config.get('ironic', 'config_file')
    if config.has_option('ironic', 'log_file'):
        ironic_log_file = config.get('ironic', 'log_file')
except Exception:
    pass

version_info = pbr.version.VersionInfo(DOMAIN)

LOG = logging.getLogger(__name__, project=DOMAIN,
                        version=version_info.release_string())
logging.register_options(CONF)

conf_kwargs = dict(args=[], project=DOMAIN,
                   version=version_info.release_string())
if ironic_config:
    conf_kwargs['default_config_files'] = [ironic_config]
CONF(**conf_kwargs)

if ironic_log_file:
    CONF.set_override("log_file", ironic_log_file)

logging.setup(CONF, DOMAIN)


class CallbackModule(object):

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'ironic_log'
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
        LOG.error(i18n._LE(
            "Ansible task %(name)s failed on node %(node)s: %(res)s"),
            self.runner_msg_dict(result))

    def v2_runner_on_ok(self, result):
        msg_dict = self.runner_msg_dict(result)
        if msg_dict['name'] == 'setup':
            LOG.info(i18n._LI(
                "Ansible task 'setup' complete on node %(node)s"),
                msg_dict)
        else:
            LOG.info(i18n._LI(
                "Ansible task %(name)s complete on node %(node)s: %(res)s"),
                msg_dict)

    def v2_runner_on_unreachable(self, result):
        LOG.error(i18n._LE(
            "Node %(node)s was unreachable for Ansible task %(name)s: "
            "%(res)s"),
            self.runner_msg_dict(result))

    def v2_runner_on_async_poll(self, result):
        LOG.debug("Polled ansible task %(name)s for complete "
                  "on node %(node)s: %(res)s",
                  self.runner_msg_dict(result))

    def v2_runner_on_async_ok(self, result):
        LOG.info(i18n._LI(
            "Async Ansible task %(name)s complete on node %(node)s: %(res)s"),
            self.runner_msg_dict(result))

    def v2_runner_on_async_failed(self, result):
        LOG.error(i18n._LE(
            "Async Ansible task %(name)s failed on node %(node)s: %(res)s"),
            self.runner_msg_dict(result))

    def v2_runner_on_skipped(self, result):
        LOG.debug("Ansible task %(name)s skipped on node %(node)s: %(res)s",
                  self.runner_msg_dict(result))
