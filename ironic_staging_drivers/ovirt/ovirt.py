# Copyright 2017 Red Hat, Inc.
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
Ironic oVirt power manager and management interface.

Provides basic power control and management of virtual machines
via oVirt sdk API.

For use in dev and test environments.
"""

from ironic.common import boot_devices
from ironic.common import exception
from ironic.common.i18n import _
from ironic.common import states
from ironic.conductor import task_manager
from ironic.drivers import base
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils

from ironic_staging_drivers.common import exception as staging_exception

ovirtsdk = importutils.try_import('ovirtsdk4')
if ovirtsdk:
    import ovirtsdk4 as sdk
    import ovirtsdk4.types as otypes

IRONIC_TO_OVIRT_DEVICE_MAPPING = {
    boot_devices.PXE: 'network',
    boot_devices.DISK: 'hd',
    boot_devices.CDROM: 'cdrom',
}
OVIRT_TO_IRONIC_DEVICE_MAPPING = {v: k for k, v in
                                  IRONIC_TO_OVIRT_DEVICE_MAPPING.items()}

OVIRT_TO_IRONIC_POWER_MAPPING = {
    'down': states.POWER_OFF,
    'error': states.ERROR,
    'image_locked': states.POWER_OFF,
    'migrating': states.POWER_ON,
    'not_responding': states.ERROR,
    'paused': states.ERROR,
    'powering_down': states.POWER_OFF,
    'powering_up': states.POWER_ON,
    'reboot_in_progress': states.POWER_ON,
    'wait_for_launch': states.POWER_ON,
    'up': states.POWER_ON
}

opts = [
    cfg.StrOpt('address',
               default='127.0.0.1',
               help='oVirt address'),
    cfg.StrOpt('username',
               default='admin@internal',
               help='oVirt username'),
    cfg.StrOpt('password',
               help='oVirt password'),
    cfg.StrOpt('insecure',
               default=False,
               help='Skips verification of the oVirt host certificate'),
    cfg.StrOpt('ca_file',
               help='oVirt path to a CA file'),
]
CONF = cfg.CONF
CONF.register_opts(opts, group='ovirt')

LOG = logging.getLogger(__name__)

PROPERTIES = {
    'ovirt_address': _("Address of the oVirt Manager"),
    'ovirt_username': _("oVirt username"),
    'ovirt_password': _("oVirt password"),
    'ovirt_insecure': _("Skips oVirt host certificate's verification"),
    'ovirt_ca_file': _("oVirt path to a CA file"),
    'ovirt_vm_name': _("Name of the VM in oVirt. Required."),
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
    conf_info = {attr: getattr(CONF.ovirt, attr) for attr in CONF.ovirt}
    node_info = node.driver_info or {}
    driver_info = {}
    for prop in PROPERTIES:
        node_value = node_info.get(prop)
        conf_value = conf_info.get(prop.replace('ovirt_', ''))
        value = node_value if node_value is not None else conf_value
        if value is None and prop not in ['ovirt_ca_file', 'ovirt_insecure']:
            msg = _("%s is not set in either the configuration or "
                    "in the node's driver_info") % prop
            raise exception.MissingParameterValue(msg)
        else:
            driver_info[prop] = value
    insecure = driver_info['ovirt_insecure']
    ovirt_ca_file = driver_info['ovirt_ca_file']
    if not insecure and ovirt_ca_file is None:
            msg = _("Missing ovirt_ca_file in the node's driver_info")
            raise exception.MissingParameterValue(msg)
    return driver_info


def _getvm(driver_info):
    address = driver_info['ovirt_address']
    username = driver_info['ovirt_username']
    password = driver_info['ovirt_password']
    insecure = driver_info['ovirt_insecure']
    ca_file = driver_info['ovirt_ca_file']
    name = driver_info['ovirt_vm_name'].encode('ascii', 'ignore')
    url = "https://%s/ovirt-engine/api" % address
    try:
        # pycurl.Curl.setopt doesn't support unicode stings
        # convert them to a acsii str
        url = url.encode('ascii', 'strict')
    except UnicodeEncodeError:
        # url contains unicode characters that can't be converted, attempt to
        # use it, if we have a version of pycurl that rejects it then a
        # sdk.Error will be thrown below
        pass

    try:
        connection = sdk.Connection(url=url, username=username,
                                    password=password, insecure=insecure,
                                    ca_file=ca_file)
        vms_service = connection.system_service().vms_service()
        vmsearch = vms_service.list(search='name=%s' % name)
    except sdk.Error as e:
        LOG.error("Could not fetch information about VM vm %(name)s, "
                  "got error: %(error)s", {'name': name, 'error': e})
        raise staging_exception.OVirtError(err=e)
    if vmsearch:
        return vms_service.vm_service(vmsearch[0].id)
    else:
        raise staging_exception.OVirtError(_("VM with name "
                                             "%s was not found") % name)


class OVirtPower(base.PowerInterface):

    def get_properties(self):
        return PROPERTIES

    def validate(self, task):
        """Check if node.driver_info contains ovirt_vm_name.

        :param task: a TaskManager instance.
        :raises: MissingParameterValue, if some of the required parameters are
            missing in the node's driver_info.
        :raises: InvalidParameterValue, if some of the parameters have invalid
            values in the node's driver_info.
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
        vm_name = driver_info['ovirt_vm_name']
        vm = _getvm(driver_info)
        status = vm.get().status.value
        if status not in OVIRT_TO_IRONIC_POWER_MAPPING:
            msg = ("oVirt returned unknown state for node %(node)s "
                   "and vm %(vm)s")
            LOG.error(msg, {'node': task.node.uuid, 'vm': vm_name})
            return states.ERROR
        else:
            return OVIRT_TO_IRONIC_POWER_MAPPING[status]

    @task_manager.require_exclusive_lock
    def set_power_state(self, task, target_state, timeout=None):
        """Turn the current power state on or off.

        :param task: a TaskManager instance.
        :param target_state: The desired power state POWER_ON, POWER_OFF or
            REBOOT from :mod:`ironic.common.states`.
        :raises: MissingParameterValue, if some required parameter(s) are
            missing in the node's driver_info.
        :raises: InvalidParameterValue, if some parameter(s) have invalid
            value(s) in the node's driver_info OR if an invalid power state
            was specified.
        """
        driver_info = _parse_driver_info(task.node)
        vm_name = driver_info['ovirt_vm_name']
        vm = _getvm(driver_info)
        try:
            if target_state == states.POWER_OFF:
                vm.stop()
            elif target_state == states.POWER_ON:
                vm.start()
            elif target_state == states.REBOOT:
                status = vm.get().status.value
                if status == 'down':
                    vm.start()
                else:
                    vm.reboot()
            else:
                msg = _("'set_power_state' called with invalid power "
                        "state '%s'") % target_state
                raise exception.InvalidParameterValue(msg)
        except sdk.Error as e:
            LOG.error("Could not change status of VM vm %(name)s "
                      "got error: %(error)s", {'name': vm_name, 'error': e})
            raise staging_exception.OVirtError(err=e)

    @task_manager.require_exclusive_lock
    def reboot(self, task, timeout=None):
        """Reboot the node.

        :param task: a TaskManager instance.
        :raises: MissingParameterValue, if some required parameter(s) are
            missing in the node's driver_info.
        :raises: InvalidParameterValue, if some parameter(s) have invalid
            value(s) in the node's driver_info.
        :raises: ovirtsdk4.Error, if error encountered from
            oVirt operation.
        """
        self.set_power_state(task, states.REBOOT, timeout=timeout)


