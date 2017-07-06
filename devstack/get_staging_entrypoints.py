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

"""List entrypoints registered by ironic-staging-drivers, possibly per type"""

import sys

import pkg_resources


ARGS_MAP = {
    'driver': 'ironic.drivers',
    'hwtypes': 'ironic.hardware.types',
    'deploy': 'ironic.hardware.interfaces.deploy',
    'power': 'ironic.hardware.interfaces.power',
    'mgmt': 'ironic.hardware.interfaces.management',
    'vendor': 'ironic.hardware.interfaces.vendor'
}


def list_and_filter_ep_names(ep_type, eps):
    ep_names = list(eps.get(ARGS_MAP[ep_type], {}).keys())
    return ','.join(filter(lambda x: 'fake' not in x, ep_names))


def parse_staging_entrypoints():
    eps = pkg_resources.get_entry_map(
        pkg_resources.get_distribution('ironic-staging-drivers'))
    if len(sys.argv) > 1:
        ep_type = sys.argv[1]
        if ep_type not in ARGS_MAP:
            return "Ironic entry point type not known"
        print(list_and_filter_ep_names(ep_type, eps))
    else:
        for ep_type in ARGS_MAP:
            print("%s=%s" % (ep_type, list_and_filter_ep_names(ep_type, eps)))


if __name__ == '__main__':
    sys.exit(parse_staging_entrypoints())
