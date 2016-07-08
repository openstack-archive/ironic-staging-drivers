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


PARTITION_TYPES = ('primary', 'logical', 'extended')


def construct_parted_args(device):

    parted_args = [
        '-s', device['device'],
    ]
    if device['label']:
        parted_args.extend(['mklabel', device['label']])

    partitions = device['partitions']
    if partitions:
        parted_args.extend(['-a', 'optimal', '--', 'unit', 'MiB'])
        start = 1
        for ind, partition in enumerate(device['partitions']):
            parted_args.extend([
                'mkpart', partition['type']])
            if partition['swap']:
                parted_args.append('linux-swap')
            end = start + partition['size_mib']
            parted_args.extend(["%i" % start, "%i" % end])
            start = end
            if partition['boot']:
                parted_args.extend([
                    'set', str(ind + 1), 'boot', 'on'])

    return parted_args


def validate_partitions(module, partitions):
    for ind, partition in enumerate(partitions):
        # partition name might be an empty string
        partition['name'] = partition.get('name') or str(ind + 1)
        size = partition.get('size_mib', None)
        if not size:
            module.fail_json(msg="Partition size must be provided")
        try:
            partition['size_mib'] = int(size)
        except ValueError:
            module.fail_json(msg="Can not cast partition size to INT.")
        partition.setdefault('type', 'primary')
        if partition['type'] not in PARTITION_TYPES:
            module.fail_json(msg="Partition type must be one of "
                             "%s." % PARTITION_TYPES)
        partition['swap'] = module.boolean(partition.get('swap', False))
        partition['boot'] = module.boolean(partition.get('boot', False))
        if partition['boot'] and partition['swap']:
            module.fail_json(msg="Can not set partition to "
                                 "boot and swap simultaneously.")
    # TODO(pas-ha) add more validation, e.g.
    # - only one boot partition?
    # - no more than 4 primary partitions on msdos table
    # - no more that one extended partition on msdos table
    # - estimate and validate available space


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(required=True, type='str'),
            dryrun=dict(required=False, default=False, type='bool'),
            new_label=dict(required=False, default=False, type='bool'),
            label=dict(requred=False, default='msdos', choices=[
                "bsd", "dvh", "gpt", "loop", "mac", "msdos", "pc98", "sun"]),
            partitions=dict(
                required=False, type='list')
        ),
        supports_check_mode=True)

    device = module.params['device']
    dryrun = module.params['dryrun']
    new_label = module.params['new_label']
    label = module.params['label']
    if not new_label:
        label = False
    partitions = module.params['partitions'] or []
    try:
        validate_partitions(module, partitions)
    except Exception as e:
        module.fail_json(msg="Malformed partitions arguments: %s" % e)
    parted_args = construct_parted_args(dict(device=device, label=label,
                                             partitions=partitions))
    command = [module.get_bin_path('parted', required=True)]
    if not (module.check_mode or dryrun):
        command.extend(parted_args)
        module.run_command(command, check_rc=True)
    partitions_created = {p['name']: '%s%i' % (device, i + 1)
                          for i, p in enumerate(partitions)}
    module.exit_json(changed=not dryrun, created=partitions_created)


from ansible.module_utils.basic import *  # noqa
if __name__ == '__main__':
    main()
