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

from ironic.drivers import base
from ironic.drivers.modules import iscsi_deploy
from ironic.drivers.modules import pxe

from ironic_staging_drivers.wol import wol


class PXEAndWakeOnLanDriver(base.BaseDriver):
    """PXE + WakeOnLan driver.

    This driver implements the `core` functionality, combining
    :class:`ironic.drivers.modules.wol.WakeOnLanPower` for power on
    :class:`ironic.drivers.modules.iscsi_deploy.ISCSIDeploy` for image
    deployment.  Implementations are in those respective classes;
    this class is merely the glue between them.
    """
    def __init__(self):
        self.power = wol.WakeOnLanPower()
        self.boot = pxe.PXEBoot()
        self.deploy = iscsi_deploy.ISCSIDeploy()
        self.vendor = iscsi_deploy.VendorPassthru()
