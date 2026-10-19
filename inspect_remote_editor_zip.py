#!/usr/bin/env python3
"""Read only the official ZIP directory, without downloading file payloads."""
import collections
import io
import json
import pathlib
import urllib.request
import zipfile


class RangeReader(io.RawIOBase):
    def __init__(self, url, length):
        self.url, self.length, self.position = url, length, 0

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset + (0 if whence == 0 else self.position if whence == 1 else self.length)
        if self.position < 0:
            raise ValueError('Negative seek')
        return self.position

    def read(self, size=-1):
        size = self.length-self.position if size < 0 else min(size, self.length-self.position)
        if size <= 0:
            return b''
        if size > 128*1024*1024:
            raise ValueError('Metadata read exceeded bound')
        start, end = self.position, self.position+size-1
        request = urllib.request.Request(self.url, headers={'Range': f'bytes={start}-{end}'})
        with urllib.request.urlopen(request, timeout=90) as response:
            if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{self.length}':
                raise ValueError('Server did not honor exact range')
            data = response.read(size+1)
        if len(data) != size:
            raise ValueError('Incorrect ranged response size')
        self.position += size
        return data


def main():
    url = pathlib.Path('/tmp/ue-download-url').read_text().strip()
    if not url.startswith('https://ucs-blob-store.s3-accelerate.amazonaws.com/'):
        raise ValueError('Unexpected official download host')
    with zipfile.ZipFile(RangeReader(url, 39818576005)) as archive:
        extensions, directories = collections.Counter(), collections.Counter()
        entries = archive.infolist()
        for entry in entries:
            path = pathlib.PurePosixPath(entry.filename)
            extensions[path.suffix or '<none>'] += entry.file_size
            directories['/'.join(path.parts[:3])] += entry.file_size
        report = {'status': 'remote_directory_only', 'files': len(entries),
                  'uncompressed_bytes': sum(entry.file_size for entry in entries),
                  'extension_bytes': extensions.most_common(18),
                  'directory_bytes': directories.most_common(18),
                  'note': 'File payloads have not been verified.'}
    pathlib.Path('/workspace/ue-remote-inventory.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
