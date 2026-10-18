#!/usr/bin/env python3
"""Read-only Linux demo prerequisites; no downloads, installs, or readiness verdict."""

import argparse
import glob
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def cgroup_limits():
    result = {"version": None, "effective_cpu_ceiling": None,
              "memory_limit_bytes": None, "memory_current_bytes": None}
    membership = read_text("/proc/self/cgroup") or ""
    group = next((line[3:] for line in membership.splitlines()
                  if line.startswith("0::")), None)
    mounts = read_text("/proc/self/mountinfo") or ""
    for line in mounts.splitlines():
        if " - cgroup2 " not in line or group is None:
            continue
        fields = line.split(" - ", 1)[0].split()
        mount_root = fields[3].replace("\\040", " ")
        mount = Path(fields[4].replace("\\040", " "))
        try:
            relative = Path(group).relative_to(mount_root)
        except ValueError:
            relative = Path(group.lstrip("/"))
        current = (mount / relative).resolve()
        if not current.is_relative_to(mount.resolve()) or not current.is_dir():
            current = mount
        result.update(version=2, path=str(current))
        cpu_quotas, memory_limits = [], []
        for directory in [current, *current.parents]:
            if not directory.is_relative_to(mount):
                break
            cpu = (read_text(directory / "cpu.max") or "").split()
            if len(cpu) == 2 and cpu[0].isdigit() and cpu[1].isdigit() and int(cpu[1]):
                cpu_quotas.append(int(cpu[0]) / int(cpu[1]))
            memory = read_text(directory / "memory.max")
            if memory and memory.isdigit():
                memory_limits.append(int(memory))
        cpuset = read_text(current / "cpuset.cpus.effective")
        result["cpuset_cpus_effective"] = cpuset
        if cpuset:
            count = 0
            for item in cpuset.split(","):
                bounds = [int(value) for value in item.split("-")]
                count += bounds[-1] - bounds[0] + 1
            cpu_quotas.append(count)
        if hasattr(os, "sched_getaffinity"):
            try:
                cpu_quotas.append(len(os.sched_getaffinity(0)))
            except OSError:
                pass
        usage = read_text(current / "memory.current")
        result["memory_current_bytes"] = int(usage) if usage and usage.isdigit() else None
        result["effective_cpu_ceiling"] = min(cpu_quotas) if cpu_quotas else None
        result["memory_limit_bytes"] = min(memory_limits) if memory_limits else None
        result["scope"] = "Visible cgroup ancestry and process affinity; hidden/shared ancestors may constrain further."
        break
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ue-root", type=Path, help="Optional explicit Unreal Engine root")
    args = parser.parse_args()
    release = {}
    for line in (read_text("/etc/os-release") or "").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in ("ID", "VERSION_ID", "PRETTY_NAME"):
            release[key] = value.strip('"')
    tools = {name: shutil.which(name) for name in ("git", "git-lfs", "docker", "UnrealEditor")}
    repo = {"path": str(args.repo.resolve()), "revision": None, "lfs_version": None}
    if tools["git"]:
        repo["revision"] = command([tools["git"], "-C", str(args.repo), "rev-parse", "--verify", "HEAD"])
        repo["lfs_version"] = command([tools["git"], "-C", str(args.repo), "lfs", "version"])
    ue = {"root": str(args.ue_root.resolve()) if args.ue_root else None,
          "editor": tools["UnrealEditor"], "version": None}
    if args.ue_root:
        editor = args.ue_root / "Engine/Binaries/Linux/UnrealEditor"
        ue["editor"] = str(editor.resolve()) if editor.is_file() else None
        version = read_text(args.ue_root / "Engine/Build/Build.version")
        try:
            data = json.loads(version or "null")
            if isinstance(data, dict):
                ue["version"] = {key: data.get(key) for key in ("MajorVersion", "MinorVersion", "PatchVersion")}
        except json.JSONDecodeError:
            pass
    devices = sorted(set(glob.glob("/dev/nvidia*") + glob.glob("/dev/dri/*")))
    icds = sorted(set(glob.glob("/etc/vulkan/icd.d/*.json")
                      + glob.glob("/usr/share/vulkan/icd.d/*.json")
                      + glob.glob("/usr/local/share/vulkan/icd.d/*.json")))
    report = {
        "probe": "read-only; device/ICD presence does not prove Vulkan or demo readiness",
        "system": {"os": platform.system(), "release": release,
                   "kernel": platform.release(), "architecture": platform.machine(),
                   "glibc": list(platform.libc_ver()), "uid": os.getuid() if hasattr(os, "getuid") else None},
        "cgroup": cgroup_limits(),
        "graphics": {"gpu_device_paths": devices, "vulkan_icd_files": icds,
                     "display": {key: os.environ.get(key) for key in ("DISPLAY", "WAYLAND_DISPLAY")}},
        "tools": tools, "unreal_engine": ue, "repository": repo,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
