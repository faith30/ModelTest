#!/usr/bin/env python3
"""Verify a Git LFS runtime artifact and stream it into a new Linux directory.

Requires Python 3.12+ and a non-root Linux user. Does not download files or run UE.
All links and special files are rejected; only a single LinuxServer tree is allowed.
"""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sys
import tarfile


def sha256_file(path, aggregate=None):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
            if aggregate is not None:
                aggregate.update(block)
    return digest.hexdigest()


def ordinary_file(directory, name):
    if not isinstance(name, str) or not name or Path(name).name != name or ":" in name:
        raise ValueError("Artifact filenames must be simple relative names")
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing ordinary artifact file: {name}")
    return path


def verify_artifact(directory):
    manifest = json.loads((directory / "artifact_manifest.json").read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict) or (manifest.get("schema_version"), manifest.get("format"), manifest.get("root")) != (1, "tar.gz", "LinuxServer"):
        raise ValueError("Unsupported artifact manifest")
    parts = manifest.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("Manifest must list archive parts in order")
    aggregate = hashlib.sha256()
    total, paths = 0, []
    for index, item in enumerate(parts):
        if not isinstance(item, dict) or item.get("name") != f"runtime.tar.gz.part{index:04d}":
            raise ValueError("Archive parts must be contiguous and ordered")
        path = ordinary_file(directory, item["name"])
        size = path.stat().st_size
        if type(item.get("size")) is not int or item["size"] <= 0 or size != item["size"]:
            raise ValueError(f"Part size mismatch: {path.name}; Git LFS may still contain a pointer")
        if sha256_file(path, aggregate) != item.get("sha256"):
            raise ValueError(f"Part SHA256 mismatch: {path.name}")
        total += size
        paths.append(path)
    if total != manifest.get("archive_size") or aggregate.hexdigest() != manifest.get("archive_sha256"):
        raise ValueError("Combined archive size/SHA256 mismatch")
    sidecars = manifest.get("sidecars")
    required_sidecars = {"run_linux.py", "score_ue_report.py", "extract_runtime.py", "build-manifest.json", ".gitattributes"}
    if not isinstance(sidecars, dict) or not required_sidecars.issubset(sidecars):
        raise ValueError("Manifest must list evaluator sidecars")
    for name, item in sidecars.items():
        path = ordinary_file(directory, name)
        if not isinstance(item, dict) or path.stat().st_size != item.get("size") or sha256_file(path) != item.get("sha256"):
            raise ValueError(f"Sidecar mismatch: {name}")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != manifest.get("file_count"):
        raise ValueError("Invalid file inventory")
    expected = {}
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("Invalid inventory entry")
        relative = PurePosixPath(item["path"])
        if (relative.is_absolute() or ".." in relative.parts or "\\" in item["path"]
                or ":" in item["path"] or not relative.parts or relative.as_posix() != item["path"]):
            raise ValueError("Invalid inventory path")
        if item["path"] in expected or type(item.get("size")) is not int or item["size"] < 0:
            raise ValueError("Duplicate inventory path or invalid size")
        if item.get("mode") not in (0o644, 0o755) or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            raise ValueError("Invalid inventory permissions or SHA256")
        expected[item["path"]] = item
    if sum(item["size"] for item in files) != manifest.get("unpacked_size"):
        raise ValueError("Unpacked size does not match inventory")
    return manifest, paths, expected


class PartsReader(io.RawIOBase):
    def __init__(self, paths):
        super().__init__()
        self.paths = iter(paths)
        self.current = None

    def readable(self):
        return True

    def read(self, size=-1):
        if size < 0:
            raise ValueError("Unbounded reads are not allowed")
        chunks = []
        remaining = size
        while remaining:
            if self.current is None:
                path = next(self.paths, None)
                if path is None:
                    break
                self.current = path.open("rb")
            block = self.current.read(remaining)
            if block:
                chunks.append(block)
                remaining -= len(block)
            else:
                self.current.close()
                self.current = None
        return b"".join(chunks)

    def close(self):
        if self.current is not None:
            self.current.close()
        super().close()


def extract_artifact(directory, output):
    directory = directory.resolve(strict=True)
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists; choose a new directory")
    manifest, parts, expected = verify_artifact(directory)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    seen, seen_files = set(), set()
    with PartsReader(parts) as source:
        with tarfile.open(fileobj=source, mode="r|gz") as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if (name.is_absolute() or not name.parts or name.parts[0] != "LinuxServer"
                        or ".." in name.parts or "\\" in member.name or ":" in member.name
                        or member.name.rstrip("/") != name.as_posix()
                        or not (member.isfile() or member.isdir()) or name.as_posix() in seen):
                    raise ValueError(f"Rejected archive member: {member.name}")
                seen.add(name.as_posix())
                if member.isfile():
                    relative = name.relative_to("LinuxServer").as_posix()
                    item = expected.get(relative)
                    if item is None or member.size != item["size"] or member.mode != item["mode"]:
                        raise ValueError(f"Archive inventory mismatch: {member.name}")
                    seen_files.add(relative)
                elif member.mode != 0o755:
                    raise ValueError(f"Unexpected directory permissions: {member.name}")
                archive.extract(member, path=output, filter="data")
                if member.isfile() and sha256_file(output / member.name) != item["sha256"]:
                    raise ValueError(f"Extracted file SHA256 mismatch: {member.name}")
    if seen_files != set(expected):
        raise ValueError("Archive is missing files from the manifest")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory containing LinuxServer")
    args = parser.parse_args(argv)
    try:
        if sys.version_info < (3, 12):
            raise ValueError("Python 3.12 or newer is required for tarfile filter=data")
        if platform.system() != "Linux" or not hasattr(os, "geteuid") or os.geteuid() == 0:
            raise ValueError("Extraction must run on Linux as a non-root user")
        result = extract_artifact(args.artifact_root, args.output)
    except (OSError, ValueError, tarfile.TarError) as error:
        parser.exit(2, f"Extraction failed: {error}\n")
    print(f"Verified and extracted {result['file_count']} files ({result['unpacked_size']} bytes)")
    print(args.output.resolve() / "LinuxServer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
