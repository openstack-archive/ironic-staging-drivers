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

from ironic.common import exception as ironic_exception
from ironic.drivers import base
from ironic.drivers.modules import fake
from oslo_utils import importutils

from ironic_staging_drivers.amt import management as amt_mgmt
from ironic_staging_drivers.amt import power as amt_power
from ironic_staging_drivers.wol import power as wol_power


class FakeWakeOnLanFakeDriver(base.BaseDriver):
    """Fake Wake-On-Lan driver."""

    def __init__(self):
        self.boot = fake.FakeBoot()
        self.power = wol_power.WakeOnLanPower()
        self.deploy = fake.FakeDeploy()


class FakeAMTFakeDriver(base.BaseDriver):
    """Fake AMT driver."""

    def __init__(self):
        if not importutils.try_import('pywsman'):
            raise ironic_exception.DriverLoadError(
                driver=self.__class__.__name__,
                reason=_("Unable to import pywsman library"))
        self.power = amt_power.AMTPower()
        self.deploy = fake.FakeDeploy()
        self.management = amt_mgmt.AMTManagement()
