#!/usr/bin/python
# -*- coding: utf-8 -*-
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

# NOTE(pas-ha) might not need it when Ansible PullRequest#2971 is accepted

import itertools
try:
    import json
except ImportError:
    import simplejson as json

PARTITION_TYPES = ('primary', 'logical', 'extended')
SUPPORTED_UNITS = {'%', 'MiB'}
SUPPORTED_ALIGN = {'optimal', 'minimal', 'cylinder', 'none'}

DOCUMENTATION = """
---
module: ironic_parted
short_description: Create disk partition tables and partitions
description: uses GNU parted utility
author: Pavlo Shchelokovskyy @pshchelo
version_added: null
notes:
- IS NOT IDEMPOTENT! partitions and table (if requested) are created anyway
- does not support all the partition labels parted supports, only msdos and gpt
- does not support units other than % and MiB
- check mode is supported by returning emulated list of created block devices
- makes no validation re if given partitions will actually fit the device
- makes some extra validations for appropriate partition types for msdos label
requirements:
- Python >= 2.4 (itertools.groupby available) on the managed node
- 'simplejson' for Python < 2.6
- 'parted' utility installed on the managed node
- 'lsblk' available on managed node
- 'udevadm' available on managed node
options:
    device:
        description: device to pass to parted
        required: true
        default: null
        choices: []
        aliases: []
        version_added: null
    label:
        description: |
            type of a partition table to create;
            to use an existing partition table, omit it or pass null YAML value
        required: false
        default: none
        choices: [null, msdos, gpt]
        aliases: []
        version_added: null
    dry_run:
        description: |
            if actually to write changes to disk.
            If no, simulated partitions will be reported.
        required: false
        default: no
        choices: [yes, no]
        aliases: []
        version_added: null
    partitions:
        description:|
            list of partitions. each entry is a dictionary in the form
            - size: <int>, required, must be positive
              type: [primary, extended, logical], default is primary
              format: a format to pass to parted;
                      does not actually creates filesystems, only sets
                      partition ID
              name: <str> (optional) name of the partition;
                    only supported for gpt partitions;
                    if not set will be reported as 'partN'
              unit: 'MiB' or '%' are currently supported,
                     must be the same for all partitions. default is '%'
              align: one of 'optimal', 'cylinder', 'minimal' or 'none';
                     the default is 'optimal'
              flags: <dict> of <flag>: <bool> to (un)set partition flags
        required: false
        default: null
        choices: []
        aliases: []
        version_added: null
"""

EXAMPLES = """
---
"""

RETURNS = """
---
{"created": {
    "<name-as-provided-to-module>": "<device-handle-without-leading-dev>"
    }
}
"""


def parse_sizes(module, partitions):
    start = 0 if partitions[0]['unit'] == '%' else 1
    sizes = {}
    for p in partitions:
        size = p.get('size')
        if not size:
            module.fail_json(msg="Partition size must be provided")
        try:
            p['size'] = int(size)
        except ValueError:
            module.fail_json(msg="Can not cast partition size to INT.")
        if p['size'] <= 0:
            module.fail_json(msg="Partition size must be positive.")
        end = start + p['size']
        sizes[p['name']] = (start, end)
        start = end
    return sizes


def create_part_args(partition, label, sizes):

    parted_args = ['-a', partition['align'],
                   '--', 'unit', partition['unit'],
                   'mkpart']
    if label == 'msdos':
        parted_args.append(partition['type'])
    else:
        parted_args.append(partition['name'])

    if partition['format']:
        parted_args.append(partition['format'])
    parted_args.extend(["%i" % sizes[partition['name']][0],
                        "%i" % sizes[partition['name']][1]])
    return parted_args


def change_part_args(part_number, partition):
    parted_args = []
    for flag, state in partition['flags'].items():
        parted_args.extend(['set', part_number, flag, state])
    return parted_args


def parse_lsblk_json(output):

    def get_names(devices):
        names = []
        for d in devices:
            names.append(d['name'])
            names.extend(get_names(d.get('children', [])))
        return names

    return set(get_names(json.loads(output)['blockdevices']))


def parse_parted_output(output):
    partitions = set()
    for line in output.splitlines():
        out_line = line.strip().split()
        if out_line:
            try:
                int(out_line[0])
            except ValueError:
                continue
            else:
                partitions.add(out_line[0])
    return partitions


def parse_partitions(module, partitions):

    for ind, partition in enumerate(partitions):
        # partition name might be an empty string
        partition.setdefault('unit', '%')
        partition.setdefault('align', 'optimal')
        partition['name'] = partition.get('name') or 'part%i' % (ind + 1)
        partition.setdefault('type', 'primary')
        if partition['type'] not in PARTITION_TYPES:
            module.fail_json(msg="Partition type must be one of "
                             "%s." % PARTITION_TYPES)
        if partition['align'] not in SUPPORTED_ALIGN:
            module.fail_json("Unsupported partition alignmnet option. "
                             "Supported are %s" % list(SUPPORTED_ALIGN))
        partition['format'] = partition.get('format', None)
        # validate and convert partition flags
        partition['flags'] = {
            k: 'on' if module.boolean(v) else 'off'
            for k, v in partition.get('flags', {}).items()
        }
    # validate name uniqueness
    names = [p['name'] for p in partitions]
    if len(list(names)) != len(set(names)):
        module.fail_json("Partition names must be unique.")


