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

import json
import os

from ironic.common import exception
from ironic.drivers import base
from ironic.drivers.modules import ipmitool
from ironic_lib import utils as ironic_utils
import jsonschema
from jsonschema import exceptions as json_schema_exc
from oslo_config import cfg
from oslo_log import log
from oslo_utils import excutils
import six

from ironic_staging_drivers.common.i18n import _
from ironic_staging_drivers.intel_nm import nm_commands


CONF = cfg.CONF
CONF.import_opt('tempdir', 'ironic.common.utils')
LOG = log.getLogger(__name__)

SCHEMAS = ('control_schema', 'get_cap_schema', 'main_ids_schema',
           'policy_schema', 'suspend_schema', 'statistics_schema')


def _command_to_string(cmd):
    """Convert a list with command raw bytes to string."""
    return ' '.join(cmd)


def _get_nm_address(task):
    """Get Intel Node Manager target channel and address.

    :param task: a TaskManager instance.
    :raises: IPMIFailure if Intel Node Manager is not detected on a node or if
             an error happens during detection.
    :returns: a tuple with IPMI channel and address of Intel Node Manager.
    """
    node = task.node
    driver_internal_info = node.driver_internal_info

    def _save_to_node(channel, address):
        driver_internal_info['intel_nm_channel'] = channel
        driver_internal_info['intel_nm_address'] = address
        node.driver_internal_info = driver_internal_info
        node.save()

    channel = driver_internal_info.get('intel_nm_channel')
    address = driver_internal_info.get('intel_nm_address')
    if channel and address:
        return channel, address
    if channel is False and address is False:
        raise exception.IPMIFailure(_('Driver data indicates that Intel '
                                      'Node Manager detection failed.'))
    LOG.info('Start detection of Intel Node Manager on node %s',
             node.uuid)
    sdr_filename = os.path.join(CONF.tempdir, node.uuid + '.sdr')
    res = None
    try:
        ipmitool.dump_sdr(task, sdr_filename)
        res = nm_commands.parse_slave_and_channel(sdr_filename)
    finally:
        ironic_utils.unlink_without_raise(sdr_filename)
    if res is None:
        _save_to_node(False, False)
        raise exception.IPMIFailure(_('Intel Node Manager is not detected.'))
    address, channel = res
    LOG.debug('Intel Node Manager sensors present in SDR on node %(node)s, '
              'channel %(channel)s address %(address)s.',
              {'node': node.uuid, 'channel': channel, 'address': address})
    # SDR can contain wrong info, try simple command
    node.driver_info['ipmi_bridging'] = 'single'
    node.driver_info['ipmi_target_channel'] = channel
    node.driver_info['ipmi_target_address'] = address
    try:
        ipmitool.send_raw(task,
                          _command_to_string(nm_commands.get_version(None)))
        _save_to_node(channel, address)
        return channel, address
    except exception.IPMIFailure:
        _save_to_node(False, False)
        raise exception.IPMIFailure(_('Intel Node Manager sensors record '
                                      'present in SDR but Node Manager is not '
                                      'responding.'))


def _execute_nm_command(task, data, command_func, parse_func=None):
    """Execute Intel Node Manager command via send_raw().

    :param task: a TaskManager instance.
    :param data: a dict with data passed to vendor's method.
    :param command_func: a function that returns raw command bytes.
    :param parse_func: a function that parses returned raw bytes.
    :raises: IPMIFailure if Intel Node Manager is not detected on a node or if
             an error happens during command execution.
    :returns: a dict with parsed output or None if command does not return
              user's info.
    """
    try:
        channel, address = _get_nm_address(task)
    except exception.IPMIFailure as e:
        with excutils.save_and_reraise_exception():
            LOG.exception('Can not obtain Intel Node Manager address for '
                          'node %(node)s: %(err)s',
                          {'node': task.node.uuid, 'err': six.text_type(e)})
    driver_info = task.node.driver_info
    driver_info['ipmi_bridging'] = 'single'
    driver_info['ipmi_target_channel'] = channel
    driver_info['ipmi_target_address'] = address
    cmd = _command_to_string(command_func(data))
    out = ipmitool.send_raw(task, cmd)[0]
    if parse_func:
        try:
            return parse_func(out.split())
        except exception.IPMIFailure as e:
            with excutils.save_and_reraise_exception():
                LOG.exception('Error in returned data for node %(node)s: '
                              '%(err)s', {'node': task.node.uuid,
                                          'err': six.text_type(e)})


