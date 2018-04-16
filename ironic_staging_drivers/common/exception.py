# Copyright 2016 Red Hat, Inc.
# All Rights Reserved.
#
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

from ironic.common import exception

from ironic_staging_drivers.common.i18n import _


class WOLOperationError(exception.IronicException):
    pass


class AMTConnectFailure(exception.IronicException):
    _msg_fmt = _("Failed to connect to AMT service. This could be caused "
                 "by the wrong amt_address or bad network environment.")


class AMTFailure(exception.IronicException):
    _msg_fmt = _("AMT call failed: %(cmd)s.")


class LibvirtError(exception.IronicException):
    message = _("Libvirt call failed: %(err)s.")


class InvalidIPMITimestamp(exception.IronicException):
    pass


class OVirtError(exception.IronicException):
    message = _("oVirt call failed: %(err)s.")
