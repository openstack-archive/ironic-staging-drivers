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

"""List entrypoint names registered by package, possibly per type"""

import argparse
import sys

import pkg_resources


def filter_ep_names(eps, ep_type, skip=None):
    if not skip:
        skip = []
    return filter(lambda e: all([s not in e for s in skip]),
                  list(eps.get(ep_type, {}).keys()))


def list_package_entrypoints(package_name, ep_types=None, skip=None):
    eps = pkg_resources.get_entry_map(
        pkg_resources.get_distribution(package_name))

    if not ep_types:
        ep_types = eps.keys()
    if not skip:
        skip = []

    if len(ep_types) == 1:
        names = filter_ep_names(eps, ep_types[0], skip=skip)
        if names:
            print(','.join(names))
    else:
        for ep_t in ep_types:
            print("%s=%s" % (ep_t,
                             ','.join(filter_ep_names(eps, ep_t, skip=skip))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', metavar='PKG_NAME', type=str,
                        help='Name of Python package')
    parser.add_argument('-t', '--entrypoint_type', dest='ep_types',
                        action='append', default=[],
                        help='type of entrypoints to find, all if not set')
    parser.add_argument('-s', '--skip-names', dest='ep_skip',
                        action='append', default=[],
                        help='skip entrypoint names containing this substring')
    args = parser.parse_args()

    sys.exit(list_package_entrypoints(args.package,
                                      ep_types=args.ep_types,
                                      skip=args.ep_skip))
