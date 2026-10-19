#!/usr/bin/env python3
"""Extract a Linux editor without optional debug symbols, validate, remove its redundant ZIP."""
import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import time
import zipfile


def main():
    archive = pathlib.Path('/workspace/Linux_Unreal_Engine_5.8.3.zip')
    engine = pathlib.Path('/workspace/UE_5.8.3')
    if archive.stat().st_size != 39818576005:
        raise ValueError('Official archive download is not complete')
    if engine.exists():
        raise ValueError('Engine destination already exists; refusing to merge or overwrite')
    if not shutil.which('unzip'):
        raise ValueError('unzip is required to preserve archive permissions and symlinks')
    started = time.time()
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        for entry in entries:
            path = pathlib.PurePosixPath(entry.filename)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe archive path')
            if stat.S_ISLNK(entry.external_attr >> 16):
                target = package.read(entry).decode('utf8')
                destination = (engine / str(path.parent) / target).resolve()
                if not destination.is_relative_to(engine.resolve()):
                    raise ValueError('Archive symlink leaves engine root')
        excluded = [entry for entry in entries if entry.filename.endswith(('.debug', '.sym'))]
        selected_bytes = sum(entry.file_size for entry in entries) - sum(entry.file_size for entry in excluded)
    print('Archive directory validated; extracting selected files with CRC checks', flush=True)
    subprocess.run(['unzip', '-q', str(archive), '-d', str(engine), '-x', '*.debug', '*.sym'], check=True)
    version = json.loads((engine / 'Engine/Build/Build.version').read_text())
    if (version['MajorVersion'], version['MinorVersion'], version['PatchVersion']) != (5, 8, 3):
        raise ValueError('Unexpected engine version')
    executable = engine / 'Engine/Binaries/Linux/UnrealEditor-Cmd'
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError('Editor executable missing or not executable')
    with executable.open('rb') as stream:
        if stream.read(4) != b'\x7fELF':
            raise ValueError('Editor executable is not ELF')
    with archive.open('rb') as stream:
        archive_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = {'status': 'extracted_not_yet_runtime_verified', 'engine': str(engine),
                'version': version, 'archive_bytes': archive.stat().st_size,
                'archive_sha256': archive_sha256, 'excluded_suffixes': ['.debug', '.sym'],
                'excluded_files': len(excluded), 'excluded_bytes': sum(entry.file_size for entry in excluded),
                'selected_uncompressed_bytes': selected_bytes, 'unzip_exit': 0,
                'elapsed_seconds': time.time()-started,
                'note': 'All selected entries passed unzip CRC. Optional symbols omitted; no feature validation yet.'}
    # This archive was downloaded by this task and is reproducible from the official source.
    # Remove only this exact completed redundant installer before the snapshot.
    archive.unlink()
    manifest['redundant_archive_removed'] = True
    pathlib.Path('/workspace/ue-lean-install.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == '__main__':
    main()
