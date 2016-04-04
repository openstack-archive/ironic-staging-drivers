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
Ironic Ovirt power manager and management interface.

Provides basic power control and management of virtual machines
via Ovirt sdk API.

For use in dev and test environments.
"""

from oslo_config import cfg
from oslo_utils import importutils

from ironic.common import boot_devices
from ironic.common import exception
from ironic.common.i18n import _
from ironic.common.i18n import _LE
from ironic.common import states
from ironic.conductor import task_manager
from ironic.drivers import base
from ironic.openstack.common import log as logging

ovirtsdk = importutils.try_import('ovirtsdk')
if ovirtsdk:
    from ovirtsdk.api import API
    from ovirtsdk.xml import params

IRONIC_TO_OVIRT_DEVICE_MAPPING = {
    boot_devices.PXE: 'network',
    boot_devices.DISK: 'hd',
    boot_devices.CDROM: 'cdrom',
}
OVIRT_TO_IRONIC_DEVICE_MAPPING = {v: k for k, v in
                                  IRONIC_TO_OVIRT_DEVICE_MAPPING.items()}

OVIRT_TO_IRONIC_POWER_MAPPING = {
    'down': states.POWER_OFF,
    'powering_up': states.POWER_ON,
    'wait_for_launch': states.POWER_ON,
    'up': states.POWER_ON,
    'error': states.ERROR
}

opts = [
    cfg.StrOpt('host',
               default='127.0.0.1',
               help='Ovirt host'),
    cfg.IntOpt('port',
               default=443,
               help='Ovirt port'),
    cfg.StrOpt('user',
               default='admin@internal',
               help='Ovirt username'),
    cfg.StrOpt('password',
               default='prout',
               help='Ovirt password'),
]
CONF = cfg.CONF
CONF.register_opts(opts, group='ovirt')

LOG = logging.getLogger(__name__)

PROPERTIES = {
    'vmname': _("Name of the VM in Ovirt. Required."),
}


def _parse_driver_info(node):
    """Gets the driver specific node driver info.

    This method validates whether the 'driver_info' property of the
    supplied node contains the required information for this driver.

    :param node: an Ironic Node object.
    :returns: a dict containing information from driver_info (or where
        applicable, config values).
    :raises: MissingParameterValue, if some required parameter(s) are missing
        in the node's driver_info.
    :raises: InvalidParameterValue, if some parameter(s) have invalid value(s)
        in the node's driver_info.
    """
    info = node.driver_info
    d_info = {}
    d_info['host'] = CONF.ovirt.host
    d_info['user'] = CONF.ovirt.user
    d_info['password'] = CONF.ovirt.password
    d_info['vmname'] = info.get('vmname')

    try:
        d_info['port'] = int(d_info.get('port', CONF.ovirt.port))
    except ValueError:
        msg = _("'ovirt port' is not an integer.")
        raise exception.InvalidParameterValue(msg)

    return d_info


def _getvm(driver_info):
    host, port, user, password = driver_info['host'], driver_info[
        'port'], driver_info['user'], driver_info['password']
    name = driver_info['vmname']
    url = "https://%s:%s/api" % (host, port)
    api = API(url=url, username=user, password=password, insecure=True)
    vm = api.vms.get(name=name)
    return vm


class OvirtPower(base.PowerInterface):

    def get_properties(self):
        return PROPERTIES

    def validate(self, task):
        """Check if node.driver_info contains the required credentials.

        :param task: a TaskManager instance.
        :raises: MissingParameterValue, if some required parameter(s) are
            missing in the node's driver_info.
        :raises: InvalidParameterValue, if some parameter(s) have invalid
            value(s) in the node's driver_info.
        """
        _parse_driver_info(task.node)

    def get_power_state(self, task):
        """Gets the current power state.

        :param task: a TaskManager instance.
        :returns: one of :mod:`ironic.common.states`
        :raises: MissingParameterValue, if some required parameter(s) are
            missing in the node's driver_info.
        :raises: InvalidParameterValue, if some parameter(s) have invalid
            value(s) in the node's driver_info.
        """
        driver_info = _parse_driver_info(task.node)
        vm = _getvm(driver_info)
        if vm is None:
            power_status = 'NotFound'
        else:
            power_status = vm.status.state
        try:
            return OVIRT_TO_IRONIC_POWER_MAPPING[power_status]
        except KeyError:
            msg = _LE("Ovirt returned unknown state '%(state)s' for "
                      "node %(node)s")
            LOG.error(msg, {'state': power_status, 'node': task.node.uuid})
            return states.ERROR

    @task_manager.require_exclusive_lock
    def set_power_state(self, task, target_state):
        """Turn the current power state on or off.

        :param task: a TaskManager instance.
        :param target_state: The desired power state POWER_ON,POWER_OFF or
            REBOOT from :mod:`ironic.common.states`.
        :raises: MissingParameterValue, if some required parameter(s) are
            missing in the node's driver_info.
        :raises: InvalidParameterValue, if some parameter(s) have invalid
            value(s) in the node's driver_info OR if an invalid power state
            was specified.
        """
        if target_state == states.POWER_OFF:
            driver_info = _parse_driver_info(task.node)
            vm = _getvm(driver_info)
            vm.stop()
        elif target_state == states.POWER_ON:
            driver_info = _parse_driver_info(task.node)
            vm = _getvm(driver_info)
            vm.start()
        elif target_state == states.REBOOT:
            self.reboot(task)
        else:
            msg = _("'set_power_state' called with invalid power "
                    "state '%s'") % target_state
            raise exception.InvalidParameterValue(msg)

    @task_manager.require_exclusive_lock
    def reboot(self, task):
        """Reboot the node.

        :param task: a TaskManager instance.
        :raises: MissingParameterValue, if some required parameter(s) are
            missing in the node's driver_info.
        :raises: InvalidParameterValue, if some parameter(s) have invalid
            value(s) in the node's driver_info.
        :raises: VirtualBoxOperationFailed, if error encountered from
            VirtualBox operation.
        """
        driver_info = _parse_driver_info(task.node)
        vm = _getvm(driver_info)
        vm.stop()
        vm.start()


class OvirtManagement(base.ManagementInterface):

    def get_properties(self):
        return PROPERTIES

    def validate(self, task):
        """Check that 'driver_info' contains required credentials.

        Validates whether the 'driver_info' property of the supplied
        task's node contains the required credentials information.

        :param task: a task from TaskManager.
        :raises: MissingParameterValue, if some required parameter(s) are
            missing in the node's driver_info.
        :raises: InvalidParameterValue, if some parameter(s) have invalid
            value(s) in the node's driver_info.
        """
        _parse_driver_info(task.node)

    def get_supported_boot_devices(self):
        """Get a list of the supported boot devices.

        :returns: A list with the supported boot devices defined
                  in :mod:`ironic.common.boot_devices`.
        """
        return list(IRONIC_TO_OVIRT_DEVICE_MAPPING.keys())

    def get_boot_device(self, task):
        """Get the current boot device for a node.

        :param task: a task from TaskManager.
        :returns: a dictionary containing:
            'boot_device': one of the ironic.common.boot_devices or None
            'persistent': True if boot device is persistent, False otherwise
        :raises: MissingParameterValue, if some required parameter(s) are
            missing in the node's driver_info.
        :raises: InvalidParameterValue, if some parameter(s) have invalid
            value(s) in the node's driver_info.
        :raises: VirtualBoxOperationFailed, if error encountered from
            VirtualBox operation.
        """
        driver_info = _parse_driver_info(task.node)
        vm = _getvm(driver_info)
        boot_dev = vm.os.boot[0].get_dev()
        persistent = True
        ironic_boot_dev = OVIRT_TO_IRONIC_DEVICE_MAPPING.get(boot_dev,
                                                             None)
        if not ironic_boot_dev:
            persistent = None
            msg = _LE("Ovirt returned unknown boot device '%(device)s' "
                      "for node %(node)s")
            LOG.error(msg, {'device': boot_dev, 'node': task.node.uuid})

        return {'boot_device': ironic_boot_dev, 'persistent': persistent}

    @task_manager.require_exclusive_lock
    def set_boot_device(self, task, device, persistent=False):
        """Set the boot device for a node.

        :param task: a task from TaskManager.
        :param device: ironic.common.boot_devices
        :param persistent: This argument is ignored as VirtualBox support only
            persistent boot devices.
        :raises: MissingParameterValue, if some required parameter(s) are
            missing in the node's driver_info.
        :raises: InvalidParameterValue, if some parameter(s) have invalid
            value(s) in the node's driver_info.
        """
        try:
            boot_dev = IRONIC_TO_OVIRT_DEVICE_MAPPING[device]
        except KeyError:
            raise exception.InvalidParameterValue(_(
                "Invalid boot device %s specified.") % device)

        try:
            driver_info = _parse_driver_info(task.node)
            vm = _getvm(driver_info)
            boot = [params.Boot(dev=boot_dev), params.Boot(dev=None)]
            vm.os.boot = boot
            vm.update()
        except Exception e:
            LOG.error(_LE("'set_boot_device' failed for node %(node_id)s "
                          "with error: %(error)s"),
                      {'node_id': task.node.uuid, 'error': e})

    def get_sensors_data(self, task):
        """Get sensors data.

        :param task: a TaskManager instance.
        :raises: FailedToGetSensorData when getting the sensor data fails.
        :raises: FailedToParseSensorData when parsing sensor data fails.
        :returns: returns a consistent format dict of sensor data grouped by
        sensor type, which can be processed by Ceilometer.
        """
        raise NotImplementedError()
