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

from __future__ import print_function

import argparse
import sys

import pkg_resources


def filter_ep_names(eps, ep_type, skips=None, filters=None):
    if not skips:
        skips = []
    if not filters:
        filters = []

    def filter_func(name):
        return (all([s not in name for s in skips]) and
                all([f in name for f in filters]))

    return filter(filter_func, list(eps.get(ep_type, {}).keys()))


def list_package_entrypoints(package_name, ep_types=None, skips=None,
                             filters=None):
    eps = pkg_resources.get_entry_map(
        pkg_resources.get_distribution(package_name))

    if not ep_types:
        ep_types = eps.keys()
    if not skips:
        skips = []
    if not filters:
        filters = []

    if len(ep_types) == 1:
        names = filter_ep_names(eps, ep_types[0], skips=skips,
                                filters=filters)
        if names:
            print(','.join(names))
    else:
        for ep_t in ep_types:
            print("%s=%s" % (ep_t,
                             ','.join(filter_ep_names(eps, ep_t,
                                                      skips=skips,
                                                      filters=filters))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', metavar='PACKAGE_NAME', type=str,
                        help='Name of Python package')
    parser.add_argument('-t', '--entrypoint-types', dest='ep_types', nargs='+',
                        metavar="ENTRYPOINT_TYPE",
                        help='type of entrypoints to find, all if not set')
    parser.add_argument('-s', '--skip-names', dest='ep_skips', nargs='+',
                        metavar='SKIP_ENTRYPOINT',
                        help='do not output entrypoint names containing any '
                        'of these substrings, ignored if not set')
    parser.add_argument('-f', '--filter-names', dest='ep_filters', nargs='+',
                        metavar='FILTER_ENTRYPOINT',
                        help='only output entrypoint names containing all '
                        'these substrings, ignored if not set')
    args = parser.parse_args()

    sys.exit(list_package_entrypoints(args.package,
                                      ep_types=args.ep_types,
                                      skips=args.ep_skips,
                                      filters=args.ep_filters))
