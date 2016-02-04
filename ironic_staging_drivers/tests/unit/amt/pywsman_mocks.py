# Copyright 2014 Hewlett-Packard Development Company, L.P.
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

"""This module detects whether third-party libraries, utilized by third-party
drivers, are present on the system. If they are not, it mocks them and tinkers
with sys.modules so that the drivers can be loaded by unit tests, and the unit
tests can continue to test the functionality of those drivers without the
respective external libraries' actually being present.

"""

import sys

import mock
from oslo_utils import importutils
import six

from ironic_staging_drivers.tests.unit.amt import pywsman_mocks_specs

# attempt to load the external 'pywsman' library, which is required by
# the optional amt module
pywsman = importutils.try_import('pywsman')
if not pywsman:
    pywsman = mock.MagicMock(spec_set=pywsman_mocks_specs.PYWSMAN_SPEC)
    sys.modules['pywsman'] = pywsman
    # Now that the external library has been mocked, if anything had already
    # loaded any of the drivers, reload them.
    if 'ironic_staging_drivers.amt' in sys.modules:
        six.moves.reload_module(sys.modules['ironic_staging_drivers.amt'])
