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

import hashlib
import string

import requests

# adapted from IPA
DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1MB


class StreamingDownloader(object):

    def __init__(self, url, chunksize, hash_algo=None):
        if hash_algo is not None:
            self.hasher = hashlib.new(hash_algo)
        else:
            self.hasher = None
        self.chunksize = chunksize
        resp = requests.get(url, stream=True)
        if resp.status_code != 200:
            raise Exception('Invalid response code: %s' % resp.status_code)

        self._request = resp

    def __iter__(self):
        for chunk in self._request.iter_content(chunk_size=self.chunksize):
            if self.hasher is not None:
                self.hasher.update(chunk)
            yield chunk

    def checksum(self):
        if self.hasher is not None:
            return self.hasher.hexdigest()


def stream_to_dest(url, dest, chunksize, hash_algo):
    downloader = StreamingDownloader(url, chunksize, hash_algo)

    with open(dest, 'wb+') as f:
        for chunk in downloader:
            f.write(chunk)

    return downloader.checksum()


def main():
    module = AnsibleModule(
        argument_spec=dict(
            url=dict(required=True, type='str'),
            dest=dict(required=True, type='str'),
            checksum=dict(required=False, type='str', default=''),
            chunksize=dict(required=False, type='int',
                           default=DEFAULT_CHUNK_SIZE)
        ))

    url = module.params['url']
    dest = module.params['dest']
    checksum = module.params['checksum']
    chunksize = module.params['chunksize']
    if checksum == '':
        hash_algo, checksum = None, None
    else:
        try:
            hash_algo, checksum = checksum.rsplit(':', 1)
        except ValueError:
            module.fail_json(msg='The checksum parameter has to be in format '
                             '"<algorithm>:<checksum>"')
        checksum = checksum.lower()
        if not all(c in string.hexdigits for c in checksum):
            module.fail_json(msg='The checksum must be valid HEX number')

        if hash_algo not in hashlib.algorithms_available:
            module.fail_json(msg="%s checksums are not supported" % hash_algo)

    try:
        actual_checksum = stream_to_dest(
            url, dest, chunksize, hash_algo)
    except Exception as e:
        module.fail_json(msg=str(e))
    else:
        if hash_algo and actual_checksum != checksum:
            module.fail_json(msg='Invalid dest checksum')
        else:
            module.exit_json(changed=True)


# NOTE(pas-ha) Ansible's module_utils.basic is licensed under BSD (2 clause)
from ansible.module_utils.basic import *  # noqa
if __name__ == '__main__':
    main()
