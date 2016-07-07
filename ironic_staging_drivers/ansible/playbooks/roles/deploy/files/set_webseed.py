#!/usr/bin/python
import sys
import libtorrent as lt

torrent_file = sys.argv[1]
webseeds = sys.argv[2]
orig = lt.bdecode(open(torrent_file, 'rb').read())
new = {'info': {'name': 'image',
                'length': orig['info']['length'],
                'piece length': orig['info']['piece length'],
                'pieces': orig['info']['pieces']},
       'url-list': webseeds.split(',')}
open(torrent_file, 'wb').write(lt.bencode(new))