def validate_units(module, partitions):
    has_units = set(p['unit'] for p in partitions)
    if not has_units.issubset(SUPPORTED_UNITS):
        module.fail_json("Unsupported partition size unit. Supported units "
                         "are %s" % list(SUPPORTED_UNITS))

    if len(has_units) > 1:
        module.fail_json("All partitions must have the same size unit. "
                         "Requested units are %s" % list(has_units))


def validate_msdos(module, partitions):
    """Validate limitations of MSDOS partition table"""
    p_types = [p['type'] for p in partitions]
    # NOTE(pas-ha) no more than 4 primary
    if p_types.count('primary') > 4:
        module.fail_json("Can not create more than 4 primary partitions "
                         "on a MSDOS partition table.")
    if 'extended' in p_types:
        # NOTE(pas-ha) only single extended
        if p_types.count('extended') > 1:
            module.fail_json("Can not create more than single extended "
                             "partition on a MSDOS partition table.")
        allowed = ['primary', 'extended']
        if 'logical' in p_types:
            allowed.append('logical')

        # NOTE(pas-ha) this produces list with subsequent duplicates
        # removed
        if [k for k, g in itertools.groupby(p_types)] != allowed:
            module.fail_json("Incorrect partitions order: for MSDOS, "
                             "all primary, single extended, all logical")
    elif 'logical' in p_types:
        # NOTE(pas-ha) logical has sense only with extended
        module.fail_json("Logical partition w/o extended one on MSDOS "
                         "partition table")


# TODO(pas-ha) add more validation, e.g.
# - add idempotency: first check the already existing partitions
#   and do not run anything unless really needed, and only what's needed
#   - if only change tags - use specific command
#   - allow fuzziness in partition sizes when alligment is 'optimal'
# - estimate and validate available space
# - support more units
# - support negative units?
def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(required=True, type='str'),
            label=dict(requred=False, default=None, choices=[None,
                                                             "gpt",
                                                             "msdos"]),
            dry_run=dict(required=False, type='bool', default=False),
            partitions=dict(required=False, type='list')
        ),
        supports_check_mode=True
    )

    device = module.params['device']
    label = module.params['label']
    partitions = module.params['partitions'] or []
    dry_run = module.params['dry_run']

    if partitions:
        parse_partitions(module, partitions)
        if label == 'msdos':
            validate_msdos(module, partitions)
        validate_units(module, partitions)
        sizes = parse_sizes(module, partitions)
    else:
        sizes = {}

    if module.check_mode or dry_run:
        short_dev = device.split('/')[-1]
        created_partitions = {}
        for i, p in enumerate(partitions):
            created_partitions[p['name']] = '%s%s' % (short_dev, i + 1)
        module.exit_json(changed=dry_run, created=created_partitions)

    parted_bin = module.get_bin_path('parted', required=True)
    lsblk_bin = module.get_bin_path('lsblk', required=True)
    udevadm_bin = module.get_bin_path('udevadm', required=True)
    parted = [parted_bin, '-s', device]
    lsblk = [lsblk_bin, '-J', device]
    if label:
        module.run_command(parted + ['mklabel', label], check_rc=True)
        rc, part_output, err = module.run_command(parted + ['print'],
                                                  check_rc=True)
        rc, lsblk_output, err = module.run_command(lsblk,
                                                   check_rc=True)
        part_cache = parse_parted_output(part_output)
        dev_cache = parse_lsblk_json(lsblk_output)

    created_partitions = {}

    for partition in partitions:
        # create partition
        parted_args = create_part_args(partition, label, sizes)
        module.run_command(parted + parted_args, check_rc=True)
        rc, part_output, err = module.run_command(parted + ['print'],
                                                  check_rc=True)
        # get created partition number
        part_current = parse_parted_output(part_output)
        part_created = part_current - part_cache
        part_cache = part_current
        # set partition flags
        parted_args = change_part_args(part_created.pop(),
                                       partition)
        if parted_args:
            module.run_command(parted + parted_args, check_rc=True)

        # get created block device name
        rc, lsblk_output, err = module.run_command(lsblk, check_rc=True)
        dev_current = parse_lsblk_json(lsblk_output)
        dev_created = dev_current - dev_cache
        dev_cache = dev_current
        created_partitions[partition['name']] = dev_created.pop()

    # NOTE(pas-ha) wait for all partitions to become available for write
    for dev_name in created_partitions.values():
        module.run_command([udevadm_bin,
                            'settle',
                            '--exit-if-exists=/dev/%s' % dev_name])

    module.exit_json(changed=True, created=created_partitions)


from ansible.module_utils.basic import *  # noqa
if __name__ == '__main__':
    main()
