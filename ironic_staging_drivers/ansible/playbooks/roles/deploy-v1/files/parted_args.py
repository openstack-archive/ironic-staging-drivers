#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys


def _add_variables(variables, filename):
    params = ['%(key)s="%(val)s"' % {'key': key, 'val': val}
              for key, val in variables.items()]
    params_str = ' ' + ' '.join(params)
    with open(filename, 'a') as f:
        f.write(params_str)


def main():
    devices = {}
    device = sys.argv[1]
    root_mb = int(sys.argv[2])
    swap_mb = int(sys.argv[3])
    ephemeral_mb = int(sys.argv[4])
    configdrive_mb = (int(sys.argv[5]) / (1024 * 1024)) + 1
    inventory = sys.argv[6]

    parted_arg = '-a optimal -s %s -- unit MiB mklabel msdos' % device
    start, number = 1, 1
    add_command = ' mkpart primary %(start)s %(end)s'

    if ephemeral_mb != 0:
        end = start + ephemeral_mb
        parted_arg += add_command % {'start': start, 'end': end}
        devices['ephemeral_part'] = device + str(number)
        start = end
        number += 1

    if swap_mb != 0:
        end = start + swap_mb
        parted_arg += (' mkpart primary linux-swap %(start)s %(end)s' %
                       {'start': start, 'end': end})
        devices['swap_part'] = device + str(number)
        start = end
        number += 1

    if configdrive_mb != 0:
        end = start + configdrive_mb
        parted_arg += add_command % {'start': start, 'end': end}
        devices['configdrive_part'] = device + str(number)
        start = end
        number += 1

    end = start + root_mb
    parted_arg += add_command % {'start': start, 'end': end}
    parted_arg += ' set %s boot on' % number
    devices['root_part'] = device + str(number)

    _add_variables(devices, inventory)
    sys.stdout.write(parted_arg)


if __name__ == '__main__':
    sys.exit(main())
