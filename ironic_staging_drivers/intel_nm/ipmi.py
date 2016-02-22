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

from ironic.common import exception
from ironic.conductor import task_manager
from ironic.drivers.modules import ipmitool
from oslo_concurrency import processutils
from oslo_log import log

from ironic_staging_drivers.common.i18n import _LE

LOG = log.getLogger(__name__)

# NOTE(yuriyz): there are extended version of send_raw() from Ironic ipmitool
# driver and dump_sdr(). These functions depends on ipmitool driver internals,
# and should be moved to Ironic for use from out-of-tree drivers.


@task_manager.require_exclusive_lock
def send_raw(task, raw_bytes):
    """Send raw bytes to the BMC. Bytes should be a string of bytes.

    :param task: a TaskManager instance.
    :param raw_bytes: a string of raw bytes to send, e.g. '0x00 0x01'
    :returns: a tuple with stdout and stderr.
    :raises: IPMIFailure on an error from ipmitool.
    :raises: MissingParameterValue if a required parameter is missing.
    :raises: InvalidParameterValue when an invalid value is specified.

    """
    node_uuid = task.node.uuid
    LOG.debug('Sending node %(node)s raw bytes %(bytes)s',
              {'bytes': raw_bytes, 'node': node_uuid})
    driver_info = ipmitool._parse_driver_info(task.node)
    cmd = 'raw %s' % raw_bytes

    try:
        out, err = ipmitool._exec_ipmitool(driver_info, cmd)
        LOG.debug('send raw bytes returned stdout: %(stdout)s, stderr:'
                  ' %(stderr)s', {'stdout': out, 'stderr': err})
    except (exception.PasswordFileFailedToCreate,
            processutils.ProcessExecutionError) as e:
        LOG.exception(_LE('IPMI "raw bytes" failed for node %(node_id)s '
                      'with error: %(error)s.'),
                      {'node_id': node_uuid, 'error': e})
        raise exception.IPMIFailure(cmd=cmd)

    return out, err


def dump_sdr(task, filename):
    """Dump SDR data to a file.

    :param task: a TaskManager instance.
    :param filename: File name for dump.
    :raises: IPMIFailure on an error from ipmitool.
    :raises: MissingParameterValue if a required parameter is missing.
    :raises: InvalidParameterValue when an invalid value is specified.

    """
    node_uuid = task.node.uuid
    LOG.debug('Dump SDR data for node %(node)s to file %(name)s',
              {'name': filename, 'node': node_uuid})
    driver_info = ipmitool._parse_driver_info(task.node)
    cmd = 'sdr dump %s' % filename

    try:
        out, err = ipmitool._exec_ipmitool(driver_info, cmd)
        LOG.debug('dump SDR returned stdout: %(stdout)s, stderr:'
                  ' %(stderr)s', {'stdout': out, 'stderr': err})
    except (exception.PasswordFileFailedToCreate,
            processutils.ProcessExecutionError) as e:
        LOG.exception(_LE('IPMI "sdr dump" failed for node %(node_id)s '
                      'with error: %(error)s.'),
                      {'node_id': node_uuid, 'error': e})
        raise exception.IPMIFailure(cmd=cmd)
