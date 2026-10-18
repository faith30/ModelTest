#!/usr/bin/env python3
"""Package staged LinuxServer files for Git LFS without running UE or Git.

The archive has normalized metadata, preserves file bytes, omits Saved directories,
and retains debug symbols. Identical input bytes and compressor versions produce
identical output; this does not promise deterministic UE builds.
"""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile


CHUNK_SIZE = 1024 ** 3
ROOT_NAME = "LinuxServer"


class ChunkWriter(io.RawIOBase):
    def __init__(self, directory, chunk_size=CHUNK_SIZE):
        super().__init__()
        self.directory, self.chunk_size = directory, chunk_size
        self.current = None
        self.parts = []
        self.size = 0
        self.sha256 = hashlib.sha256()

    def writable(self):
        return True

    def tell(self):
        return self.size

    def finish_part(self):
        if self.current is not None:
            self.current.close()
            self.parts.append({"name": self.name, "size": self.part_size,
                               "sha256": self.part_hash.hexdigest()})
            self.current = None

    def write(self, data):
        view = memoryview(data)
        self.sha256.update(view)
        self.size += len(view)
        while view:
            if self.current is None:
                self.name = f"runtime.tar.gz.part{len(self.parts):04d}"
                self.current = (self.directory / self.name).open("xb")
                self.part_size, self.part_hash = 0, hashlib.sha256()
            block = view[:self.chunk_size - self.part_size]
            self.current.write(block)
            self.part_hash.update(block)
            self.part_size += len(block)
            view = view[len(block):]
            if self.part_size == self.chunk_size:
                self.finish_part()
        return len(data)

    def close(self):
        self.finish_part()
        super().close()


class HashingReader:
    def __init__(self, source):
        self.source, self.sha256 = source, hashlib.sha256()

    def read(self, size):
        data = self.source.read(size)
        self.sha256.update(data)
        return data


def normalized_info(name, size=0, directory=False, executable=False):
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.size = size
    info.mode = 0o755 if directory or executable else 0o644
    info.uid = info.gid = info.mtime = 0
    info.uname = info.gname = ""
    return info


def package(package_root, build_manifest, output):
    package_root = package_root.resolve(strict=True)
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists; choose a new directory")
    output = output.resolve()
    if not package_root.is_dir() or output.is_relative_to(package_root):
        raise ValueError("Package must be a directory; output must be outside it")
    build_bytes = build_manifest.read_bytes()
    build = json.loads(build_bytes.decode("utf-8-sig"))
    if (not isinstance(build, dict) or type(build.get("build_exit_code")) is not int
            or build["build_exit_code"] != 0 or build.get("target_platform") != "Linux"):
        raise ValueError("Build manifest must record a successful build")
    paths = sorted(package_root.rglob("*"), key=lambda p: p.relative_to(package_root).as_posix())
    included = []
    excluded = []
    for path in paths:
        relative = path.relative_to(package_root)
        if "saved" in (part.lower() for part in relative.parts):
            if path.is_file():
                excluded.append({"path": relative.as_posix(), "size": path.stat().st_size})
            continue
        if (path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())
                or not (path.is_file() or path.is_dir())):
            raise ValueError(f"Only ordinary files/directories are supported: {relative}")
        included.append(path)
    required = ["run_linux.py", "score_ue_report.py", "extract_runtime.py"]
    for name in required:
        if not Path(__file__).with_name(name).is_file():
            raise ValueError(f"Missing evaluator script: {name}")
    output.mkdir(parents=True, exist_ok=False)
    inventory = []
    writer = ChunkWriter(output, CHUNK_SIZE)
    with writer:
        with gzip.GzipFile(filename="", mode="wb", fileobj=writer, mtime=0, compresslevel=6) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                archive.addfile(normalized_info(ROOT_NAME, directory=True))
                for path in included:
                    relative = path.relative_to(package_root).as_posix()
                    name = ROOT_NAME + "/" + relative
                    if path.is_dir():
                        archive.addfile(normalized_info(name, directory=True))
                        continue
                    before = path.stat()
                    with path.open("rb") as source:
                        executable = source.read(4) == b"\x7fELF"
                        source.seek(0)
                        reader = HashingReader(source)
                        info = normalized_info(name, before.st_size, executable=executable)
                        archive.addfile(info, reader)
                    after = path.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError(f"File changed while packaging: {relative}")
                    inventory.append({"path": relative, "size": before.st_size,
                                      "mode": info.mode, "sha256": reader.sha256.hexdigest()})
    by_path = {entry["path"]: entry for entry in inventory}
    binary_name = str(build.get("binary_relpath", "")).replace("\\", "/")
    if binary_name not in by_path or by_path[binary_name]["sha256"] != build.get("binary_sha256"):
        raise ValueError("Staged binary does not match build manifest")
    if "LyraServer.sh" not in by_path:
        raise ValueError("Package is missing LyraServer.sh")
    sidecars = {}
    for name in required:
        shutil.copyfile(Path(__file__).with_name(name), output / name)
    (output / "build-manifest.json").write_bytes(build_bytes)
    (output / ".gitattributes").write_text(
        "runtime.tar.gz.part* filter=lfs diff=lfs merge=lfs -text\n"
        "*.py -text\n*.json -text\n*.sh text eol=lf\n", encoding="utf-8", newline="\n")
    for name in [*required, "build-manifest.json", ".gitattributes"]:
        data = (output / name).read_bytes()
        sidecars[name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    manifest = {"schema_version": 1, "format": "tar.gz", "root": ROOT_NAME,
                "chunk_size": CHUNK_SIZE, "parts": writer.parts,
                "archive_size": writer.size, "archive_sha256": writer.sha256.hexdigest(),
                "file_count": len(inventory), "unpacked_size": sum(item["size"] for item in inventory),
                "files": inventory, "excluded_saved_files": excluded, "sidecars": sidecars}
    (output / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--build-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New artifact directory")
    args = parser.parse_args(argv)
    try:
        result = package(args.package_root, args.build_manifest, args.output)
    except (OSError, ValueError, tarfile.TarError) as error:
        parser.exit(2, f"Packaging failed: {error}\n")
    print(f"Packaged {result['file_count']} files; {result['unpacked_size']} bytes unpacked; "
          f"{result['archive_size']} compressed bytes in {len(result['parts'])} parts")
    print(args.output.resolve() / "artifact_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
