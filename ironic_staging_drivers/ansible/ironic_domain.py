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

"""Managing of ironic-specific keystone trusts."""

from ironic.common.i18n import _
from ironic.common import keystone
from ironic.conf import CONF
from keystoneauth1 import identity
from keystoneauth1 import loading
from keystoneclient.v3 import client as k3client
from oslo_config import cfg
from oslo_log import log


LOG = log.getLogger(__name__)

trustee_opts = [
    cfg.StrOpt('ironic_domain_admin_username',
               help=_('Name of a service user to be trusted')),
    cfg.StrOpt('ironic_domain_admin_password',
               help=_('Password for trustee user')),
    cfg.StrOpt('ironic_domain_id',
               help=_('Domain ID of the trustee.')),
    cfg.StrOpt('auth_url',
               help=_('Versioned IdentityV3 service URL.')),
    # NOTE(pas-ha) could go with a crypt key instead of fixed password,
    # generate random string for password, and store in encrypted in the
    # driver_internal_info
    cfg.StrOpt('trustee_password',
               help=_('Password to set for temporary trustee user.')),

]

IRONIC_DOMAIN_GROUP = 'ironic_domain'

CONF.register_opts(trustee_opts, group=IRONIC_DOMAIN_GROUP)
loading.register_session_conf_options(CONF, IRONIC_DOMAIN_GROUP)
loading.register_adapter_conf_options(CONF, IRONIC_DOMAIN_GROUP)


def domain_admin_auth():
    return identity.V3Password(
        auth_url=CONF.ironic_domain.auth_url,
        username=CONF.ironic_domain.ironic_domain_admin_username,
        password=CONF.ironic_domain.ironic_domain_admin_password,
        domain_id=CONF.ironic_domain.ironic_domain_id,
        user_domain_id=CONF.ironic_domain.ironic_domain_id)


@keystone.ks_exceptions
def create_domain_user(node):
    auth = domain_admin_auth()
    client = k3client.Client(
        session=loading.load_session_from_conf_options(
            CONF, IRONIC_DOMAIN_GROUP, auth=auth))
    user = client.users.create(node.uuid,
                               password=CONF.ironic_domain.trustee_password,
                               domain=CONF.ironic_domain.ironic_domain_id)
    return user


@keystone.ks_exceptions
def delete_domain_user(task):
    di_info = task.node.driver_internal_info
    if 'trust_id' not in di_info:
        return
    di_info.pop('trust_id')
    task.node.driver_internal_info = di_info
    task.node.save()
    LOG.debug("Deleting trustee user for node %s", task.node.uuid)
    auth = domain_admin_auth()
    client = k3client.Client(
        session=loading.load_session_from_conf_options(
            CONF, IRONIC_DOMAIN_GROUP, auth=auth))
    user = client.users.list(domain=CONF.ironic_domain.ironic_domain_id,
                             name=task.node.uuid)[0]
    client.users.delete(user.id)


@keystone.ks_exceptions
def create_trust(task):
    user = create_domain_user(task.node)
    context = task.context
    # generating v3token auth from context
    trustor_auth = identity.Token(
        CONF.ironic_domain.auth_url,
        context.auth_token,
        project_id=context.project_id,
        project_domain_id=context.project_domain_id)
    client = k3client.Client(
        session=loading.load_session_from_conf_options(CONF,
                                                       IRONIC_DOMAIN_GROUP,
                                                       auth=trustor_auth))
    LOG.debug("Creating trust to download image for node %s", task.node.uuid)
    # TODO(pas-ha) add expiration == deploy timeout
    trust = client.trusts.create(user.id,
                                 context.user_id,
                                 project=context.project_id,
                                 role_names=context.roles,
                                 impersonate=True,
                                 remaining_uses=1)

    di_info = task.node.driver_internal_info
    di_info['trust_id'] = trust.id
    task.node.driver_internal_info = di_info
    task.node.save()


@keystone.ks_exceptions
def get_trusted_token(task):
    trust_id = task.node.driver_internal_info['trust_id']
    trusted_auth = identity.V3Password(
        auth_url=CONF.ironic_domain.auth_url,
        user_domain_id=CONF.ironic_domain.ironic_domain_id,
        trust_id=trust_id,
        password=CONF.ironic_domain.trustee_password,
        username=task.node.uuid
    )
    session = loading.load_session_from_conf_options(CONF, IRONIC_DOMAIN_GROUP)
    trusted_token = session.get_token(auth=trusted_auth)
    return trusted_token
