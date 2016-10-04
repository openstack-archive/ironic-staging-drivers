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
Ansible deploy driver
"""

import json
import os
import shlex

from ironic_lib import metrics_utils
from ironic_lib import utils as irlib_utils
from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log
from oslo_utils import strutils
from oslo_utils import units
import retrying
import six
import six.moves.urllib.parse as urlparse
import yaml

from ironic.common import dhcp_factory
from ironic.common import exception
from ironic.common.i18n import _
from ironic.common.i18n import _LE
from ironic.common.i18n import _LI
from ironic.common.i18n import _LW
from ironic.common import images
from ironic.common import states
from ironic.common import utils
from ironic.conductor import rpcapi
from ironic.conductor import task_manager
from ironic.conductor import utils as manager_utils
from ironic.conf import CONF
from ironic.drivers import base
from ironic.drivers.modules import agent_base_vendor as agent_base
from ironic.drivers.modules import deploy_utils


ansible_opts = [
    cfg.StrOpt('ansible_extra_args',
               help=_('Extra arguments to pass on every '
                      'invocation of Ansible.')),
    cfg.IntOpt('verbosity',
               min=0,
               max=4,
               help=_('Set ansible verbosity level requested when invoking '
                      '"ansible-playbook" command. '
                      '4 includes detailed SSH session logging. '
                      'Default is 4 when global debug is enabled '
                      'and 0 otherwise.')),
    cfg.StrOpt('ansible_playbook_script',
               default='ansible-playbook',
               help=_('Path to "ansible-playbook" script. '
                      'Default will search the $PATH configured for user '
                      'running ironic-conductor process. '
                      'Provide the full path when ansible-playbook is not in '
                      '$PATH or installed in not default location.')),
    cfg.StrOpt('playbooks_path',
               default=os.path.join(os.path.dirname(__file__), 'playbooks'),
               help=_('Path to directory with playbooks, roles and '
                      'local inventory.')),
    cfg.StrOpt('config_file_path',
               default=os.path.join(
                   os.path.dirname(__file__), 'playbooks', 'ansible.cfg'),
               help=_('Path to ansible configuration file. If set to empty, '
                      'system default will be used.')),
    cfg.IntOpt('post_deploy_get_power_state_retries',
               min=0,
               default=6,
               help=_('Number of times to retry getting power state to check '
                      'if bare metal node has been powered off after a soft '
                      'power off.')),
    cfg.IntOpt('post_deploy_get_power_state_retry_interval',
               min=0,
               default=5,
               help=_('Amount of time (in seconds) to wait between polling '
                      'power state after trigger soft poweroff.')),
    cfg.IntOpt('extra_memory',
               default=10,
               help=_('Extra amount of memory in MiB expected to be consumed '
                      'by Ansible-related processes on the node. Affects '
                      'decision whether image will fit into RAM.')),
    cfg.BoolOpt('use_ramdisk_callback',
                default=True,
                help=_('Use callback request from ramdisk for start deploy or '
                       'cleaning. Disable it when using custom ramdisk '
                       'without callback script. '
                       'When callback is disabled, Neutron is mandatory.')),
]

CONF.register_opts(ansible_opts, group='ansible')

LOG = log.getLogger(__name__)

METRICS = metrics_utils.get_metrics_logger(__name__)

DEFAULT_PLAYBOOKS = {
    'deploy': 'deploy.yaml',
    'clean': 'clean.yaml'
}
DEFAULT_CLEAN_STEPS = 'clean_steps.yaml'

OPTIONAL_PROPERTIES = {
    'ansible_deploy_username': _('Deploy ramdisk username for Ansible. '
                                 'This user must have passwordless sudo '
                                 'permissions. Default is "ansible". '
                                 'Optional.'),
    'ansible_deploy_key_file': _('Path to private key file. If not specified, '
                                 'default keys for user running '
                                 'ironic-conductor process will be used. '
                                 'Note that for keys with password, those '
                                 'must be pre-loaded into ssh-agent. '
                                 'Optional.'),
    'ansible_deploy_playbook': _('Name of the Ansible playbook used for '
                                 'deployment. Default is %s. Optional.'
                                 ) % DEFAULT_PLAYBOOKS['deploy'],
    'ansible_clean_playbook': _('Name of the Ansible playbook used for '
                                'cleaning. Default is %s. Optional.'
                                ) % DEFAULT_PLAYBOOKS['clean'],
    'ansible_clean_steps_config': _('Name of the file with default cleaning '
                                    'steps configuration. Default is %s. '
                                    'Optional.'
                                    ) % DEFAULT_CLEAN_STEPS
}
COMMON_PROPERTIES = OPTIONAL_PROPERTIES

INVENTORY_FILE = os.path.join(CONF.ansible.playbooks_path, 'inventory')


class PlaybookNotFound(exception.IronicException):
    _msg_fmt = _('Failed to set ansible playbook for action %(action)s')


def _parse_ansible_driver_info(node, action='deploy'):
    user = node.driver_info.get('ansible_deploy_username', 'ansible')
    key = node.driver_info.get('ansible_deploy_key_file')
    playbook = node.driver_info.get('ansible_%s_playbook' % action,
                                    DEFAULT_PLAYBOOKS.get(action))
    if not playbook:
        raise PlaybookNotFound(action=action)
    return playbook, user, key


def _get_configdrive_path(basename):
    return os.path.join(CONF.tempdir, basename + '.cndrive')


def _get_node_ip(task):
    node = task.node
    if not CONF.ansible.use_ramdisk_callback:
        node_address = node.driver_internal_info.get('ansible_cleaning_ip')
        if not node_address:
            api = dhcp_factory.DHCPFactory().provider
            ip_addrs = api.get_ip_addresses(task)
            if not ip_addrs:
                raise exception.FailedToGetIPAddressOnPort(_(
                    "Failed to get IP address for any port on node %s.") %
                    node.uuid)
            if len(ip_addrs) > 1:
                error = _("Ansible driver does not support multiple IP "
                          "addresses during deploy or cleaning")
                raise exception.InstanceDeployFailure(reason=error)

            node_address = ip_addrs[0]
    else:
        callback_url = node.driver_internal_info.get('agent_url', '')
        node_address = urlparse.urlparse(callback_url).netloc.split(':')[0]

    return node_address


def _prepare_extra_vars(host_list, variables=None):
    nodes_var = []
    for node_uuid, ip, user, extra in host_list:
        nodes_var.append(dict(name=node_uuid, ip=ip, user=user, extra=extra))
    extra_vars = dict(ironic_nodes=nodes_var)
    if variables:
        extra_vars.update(variables)
    return extra_vars


def _run_playbook(name, extra_vars, key, tags=None, notags=None):
    """Execute ansible-playbook."""
    playbook = os.path.join(CONF.ansible.playbooks_path, name)
    args = [CONF.ansible.ansible_playbook_script, playbook,
            '-i', INVENTORY_FILE,
            '-e', json.dumps(extra_vars),
            ]

    if CONF.ansible.config_file_path:
        env = ['env', 'ANSIBLE_CONFIG=%s' % CONF.ansible.config_file_path]
        args = env + args

    if tags:
        args.append('--tags=%s' % ','.join(tags))

    if notags:
        args.append('--skip-tags=%s' % ','.join(notags))

    if key:
        args.append('--private-key=%s' % key)

    verbosity = CONF.ansible.verbosity
    if verbosity is None and CONF.debug:
        verbosity = 4
    if verbosity:
        args.append('-' + 'v' * verbosity)

    if CONF.ansible.ansible_extra_args:
        args.extend(shlex.split(CONF.ansible.ansible_extra_args))

    try:
        out, err = utils.execute(*args)
        return out, err
    except processutils.ProcessExecutionError as e:
        raise exception.InstanceDeployFailure(reason=e)


def _calculate_memory_req(task):
    image_source = task.node.instance_info['image_source']
    image_size = images.download_size(task.context, image_source)
    return image_size // units.Mi + CONF.ansible.extra_memory


def _parse_partitioning_info(node):

    info = node.instance_info
    i_info = {}

    partitions = []
    root_partition = {'name': 'root',
                      'size_mib': info['root_mb'],
                      'boot': 'yes',
                      'swap': 'no'}
    partitions.append(root_partition)

    swap_mb = info['swap_mb']
    if swap_mb:
        swap_partition = {'name': 'swap',
                          'size_mib': swap_mb,
                          'boot': 'no',
                          'swap': 'yes'}
        partitions.append(swap_partition)

    ephemeral_mb = info['ephemeral_mb']
    if ephemeral_mb:
        ephemeral_partition = {'name': 'ephemeral',
                               'size_mib': ephemeral_mb,
                               'boot': 'no',
                               'swap': 'no'}
        partitions.append(ephemeral_partition)

        i_info['ephemeral_format'] = info['ephemeral_format']
        i_info['preserve_ephemeral'] = (
            'yes' if info['preserve_ephemeral'] else 'no')

    i_info['ironic_partitions'] = partitions
    return i_info


def _prepare_variables(task):
    node = task.node
    i_info = node.instance_info
    image = {
        'url': i_info['image_url'],
        'mem_req': _calculate_memory_req(task),
        'disk_format': i_info.get('image_disk_format'),
    }
    checksum = i_info.get('image_checksum')
    if checksum:
        # NOTE(pas-ha) checksum can be in <algo>:<checksum> format
        # as supported by various Ansible modules, mostly good for
        # standalone Ironic case when instance_info is populated manually.
        # With no <algo> we take that instance_info is populated from Glance,
        # where API reports checksum as MD5 always.
        if ':' not in checksum:
            checksum = 'md5:%s' % checksum
        image['checksum'] = checksum
    variables = {'image': image}
    configdrive = i_info.get('configdrive')
    if configdrive:
        if urlparse.urlparse(configdrive).scheme in ('http', 'https'):
            cfgdrv_type = 'url'
            cfgdrv_location = configdrive
        else:
            cfgdrv_location = _get_configdrive_path(node.uuid)
            with open(cfgdrv_location, 'w') as f:
                f.write(configdrive)
            cfgdrv_type = 'file'
        variables['configdrive'] = {'type': cfgdrv_type,
                                    'location': cfgdrv_location}
    return variables


def _validate_clean_steps(steps, node_uuid):
    missing = []
    for step in steps:
        name = step.setdefault('name', 'unnamed')
        if 'interface' not in step:
            missing.append({'name': name, 'field': 'interface'})
        args = step.get('args', {})
        for arg_name, arg in args.items():
            if arg.get('required', False) and 'value' not in arg:
                missing.append({'name': name,
                                'field': '%s.value' % arg_name})
    if missing:
        err_string = ', '.join(
            'name %(name)s, field %(field)s' % i for i in missing)
        msg = _("Malformed clean_steps file: %s") % err_string
        LOG.error(msg)
        raise exception.NodeCleaningFailure(node=node_uuid,
                                            reason=msg)


def _get_clean_steps(node, interface=None, override_priorities=None):
    """Get cleaning steps."""
    clean_steps_file = node.driver_info.get('ansible_clean_steps_config',
                                            DEFAULT_CLEAN_STEPS)
    path = os.path.join(CONF.ansible.playbooks_path, clean_steps_file)
    try:
        with open(path) as f:
            internal_steps = yaml.safe_load(f)
    except Exception as e:
        msg = _('Failed to load clean steps from file '
                '%(file)s: %(exc)s') % {'file': path, 'exc': e}
        raise exception.NodeCleaningFailure(node=node.uuid, reason=msg)

    _validate_clean_steps(internal_steps, node.uuid)

    steps = []
    override = override_priorities or {}
    for params in internal_steps:
        name = params.get('name', 'unnamed')
        clean_if = params['interface']
        if interface is not None and interface != clean_if:
            continue
        new_priority = override.get(name)
        priority = (new_priority if new_priority is not None else
                    params.get('priority', 0))
        args = {}
        argsinfo = params.get('args', {})
        for arg, arg_info in argsinfo.items():
            args[arg] = arg_info.pop('value', None)
        step = {
            'interface': clean_if,
            'step': name,
            'priority': priority,
            'abortable': False,
            'argsinfo': argsinfo,
            'args': args
        }
        steps.append(step)

    return steps


# TODO(pas-ha) verbatim copy from agent_base_vendor
# remove if/when CR404364 is merged
def _notify_conductor_resume_clean(task):
    LOG.debug('Sending RPC to conductor to resume cleaning for node %s',
              task.node.uuid)
    uuid = task.node.uuid
    rpc = rpcapi.ConductorAPI()
    topic = rpc.get_topic_for(task.node)
    # Need to release the lock to let the conductor take it
    task.release_resources()
    rpc.continue_node_clean(task.context, uuid, topic=topic)


# TODO(pas-ha) inherit from HeartbeatMixin if/when CR404364 is merged
class AnsibleDeploy(agent_base.AgentDeployMixin, base.DeployInterface):
    """Interface for deploy-related actions."""

    def __init__(self):
        # NOTE(pas-ha) overriding agent creation as we won't be
        # communicating with it, only processing heartbeats
        self._client = None

    def get_properties(self):
        """Return the properties of the interface."""
        props = COMMON_PROPERTIES.copy()
        # NOTE(pas-ha) this is to get the deploy_forces_oob_reboot property
        props.update(agent_base.VENDOR_PROPERTIES)
        return props

    @METRICS.timer('AnsibleDeploy.validate')
    def validate(self, task):
        """Validate the driver-specific Node deployment info."""
        task.driver.boot.validate(task)

        node = task.node
        iwdi = node.driver_internal_info.get('is_whole_disk_image')
        if not iwdi and deploy_utils.get_boot_option(node) == "netboot":
            raise exception.InvalidParameterValue(_(
                "Node %(node)s is configured to use the %(driver)s driver "
                "which does not support netboot.") % {'node': node.uuid,
                                                      'driver': node.driver})

        params = {}
        image_source = node.instance_info.get('image_source')
        params['instance_info.image_source'] = image_source
        error_msg = _('Node %s failed to validate deploy image info. Some '
                      'parameters were missing') % node.uuid
        deploy_utils.check_for_missing_params(params, error_msg)

    def _deploy(self, task, node_address):
        """Internal function for deployment to a node."""
        notags = ['shutdown']
        if CONF.ansible.use_ramdisk_callback:
            notags.append('wait')
        node = task.node
        LOG.debug('IP of node %(node)s is %(ip)s',
                  {'node': node.uuid, 'ip': node_address})
        variables = _prepare_variables(task)
        iwdi = node.driver_internal_info.get('is_whole_disk_image')
        if iwdi:
            notags.append('parted')
        else:
            variables.update(_parse_partitioning_info(task.node))
        playbook, user, key = _parse_ansible_driver_info(task.node)
        node_list = [(node.uuid, node_address, user, node.extra)]
        extra_vars = _prepare_extra_vars(node_list, variables=variables)

        LOG.debug('Starting deploy on node %s', node.uuid)
        # any caller should manage exceptions raised from here
        _run_playbook(playbook, extra_vars, key, notags=notags)

    @METRICS.timer('AnsibleDeploy.deploy')
    @task_manager.require_exclusive_lock
    def deploy(self, task):
        """Perform a deployment to a node."""
        manager_utils.node_power_action(task, states.REBOOT)
        if CONF.ansible.use_ramdisk_callback:
            return states.DEPLOYWAIT

        node = task.node
        ip_addr = _get_node_ip(task)
        try:
            self._deploy(task, ip_addr)
        except Exception as e:
            error = _('Deploy failed for node %(node)s: '
                      'Error: %(exc)s') % {'node': node.uuid,
                                           'exc': six.text_type(e)}
            LOG.exception(error)
            deploy_utils.set_failed_state(task, error, collect_logs=False)

        else:
            self.reboot_to_instance(task)
            return states.DEPLOYDONE

    @METRICS.timer('AnsibleDeploy.tear_down')
    @task_manager.require_exclusive_lock
    def tear_down(self, task):
        """Tear down a previous deployment on the task's node."""
        manager_utils.node_power_action(task, states.POWER_OFF)
        task.driver.network.unconfigure_tenant_networks(task)
        return states.DELETED

    @METRICS.timer('AnsibleDeploy.prepare')
    def prepare(self, task):
        """Prepare the deployment environment for this node."""
        node = task.node
        # TODO(pas-ha) investigate takeover scenario
        if node.provision_state == states.DEPLOYING:
            # adding network-driver dependent provisioning ports
            manager_utils.node_power_action(task, states.POWER_OFF)
            task.driver.network.add_provisioning_network(task)
        if node.provision_state not in [states.ACTIVE, states.ADOPTING]:
            node.instance_info = deploy_utils.build_instance_info_for_deploy(
                task)
            node.save()
            boot_opt = deploy_utils.build_agent_options(node)
            task.driver.boot.prepare_ramdisk(task, boot_opt)

    @METRICS.timer('AnsibleDeploy.clean_up')
    def clean_up(self, task):
        """Clean up the deployment environment for this node."""
        task.driver.boot.clean_up_ramdisk(task)
        provider = dhcp_factory.DHCPFactory()
        provider.clean_dhcp(task)
        irlib_utils.unlink_without_raise(
            _get_configdrive_path(task.node.uuid))

    def take_over(self, task):
        LOG.error(_LE("Ansible deploy does not support take over. "
                  "You must redeploy the node %s explicitly."),
                  task.node.uuid)

    def get_clean_steps(self, task):
        """Get the list of clean steps from the file.

        :param task: a TaskManager object containing the node
        :returns: A list of clean step dictionaries
        """
        new_priorities = {
            'erase_devices': CONF.deploy.erase_devices_priority,
            'erase_devices_metadata':
                CONF.deploy.erase_devices_metadata_priority
        }
        return _get_clean_steps(task.node, interface='deploy',
                                override_priorities=new_priorities)

    # TODO(pas-ha) remove this if/when CR404364 is merged
    def _refresh_clean_steps(self, task):
        # no agent - no steps. all steps are known to conductor already
        pass

    @METRICS.timer('AnsibleDeploy.execute_clean_step')
    def execute_clean_step(self, task, step):
        """Execute a clean step.

        :param task: a TaskManager object containing the node
        :param step: a clean step dictionary to execute
        :returns: None
        """
        node = task.node
        playbook, user, key = _parse_ansible_driver_info(
            task.node, action='clean')
        stepname = step['step']

        node_address = _get_node_ip(task)
        if not node_address:
            raise exception.NodeCleaningFailure(node=node.uuid,
                                                reason='undefined node IP '
                                                'addresses')
        node_list = [(node.uuid, node_address, user, node.extra)]
        extra_vars = _prepare_extra_vars(node_list)

        LOG.debug('Starting cleaning step %(step)s on node %(node)s',
                  {'node': node.uuid, 'step': stepname})
        step_tags = step['args'].get('tags', [])
        try:
            _run_playbook(playbook, extra_vars, key,
                          tags=step_tags)
        except exception.InstanceDeployFailure as e:
            LOG.error(_LE("Ansible failed cleaning step %(step)s "
                          "on node %(node)s."), {
                              'node': node.uuid, 'step': stepname})
            manager_utils.cleaning_error_handler(task, six.text_type(e))
        else:
            LOG.info(_LI('Ansible completed cleaning step %(step)s '
                         'on node %(node)s.'),
                     {'node': node.uuid, 'step': stepname})

    @METRICS.timer('AnsibleDeploy.prepare_cleaning')
    def prepare_cleaning(self, task):
        """Boot into the ramdisk to prepare for cleaning.

        :param task: a TaskManager object containing the node
        :raises NodeCleaningFailure: if the previous cleaning ports cannot
                be removed or if new cleaning ports cannot be created
        :returns: None or states.CLEANWAIT for async prepare.
        """
        node = task.node
        use_callback = CONF.ansible.use_ramdisk_callback
        if use_callback:
            manager_utils.set_node_cleaning_steps(task)
            if not node.driver_internal_info['clean_steps']:
                # no clean steps configured, nothing to do.
                return
        task.driver.network.add_cleaning_network(task)
        boot_opt = deploy_utils.build_agent_options(node)
        task.driver.boot.prepare_ramdisk(task, boot_opt)
        manager_utils.node_power_action(task, states.REBOOT)
        if use_callback:
            return states.CLEANWAIT

        ip_addr = _get_node_ip(task)
        LOG.debug('IP of node %(node)s is %(ip)s',
                  {'node': node.uuid, 'ip': ip_addr})
        driver_internal_info = node.driver_internal_info
        driver_internal_info['ansible_cleaning_ip'] = ip_addr
        node.driver_internal_info = driver_internal_info
        node.save()
        playbook, user, key = _parse_ansible_driver_info(
            task.node, action='clean')
        node_list = [(node.uuid, ip_addr, user, node.extra)]
        extra_vars = _prepare_extra_vars(node_list)

        LOG.debug('Waiting ramdisk on node %s for cleaning', node.uuid)
        _run_playbook(playbook, extra_vars, key, tags=['wait'])
        LOG.info(_LI('Node %s is ready for cleaning'), node.uuid)

    @METRICS.timer('AnsibleDeploy.tear_down_cleaning')
    def tear_down_cleaning(self, task):
        """Clean up the PXE and DHCP files after cleaning.

        :param task: a TaskManager object containing the node
        :raises NodeCleaningFailure: if the cleaning ports cannot be
                removed
        """
        node = task.node
        driver_internal_info = node.driver_internal_info
        driver_internal_info.pop('ansible_cleaning_ip', None)
        node.driver_internal_info = driver_internal_info
        node.save()
        manager_utils.node_power_action(task, states.POWER_OFF)
        task.driver.boot.clean_up_ramdisk(task)
        task.driver.network.remove_cleaning_network(task)

    # TODO(pas-ha) remove all these dummies if/when CR404364 is merged
    def prepare_instance_to_boot(self, task, root_uuid, efi_sys_uuid):
        # NOTE(pas-ha) dummy plug just in case,
        # as this driver does not support netboot for now,
        # and localboot prepare is happening in the playbooks
        pass

    def configure_local_boot(self, task, root_uuid=None,
                             efi_system_part_uuid=None):
        # NOTE(pas-ha) dummy plug just in case,
        # as localboot preparation is happening in the playbooks
        pass

    def deploy_has_started(self, task):
        # NOTE(pas-ha) this driver currently has only single transition
        # from DEPLOYWAIT to DEPLOYING on first heartbeat,
        # but just in case always return False here
        return False

    def deploy_is_done(self, task):
        # NOTE(pas-ha) should never reach here in the first place,
        # as after the first heartbeat node is never entering DEPLOYWAIT
        # state but just in case always return False so node does not goes
        # to reboot prematurely
        return False

    def continue_cleaning(self, task):
        # NOTE(pas-ha) should never reach here in the first place,
        # but have dummy plug just in case
        pass

    @METRICS.timer('AnsibleDeploy.continue_deploy')
    def continue_deploy(self, task):
        task.upgrade_lock(purpose='deploy')
        task.process_event('resume')
        node_address = _get_node_ip(task)
        if not node_address:
            raise exception.InstanceDeployFailure(
                _("Failed to get node IP address of node %s") % task.node.uuid)
        self._deploy(task, node_address)
        self.reboot_to_instance(task)

    @METRICS.timer('AnsibleDeploy.reboot_to_instance')
    def reboot_to_instance(self, task):
        node = task.node
        LOG.info(_LI('Ansible complete deploy on node %s'), node.uuid)

        LOG.debug('Rebooting node %s to instance', node.uuid)
        manager_utils.node_set_boot_device(task, 'disk', persistent=True)
        self.reboot_and_finish_deploy(task)

        if task.driver.boot:
            task.driver.boot.clean_up_ramdisk(task)

    @METRICS.timer('AnsibleDeploy.reboot_and_finish_deploy')
    def reboot_and_finish_deploy(self, task):
        wait = CONF.ansible.post_deploy_get_power_state_retry_interval * 1000
        attempts = CONF.ansible.post_deploy_get_power_state_retries + 1

        @retrying.retry(
            stop_max_attempt_number=attempts,
            retry_on_result=lambda state: state != states.POWER_OFF,
            wait_fixed=wait
        )
        def _wait_until_powered_off(task):
            return task.driver.power.get_power_state(task)

        node = task.node
        oob_power_off = strutils.bool_from_string(
            node.driver_info.get('deploy_forces_oob_reboot', False))
        try:
            if not oob_power_off:
                try:
                    node_address = _get_node_ip(task)
                    if not node_address:
                        raise exception.InstanceDeployFailure(
                            _("Failed to get node IP address of node %s") %
                            node.uuid)
                    playbook, user, key = _parse_ansible_driver_info(
                        node)
                    node_list = [(node.uuid, node_address, user, node.extra)]
                    extra_vars = _prepare_extra_vars(node_list)
                    _run_playbook(playbook, extra_vars, key,
                                  tags=['shutdown'])
                    _wait_until_powered_off(task)
                except Exception as e:
                    LOG.warning(
                        _LW('Failed to soft power off node %(node_uuid)s '
                            'in at least %(timeout)d seconds. '
                            'Error: %(error)s'),
                        {'node_uuid': node.uuid,
                         'timeout': (wait * (attempts - 1)) / 1000,
                         'error': e})
            # NOTE(pas-ha) flush is a part of deploy playbook
            # so if it finished successfully we can safely
            # power off the node out-of-band
            manager_utils.node_power_action(task, states.POWER_OFF)
            task.driver.network.remove_provisioning_network(task)
            task.driver.network.configure_tenant_networks(task)
            manager_utils.node_power_action(task, states.POWER_ON)
        except Exception as e:
            msg = (_('Error rebooting node %(node)s after deploy. '
                     'Error: %(error)s') %
                   {'node': node.uuid, 'error': e})
            agent_base.log_and_raise_deployment_error(task, msg)

        task.process_event('done')
        LOG.info(_LI('Deployment to node %s done'), task.node.uuid)

    # TODO(pas-ha) almost verbatim copy from agent_base_vendor.AgentDeploMixin
    # except for single last line to force skipping agent log collection
    # remove this if/when CR404364 is merged
    def heartbeat(self, task, callback_url):
        """Process a heartbeat.

        :param task: task to work with.
        :param callback_url: agent HTTP API URL.
        """
        # TODO(dtantsur): upgrade lock only if we actually take action other
        # than updating the last timestamp.
        task.upgrade_lock()

        node = task.node
        LOG.debug('Heartbeat from node %s', node.uuid)

        driver_internal_info = node.driver_internal_info
        driver_internal_info['agent_url'] = callback_url

        # TODO(rloo): 'agent_last_heartbeat' was deprecated since it wasn't
        # being used so remove that entry if it exists.
        # Hopefully all nodes will have been updated by Pike, so
        # we can delete this code then.
        driver_internal_info.pop('agent_last_heartbeat', None)

        node.driver_internal_info = driver_internal_info
        node.save()

        # Async call backs don't set error state on their own
        # TODO(jimrollenhagen) improve error messages here
        msg = _('Failed checking if deploy is done.')
        try:
            if node.maintenance:
                # this shouldn't happen often, but skip the rest if it does.
                LOG.debug('Heartbeat from node %(node)s in maintenance mode; '
                          'not taking any action.', {'node': node.uuid})
                return
            elif (node.provision_state == states.DEPLOYWAIT and
                  not self.deploy_has_started(task)):
                msg = _('Node failed to get image for deploy.')
                self.continue_deploy(task)
            elif (node.provision_state == states.DEPLOYWAIT and
                  self.deploy_is_done(task)):
                msg = _('Node failed to move to active state.')
                self.reboot_to_instance(task)
            elif (node.provision_state == states.DEPLOYWAIT and
                  self.deploy_has_started(task)):
                node.touch_provisioning()
            elif node.provision_state == states.CLEANWAIT:
                node.touch_provisioning()
                try:
                    if not node.clean_step:
                        LOG.debug('Node %s just booted to start cleaning.',
                                  node.uuid)
                        msg = _('Node failed to start the first cleaning '
                                'step.')
                        # First, cache the clean steps
                        self._refresh_clean_steps(task)
                        # Then set/verify node clean steps and start cleaning
                        manager_utils.set_node_cleaning_steps(task)
                        _notify_conductor_resume_clean(task)
                    else:
                        msg = _('Node failed to check cleaning progress.')
                        self.continue_cleaning(task)
                except exception.NoFreeConductorWorker:
                    # waiting for the next heartbeat, node.last_error and
                    # logging message is filled already via conductor's hook
                    pass

        except Exception as e:
            err_info = {'node': node.uuid, 'msg': msg, 'e': e}
            last_error = _('Asynchronous exception for node %(node)s: '
                           '%(msg)s Exception: %(e)s') % err_info
            LOG.exception(last_error)
            if node.provision_state in (states.CLEANING, states.CLEANWAIT):
                manager_utils.cleaning_error_handler(task, last_error)
            elif node.provision_state in (states.DEPLOYING, states.DEPLOYWAIT):
                deploy_utils.set_failed_state(
                    task, last_error, collect_logs=bool(self._client))
