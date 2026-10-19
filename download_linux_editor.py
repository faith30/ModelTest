#!/usr/bin/env python3
"""Download the official ZIP using a locally supplied expiring URL; report size composition."""
import collections
import json
import pathlib
import subprocess
import sys
import time
import zipfile


def main():
    url_file = pathlib.Path('/tmp/ue-download-url')
    archive = pathlib.Path('/workspace/Linux_Unreal_Engine_5.8.3.zip')
    expected = 39818576005
    url = url_file.read_text().strip()
    if not url.startswith('https://ucs-blob-store.s3-accelerate.amazonaws.com/'):
        raise ValueError('Unexpected official download host')
    started = time.time()
    print('Downloading official Linux UE 5.8.3 ZIP', flush=True)
    result = subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
        '--retry', '3', '--connect-timeout', '30', '--continue-at', '-',
        '--output', str(archive), url], check=False)
    if result.returncode:
        raise RuntimeError('Download failed; curl exit code %s' % result.returncode)
    if archive.stat().st_size != expected:
        raise ValueError('Archive byte count differs from previously verified official package')
    extensions = collections.Counter()
    directories = collections.Counter()
    largest = []
    with zipfile.ZipFile(archive) as package:
        for item in package.infolist():
            path = pathlib.PurePosixPath(item.filename)
            extensions[path.suffix or '<none>'] += item.file_size
            directories['/'.join(path.parts[:3])] += item.file_size
            largest.append((item.file_size, item.filename))
        report = {'status': 'downloaded_inventory_only', 'elapsed_seconds': time.time()-started,
            'archive_bytes': archive.stat().st_size, 'files': len(package.infolist()),
            'uncompressed_bytes': sum(item.file_size for item in package.infolist()),
            'extension_bytes': extensions.most_common(20),
            'directory_bytes': directories.most_common(25),
            'largest_files': sorted(largest, reverse=True)[:15],
            'note': 'ZIP contents are inventoried, not yet CRC-verified or extracted.'}
    pathlib.Path('/workspace/ue-download-inventory.json').write_text(json.dumps(report, indent=2))
    url_file.unlink()
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr, flush=True)
        sys.exit(1)
