#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Standalone network interface. Useful for shared, flat networks, no nova.
"""

from neutronclient.common import exceptions as neutron_exceptions
from oslo_config import cfg
from oslo_log import log

from ironic.common import exception
from ironic.common.i18n import _
from ironic.common.i18n import _LI
from ironic.common.i18n import _LW
from ironic.common import neutron
from ironic.drivers import base
from ironic.drivers.modules.network import common


LOG = log.getLogger(__name__)

CONF = cfg.CONF


class StandaloneFlatNetwork(common.VIFPortIDMixin,
                            neutron.NeutronNetworkInterfaceMixin,
                            base.NetworkInterface):
    """Standalone flat network interface."""

    def __init__(self):
        failures = []
        cleaning_net = CONF.neutron.cleaning_network
        if not cleaning_net:
            failures.append('cleaning_network')

        provisioning_net = CONF.neutron.provisioning_network
        if not provisioning_net:
            failures.append('provisioning_network')

        if failures:
            raise exception.DriverLoadError(
                driver=self.__class__.__name__,
                reason=_('The following [neutron] group configuration '
                         'options are missing: {fails}').format(
                             fails=', '.join(failures)))

    def validate(self, task):
        """Validates the network interface.

        :param task: a TaskManager instance.
        :raises: InvalidParameterValue, if the network interface configuration
            is invalid.
        :raises: MissingParameterValue, if some parameters are missing.
        """
        self.get_cleaning_network_uuid()
        self.get_provisioning_network_uuid()

    def add_provisioning_network(self, task):
        """Add the provisioning network to a node.

        :param task: A TaskManager instance.
        :raises: NetworkError when failed to set binding:host_id.
        """
        LOG.debug("Creating network ports")
        node = task.node
        client = neutron.get_client()
        network_uuid = self.get_provisioning_network_uuid()
        for ironic_port in [p for p in task.ports if p.pxe_enabled]:
            neutron.rollback_ports(task, network_uuid)
            body = {
                'port': {
                    'network_id': self.get_provisioning_network_uuid(),
                    'admin_state_up': True,
                    'binding:vnic_type': 'baremetal',
                    'device_owner': 'baremetal:none',
                    'mac_address': ironic_port.address,
                }
            }
            client_id = ironic_port.extra.get('client-id')
            if client_id:
                client_id_opt = {'opt_name': 'client-id',
                                 'opt_value': client_id}
                extra_dhcp_opts = body['port'].get('extra_dhcp_opts', [])
                extra_dhcp_opts.append(client_id_opt)
                body['port']['extra_dhcp_opts'] = extra_dhcp_opts
            try:
                port = client.create_port(body)
            except neutron_exceptions.NeutronClientException as e:
                LOG.warning(_LW("Could not create neutron port for node's "
                                "%(node)s port %(ir-port)s on the neutron "
                                "network %(net)s. %(exc)s"),
                            {'net': network_uuid, 'node': node.uuid,
                             'ir-port': ironic_port.uuid, 'exc': e})
            extra = ironic_port.extra
            extra['vif_port_id'] = port['port']['id']
            ironic_port.extra = extra
            ironic_port.save()

    def remove_provisioning_network(self, task):
        """Remove the provisioning network from a node.

        :param task: A TaskManager instance.
        """
        pass

    def configure_tenant_networks(self, task):
        """Configure tenant networks for a node.

        :param task: A TaskManager instance.
        """
        LOG.debug("Setting ipv4_addresses to instance_info")
        node = task.node
        client = neutron.get_client()
        ipv4_addresses = []
        for ironic_port in [p for p in task.ports
                            if p.pxe_enabled and p.extra.get('vif_port_id')]:
            body = {
                'port': {
                    'extra_dhcp_opts': [],
                }
            }
            try:
                neutron_port = client.update_port(
                    ironic_port.extra['vif_port_id'], body)
            except neutron_exceptions.NeutronClientException as e:
                LOG.warning(_LW("Could not update neutron port for node's "
                                "%(node)s port %(ir-port)s %(exc)s. "),
                            {'node': node.uuid, 'ir-port': ironic_port.uuid,
                             'exc': e})
            ipv4_addresses.append(
                neutron_port['port']['fixed_ips'][0]['ip_address'])
        instance_info = node.instance_info
        instance_info['ipv4_addresses'] = ipv4_addresses
        node.instance_info = instance_info
        node.save()

    def unconfigure_tenant_networks(self, task):
        """Unconfigure tenant networks for a node.

        :param task: A TaskManager instance.
        """
        LOG.debug("Deleting network ports")
        macs = [p.address for p in task.ports if p.pxe_enabled]
        params = {
            'network_id': self.get_provisioning_network_uuid(),
            'mac_address': macs,
        }
        neutron.remove_neutron_ports(task, params)
        for port in task.ports:
            if 'vif_port_id' in port.extra:
                extra = port.extra
                del extra['vif_port_id']
                port.extra = extra
                port.save()

    def add_cleaning_network(self, task):
        """Add the cleaning network to a node.

        :param task: A TaskManager instance.
        :returns: a dictionary in the form {port.uuid: neutron_port['id']}.
        :raises: NetworkError, InvalidParameterValue.
        """
        # If we have left over ports from a previous cleaning, remove them
        neutron.rollback_ports(task, self.get_cleaning_network_uuid())
        LOG.info(_LI('Adding cleaning network to node %s'), task.node.uuid)
        vifs = neutron.add_ports_to_network(
            task, self.get_cleaning_network_uuid())
        for port in task.ports:
            if port.uuid in vifs:
                internal_info = port.internal_info
                internal_info['cleaning_vif_port_id'] = vifs[port.uuid]
                port.internal_info = internal_info
                port.save()
        return vifs

    def remove_cleaning_network(self, task):
        """Remove the cleaning network from a node.

        :param task: A TaskManager instance.
        :raises: NetworkError.
        """
        LOG.info(_LI('Removing ports from cleaning network for node %s'),
                 task.node.uuid)
        neutron.remove_ports_from_network(task,
                                          self.get_cleaning_network_uuid())
        for port in task.ports:
            if 'cleaning_vif_port_id' in port.internal_info:
                internal_info = port.internal_info
                del internal_info['cleaning_vif_port_id']
                port.internal_info = internal_info
                port.save()