class OVirtManagement(base.ManagementInterface):

    def get_properties(self):
        return PROPERTIES

    def validate(self, task):
        """Check that 'driver_info' contains ovirt_vm_name.

        Validates whether the 'driver_info' property of the supplied
        task's node contains the required credentials information.

        :param task: a task from TaskManager.
        :raises: MissingParameterValue, if some required parameter(s) are
            missing in the node's driver_info.
        :raises: InvalidParameterValue, if some parameter(s) have invalid
            value(s) in the node's driver_info.
        """
        _parse_driver_info(task.node)

    def get_supported_boot_devices(self, task):
        """Get a list of the supported boot devices.

        :returns: A list with the supported boot devices defined
                  in :mod:`ironic.common.boot_devices`.
        """
        return sorted(list(IRONIC_TO_OVIRT_DEVICE_MAPPING))

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
        :raises: OVirtError, if error encountered from
            oVirt operation.
        """
        driver_info = _parse_driver_info(task.node)
        vm = _getvm(driver_info)
        boot_dev = vm.os.boot[0].get_dev()
        persistent = True
        ironic_boot_dev = OVIRT_TO_IRONIC_DEVICE_MAPPING.get(boot_dev)
        if not ironic_boot_dev:
            persistent = False
            msg = _("oVirt returned unknown boot device '%(device)s' "
                    "for node %(node)s")
            LOG.error(msg, {'device': boot_dev, 'node': task.node.uuid})
            raise staging_exception.OVirtError(msg.format(device=boot_dev,
                                                          node=task.node.uuid))

        return {'boot_device': ironic_boot_dev, 'persistent': persistent}

    @task_manager.require_exclusive_lock
    def set_boot_device(self, task, device, persistent=False):
        """Set the boot device for a node.

        :param task: a task from TaskManager.
        :param device: ironic.common.boot_devices
        :param persistent: This argument is ignored.
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

        driver_info = _parse_driver_info(task.node)
        vm = _getvm(driver_info)
        try:
            boot = otypes.Boot(devices=[otypes.BootDevice(boot_dev)])
            bootos = otypes.OperatingSystem(boot=boot)
            vm.update(otypes.Vm(os=bootos))
        except sdk.Error as e:
            LOG.error("Setting boot device failed for node %(node_id)s "
                      "with error: %(error)s",
                      {'node_id': task.node.uuid, 'error': e})
            raise staging_exception.OVirtError(err=e)

    def get_sensors_data(self, task):
        """Get sensors data.

        :param task: a TaskManager instance.
        :raises: FailedToGetSensorData when getting the sensor data fails.
        :raises: FailedToParseSensorData when parsing sensor data fails.
        :returns: returns a consistent format dict of sensor data grouped by
        sensor type, which can be processed by Ceilometer.
        """
        raise NotImplementedError()
