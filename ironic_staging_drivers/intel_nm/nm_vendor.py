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
from ironic_lib import utils as ironic_utils
import jsonschema
from jsonschema import exceptions as json_schema_exc
from oslo_config import cfg
from oslo_log import log
from oslo_utils import excutils

from ironic_staging_drivers.common.i18n import _
from ironic_staging_drivers.common.i18n import _LE
from ironic_staging_drivers.common.i18n import _LI
from ironic_staging_drivers.intel_nm import ipmi
from ironic_staging_drivers.intel_nm import nm_commands


CONF = cfg.CONF
CONF.import_opt('tempdir', 'ironic.common.utils')
LOG = log.getLogger(__name__)

SCHEMAS = ('control_schema', 'get_cap_schema', 'main_ids_schema',
           'policy_schema', 'suspend_schema')


def _command_to_string(cmd):
    return ' '.join(cmd)


def _get_nm_address(task):
    """Get Intel NM target channel and address."""
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
    fail_msg = _('Driver data indicates that Intel Node Manager detection '
                 'failed.')
    if channel is False and address is False:
        raise exception.IPMIFailure(fail_msg)
    LOG.info(_LI('Start detection of Intel Node Manager on node %s'),
             node.uuid)
    sdr_filename = os.path.join(CONF.tempdir, node.uuid + '.sdr')
    res = None
    try:
        ipmi.dump_sdr(task, sdr_filename)
        res = nm_commands.parse_slave_and_channel(sdr_filename)
    finally:
        ironic_utils.unlink_without_raise(sdr_filename)
    LOG.debug('Detecting (channel, address) values is %s', res)
    fail_msg = _('Intel Node Manager is not detected.')
    if res is None:
        _save_to_node(False, False)
        raise exception.IPMIFailure(fail_msg)
    # SDR info can contain wrong info, try simple command
    address, channel = res
    node.driver_info['ipmi_bridging'] = 'single'
    node.driver_info['ipmi_target_channel'] = channel
    node.driver_info['ipmi_target_address'] = address
    fail_msg = _('Intel Node Manager sensors record present in SDR but it is '
                 'not responding.')
    try:
        ipmi.send_raw(task, _command_to_string(nm_commands.get_version(None)))
        _save_to_node(channel, address)
        return channel, address
    except exception.IPMIFailure:
        _save_to_node(False, False)
        raise exception.IPMIFailure(fail_msg)


def _execute_nm_command(task, data, command_func, parse_func=None):
    """Execute NM command via send_raw() ipmitool driver method."""
    try:
        channel, address = _get_nm_address(task)
    except exception.IPMIFailure as e:
        with excutils.save_and_reraise_exception():
            LOG.exception(_LE('Can not obtain Intel Node Manager address for '
                              'node %(node)s: %(err)s'),
                          {'node': task.node.uuid, 'err': e})
    driver_info = task.node.driver_info
    driver_info['ipmi_bridging'] = 'single'
    driver_info['ipmi_target_channel'] = channel
    driver_info['ipmi_target_address'] = address
    cmd = _command_to_string(command_func(data))
    out = ipmi.send_raw(task, cmd)[0]
    if parse_func:
        return parse_func(out.split())


class IntelNMVendorPassthru(base.VendorInterface):
    """Intel Node Manager policies vendor interface."""

    def __init__(self):
        schemas_dir = os.path.dirname(__file__)
        for schema in SCHEMAS:
            filename = os.path.join(schemas_dir, schema + '.json')
            with open(filename, 'r') as sf:
                setattr(self, schema, json.load(sf))

    def get_properties(self):
        """Returns the properties."""

        return {}

    def validate(self, task, method, http_method, **kwargs):
        """Validates the vendor method's parameters."""

        try:
            if method in ('get_nm_policy', 'remove_nm_policy',
                          'get_nm_policy_suspend', 'remove_nm_policy_suspend'):
                jsonschema.validate(kwargs, self.main_ids_schema)

            elif method == 'control_nm_policy':
                jsonschema.validate(kwargs, self.control_schema)
                no_domain = _('Missing "domain_id"')
                no_policy = _('Missing "policy_id"')
                if kwargs['scope'] == 'domain' and not kwargs.get('domain_id'):
                    raise exception.MissingParameterValue(no_domain)
                if kwargs['scope'] == 'policy':
                    if not kwargs.get('domain_id'):
                        raise exception.MissingParameterValue(no_domain)
                    if not kwargs.get('policy_id'):
                        raise exception.MissingParameterValue(no_policy)

            elif method == 'set_nm_policy':
                jsonschema.validate(kwargs, self.policy_schema)
                if kwargs['policy_trigger'] == 'boot':
                    if not isinstance(kwargs['target_limit'], dict):
                        raise exception.InvalidParameterValue(_('Invalid boot '
                                                                'policy'))

            elif method == 'set_nm_policy_suspend':
                jsonschema.validate(kwargs, self.suspend_schema)

            elif method == 'get_nm_capabilities':
                jsonschema.validate(kwargs, self.get_cap_schema)

        except json_schema_exc.ValidationError as e:
            raise exception.InvalidParameterValue(_('Input data validation '
                                                    'error: %s') % e)

    @base.passthru(['PUT'])
    def control_nm_policy(self, task, **kwargs):
        """Enable or disable Intel NM policy control."""

        _execute_nm_command(task, kwargs, nm_commands.control_policies)

    @base.passthru(['PUT'])
    def set_nm_policy(self, task, **kwargs):
        """Set Intel NM policy."""

        _execute_nm_command(task, kwargs, nm_commands.set_policy)

    @base.passthru(['GET'], async=False)
    def get_nm_policy(self, task, **kwargs):
        """Get Intel NM policy."""

        return _execute_nm_command(task, kwargs, nm_commands.get_policy,
                                   nm_commands.parse_policy)

    @base.passthru(['DELETE'])
    def remove_nm_policy(self, task, **kwargs):
        """Remove Intel NM policy."""

        _execute_nm_command(task, kwargs, nm_commands.remove_policy)

    @base.passthru(['PUT'])
    def set_nm_policy_suspend(self, task, **kwargs):
        """Set Intel NM policy suspend periods."""

        _execute_nm_command(task, kwargs, nm_commands.set_policy_suspend)

    @base.passthru(['GET'], async=False)
    def get_nm_policy_suspend(self, task, **kwargs):
        """Get Intel NM policy suspend periods."""

        return _execute_nm_command(task, kwargs,
                                   nm_commands.get_policy_suspend,
                                   nm_commands.parse_policy_suspend)

    @base.passthru(['DELETE'])
    def remove_nm_policy_suspend(self, task, **kwargs):
        """Remove Intel NM policy suspend periods."""

        _execute_nm_command(task, kwargs, nm_commands.remove_policy_suspend)

    @base.passthru(['GET'], async=False)
    def get_nm_capabilities(self, task, **kwargs):
        """Get Intel NM capabilities."""

        return _execute_nm_command(task, kwargs, nm_commands.get_capabilities,
                                   nm_commands.parse_capabilities)

    @base.passthru(['GET'], async=False)
    def get_nm_version(self, task, **kwargs):
        """Get Intel NM version."""

        return _execute_nm_command(task, kwargs, nm_commands.get_version,
                                   nm_commands.parse_version)
