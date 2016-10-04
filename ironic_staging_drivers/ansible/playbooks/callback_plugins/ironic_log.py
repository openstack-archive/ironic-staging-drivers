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
import subprocess

from oslo_config import cfg
import oslo_i18n as i18n
from oslo_log import log as logging
import pbr.version

CONF = cfg.CONF
DOMAIN = 'ironic'

# setup translation facilities
_translators = i18n.TranslatorFactory(domain=DOMAIN)

# The primary translation function using the well-known name "_"
_ = _translators.primary

# Translators for log levels.
#
# The abbreviated names are meant to reflect the usual use of a short
# name like '_'. The "L" is for "log" and the other letter comes from
# the level.
_LI = _translators.log_info
_LW = _translators.log_warning
_LE = _translators.log_error
_LC = _translators.log_critical

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

# setup logging for DevStack
if not (ironic_log_file or
        (CONF.use_syslog or
         CONF.log_config_append or
         CONF.log_file)):
    # NOTE(pas-ha) suitable for DevStack only!
    # We have no logging files or extra configuration,
    # and explicit log file is not set in config of the callback plugin.
    # Plugin will post log entries directly to ironic-conductor's
    # stdout file descriptor
    try:
        pid = subprocess.check_output(
            ['pgrep', '-f', 'ironic-conductor']).strip()
        int(pid)
    except Exception:
        pass
    else:
        ironic_log_file = os.path.join('/proc', pid.strip(), 'fd/1')

if ironic_log_file:
    CONF.set_override("log_file", ironic_log_file)
    CONF.set_override("use_stderr", False)

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
        LOG.error(_LE(
            "Ansible task %(name)s failed on node %(node)s: %(res)s"),
            self.runner_msg_dict(result))

    def v2_runner_on_ok(self, result):
        msg_dict = self.runner_msg_dict(result)
        if msg_dict['name'] == 'setup':
            LOG.info(_LI(
                "Ansible task 'setup' complete on node %(node)s"),
                msg_dict)
        else:
            LOG.info(_LI(
                "Ansible task %(name)s complete on node %(node)s: %(res)s"),
                msg_dict)

    def v2_runner_on_unreachable(self, result):
        LOG.error(_LE(
            "Node %(node)s was unreachable for Ansible task %(name)s: "
            "%(res)s"),
            self.runner_msg_dict(result))

    def v2_runner_on_async_poll(self, result):
        LOG.debug("Polled ansible task %(name)s for complete "
                  "on node %(node)s: %(res)s",
                  self.runner_msg_dict(result))

    def v2_runner_on_async_ok(self, result):
        LOG.info(_LI(
            "Async Ansible task %(name)s complete on node %(node)s: %(res)s"),
            self.runner_msg_dict(result))

    def v2_runner_on_async_failed(self, result):
        LOG.error(_LE(
            "Async Ansible task %(name)s failed on node %(node)s: %(res)s"),
            self.runner_msg_dict(result))

    def v2_runner_on_skipped(self, result):
        LOG.debug("Ansible task %(name)s skipped on node %(node)s: %(res)s",
                  self.runner_msg_dict(result))