class IntelNMVendorPassthru(base.VendorInterface):
    """Intel Node Manager policies vendor interface."""

    def __init__(self):
        schemas_dir = os.path.dirname(__file__)
        for schema in SCHEMAS:
            filename = os.path.join(schemas_dir, schema + '.json')
            with open(filename, 'r') as sf:
                setattr(self, schema, json.load(sf))

    def _validate_policy_methods(self, method, **kwargs):
        if method in ('get_nm_policy', 'remove_nm_policy',
                      'get_nm_policy_suspend', 'remove_nm_policy_suspend'):
            jsonschema.validate(kwargs, self.main_ids_schema)

        elif method == 'control_nm_policy':
            jsonschema.validate(kwargs, self.control_schema)
            if kwargs['scope'] != 'global' and 'domain_id' not in kwargs:
                raise exception.MissingParameterValue(_('Missing "domain_id"'))
            if kwargs['scope'] == 'policy' and 'policy_id' not in kwargs:
                raise exception.MissingParameterValue(_('Missing "policy_id"'))

        elif method == 'set_nm_policy':
            jsonschema.validate(kwargs, self.policy_schema)
            if kwargs['policy_trigger'] == 'boot':
                if not isinstance(kwargs['target_limit'], dict):
                    raise exception.InvalidParameterValue(_('Invalid boot '
                                                            'policy'))
            elif 'correction_time' not in kwargs:
                raise exception.MissingParameterValue(
                    _('Missing "correction_time" for no-boot policy'))

        elif method == 'set_nm_policy_suspend':
            jsonschema.validate(kwargs, self.suspend_schema)

        elif method == 'get_nm_capabilities':
            jsonschema.validate(kwargs, self.get_cap_schema)

    def _validate_statistics_methods(self, method, **kwargs):
        jsonschema.validate(kwargs, self.statistics_schema)

        global_params = ('unhandled_requests', 'response_time',
                         'cpu_throttling', 'memory_throttling',
                         'communication_failures')

        if kwargs['scope'] == 'policy' and 'policy_id' not in kwargs:
                raise exception.MissingParameterValue(_('Missing "policy_id"'))

        if kwargs.get('parameter_name') not in global_params:
            if 'domain_id' not in kwargs:
                raise exception.MissingParameterValue(_('Missing "domain_id"'))

        if method == 'reset_nm_statistics':
            if 'parameter_name' in kwargs:
                if kwargs['parameter_name'] not in global_params:
                    raise exception.InvalidParameterValue(
                        _('Invalid parameter name for resetting statistic, '
                          'individual reset is possible only for: %s') %
                        ', '.join(global_params))

        elif method == 'get_nm_statistics':
            if 'parameter_name' not in kwargs:
                raise exception.MissingParameterValue(
                    _('Parameter name is mandatory for getting statistics'))
            # valid parameters depend on scope
            if (kwargs['parameter_name'] not in
                nm_commands.STATISTICS[kwargs['scope']]):
                    raise exception.InvalidParameterValue(
                        _('Invalid parameter name %(param)% for scope '
                          '%(scope)s') % {'param': kwargs['parameter_name'],
                                          'scope': kwargs['scope']})

    def get_properties(self):
        """Returns the properties of the interface.."""
        return {}

    def validate(self, task, method, http_method, **kwargs):
        """Validates the vendor method's parameters.

        This method validates whether the supplied data contains the required
        information for the driver.

        :param task: a TaskManager instance.
        :param method: name of vendor method.
        :param http_method: HTTP method.
        :param kwargs: data passed to vendor's method.
        :raises: InvalidParameterValue if supplied data is not valid.
        :raises: MissingParameterValue if parameters missing in supplied data.
        """
        try:
            if 'statistics' in method:
                self._validate_statistics_methods(method, **kwargs)
            else:
                self._validate_policy_methods(method, **kwargs)
        except json_schema_exc.ValidationError as e:
            raise exception.InvalidParameterValue(_('Input data validation '
                                                    'error: %s') % e)

    @base.passthru(['PUT'])
    def control_nm_policy(self, task, **kwargs):
        """Enable or disable Intel Node Manager policy control.

        :param task: a TaskManager instance.
        :param kwargs: data passed to method.
        :raises: IPMIFailure on an error.
        """
        _execute_nm_command(task, kwargs, nm_commands.control_policies)

    @base.passthru(['PUT'])
    def set_nm_policy(self, task, **kwargs):
        """Set Intel Node Manager policy.

        :param task: a TaskManager instance.
        :param kwargs: data passed to method.
        :raises: IPMIFailure on an error.
        """
        _execute_nm_command(task, kwargs, nm_commands.set_policy)

    @base.passthru(['GET'], async_call=False)
    def get_nm_policy(self, task, **kwargs):
        """Get Intel Node Manager policy.

        :param task: a TaskManager instance.
        :param kwargs: data passed to method.
        :raises: IPMIFailure on an error.
        :returns: a dictionary containing policy settings.
        """
        return _execute_nm_command(task, kwargs, nm_commands.get_policy,
                                   nm_commands.parse_policy)

    @base.passthru(['DELETE'])
    def remove_nm_policy(self, task, **kwargs):
        """Remove Intel Node Manager policy.

        :param task: a TaskManager instance.
        :param kwargs: data passed to method.
        :raises: IPMIFailure on an error.
        """
        _execute_nm_command(task, kwargs, nm_commands.remove_policy)

    @base.passthru(['PUT'])
    def set_nm_policy_suspend(self, task, **kwargs):
        """Set Intel Node Manager policy suspend periods.

        :param task: a TaskManager instance.
        :param kwargs: data passed to method.
        :raises: IPMIFailure on an error.
        """
        _execute_nm_command(task, kwargs, nm_commands.set_policy_suspend)

    @base.passthru(['GET'], async_call=False)
    def get_nm_policy_suspend(self, task, **kwargs):
        """Get Intel Node Manager policy suspend periods.

        :param task: a TaskManager instance.
        :param kwargs: data passed to method.
        :raises: IPMIFailure on an error.
        :returns: a dictionary containing suspend info for a policy.
        """
        return _execute_nm_command(task, kwargs,
                                   nm_commands.get_policy_suspend,
                                   nm_commands.parse_policy_suspend)

    @base.passthru(['DELETE'])
    def remove_nm_policy_suspend(self, task, **kwargs):
        """Remove Intel Node Manager policy suspend periods.

        :param task: a TaskManager instance.
        :param kwargs: data passed to method.
        :raises: IPMIFailure on an error.
        """
        _execute_nm_command(task, kwargs, nm_commands.remove_policy_suspend)

    @base.passthru(['GET'], async_call=False)
    def get_nm_capabilities(self, task, **kwargs):
        """Get Intel Node Manager capabilities.

        :param task: a TaskManager instance.
        :param kwargs: data passed to method.
        :raises: IPMIFailure on an error.
        :returns: a dictionary containing Intel NM capabilities.
        """
        return _execute_nm_command(task, kwargs, nm_commands.get_capabilities,
                                   nm_commands.parse_capabilities)

    @base.passthru(['GET'], async_call=False)
    def get_nm_version(self, task, **kwargs):
        """Get Intel Node Manager version.

        :param task: a TaskManager instance.
        :param kwargs: data passed to method.
        :raises: IPMIFailure on an error.
        :returns: a dictionary containing Intel NM version.
        """
        return _execute_nm_command(task, kwargs, nm_commands.get_version,
                                   nm_commands.parse_version)

    @base.passthru(['GET'], async_call=False)
    def get_nm_statistics(self, task, **kwargs):
        """Get Intel Node Manager statistics.

        :param task: a TaskManager instance.
        :param kwargs: data passed to method.
        :raises: IPMIFailure on an error.
        :returns: a dictionary containing statistics info.
        """
        return _execute_nm_command(task, kwargs,
                                   nm_commands.get_statistics,
                                   nm_commands.parse_statistics)

    @base.passthru(['PUT'])
    def reset_nm_statistics(self, task, **kwargs):
        """Reset Intel Node Manager statistics.

        :param task: a TaskManager instance.
        :param kwargs: data passed to method.
        :raises: IPMIFailure on an error.
        """
        _execute_nm_command(task, kwargs, nm_commands.reset_statistics)
