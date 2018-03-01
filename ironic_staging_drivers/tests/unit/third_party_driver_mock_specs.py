# Copyright 2015 Intel Corporation
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

"""This module provides mock 'specs' for third party modules that can be used
when needing to mock those third party modules"""

# iboot
IBOOT_SPEC = (
    'iBootInterface',
)

# libvirt
LIBVIRT_SPEC = (
    'libvirtError',
    'open',
    'openAuth',
    'VIR_CRED_AUTHNAME',
    'VIR_CRED_PASSPHRASE',
)

# ovirt
OVIRT4_SPEC = (
    'types',
)
