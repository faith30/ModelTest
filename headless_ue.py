#!/usr/bin/env python3
"""Run real Linux UE 5.8.3 builds and Automation; never award benchmark scores."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("Non-finite JSON value: " + value)

    return json.loads(path.read_text(encoding="utf-8-sig"),
                      object_pairs_hook=unique_pairs, parse_constant=reject_constant)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_text(path):
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def cgroup_info():
    """Report container limits, which can differ from host RAM/CPU counts."""
    files = {
        "memory.max": "/sys/fs/cgroup/memory.max",
        "memory.current": "/sys/fs/cgroup/memory.current",
        "cpu.max": "/sys/fs/cgroup/cpu.max",
        "cpuset.cpus.effective": "/sys/fs/cgroup/cpuset.cpus.effective",
        "memory.limit_in_bytes": "/sys/fs/cgroup/memory/memory.limit_in_bytes",
        "memory.usage_in_bytes": "/sys/fs/cgroup/memory/memory.usage_in_bytes",
        "cpu.cfs_quota_us": "/sys/fs/cgroup/cpu/cpu.cfs_quota_us",
        "cpu.cfs_period_us": "/sys/fs/cgroup/cpu/cpu.cfs_period_us",
    }
    raw = {name: value for name, filename in files.items()
           if (value := read_text(Path(filename))) is not None}
    limit = raw.get("memory.max", raw.get("memory.limit_in_bytes"))
    memory_bytes = int(limit) if limit and limit.isdigit() else None
    cpu_cores = None
    try:
        if "cpu.max" in raw:
            quota, period = raw["cpu.max"].split()
        else:
            quota, period = raw.get("cpu.cfs_quota_us"), raw.get("cpu.cfs_period_us")
        if quota and period and int(quota) > 0 and int(period) > 0:
            cpu_cores = int(quota) / int(period)
    except ValueError:
        pass
    return {"raw": raw, "memory_limit_bytes": memory_bytes,
            "cpu_quota_cores": cpu_cores, "host_cpu_count": os.cpu_count(),
            "proc_self_cgroup": read_text(Path("/proc/self/cgroup"))}


def doctor(engine, project):
    engine, project = engine.resolve(), project.resolve()
    problems, warnings = [], []
    system = platform.system()
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    if system != "Linux":
        problems.append("Linux is required; this command will not launch UE on Windows or macOS.")
    if uid == 0:
        problems.append("UE must run as a non-root user; do not use sudo for build or automation.")
    if system == "Linux" and uid is None:
        problems.append("Cannot verify the effective user ID.")
    version = None
    try:
        data = read_json(engine / "Engine/Build/Build.version")
        fields = [data.get(k) for k in ("MajorVersion", "MinorVersion", "PatchVersion")]
        if any(type(value) is not int for value in fields):
            raise ValueError("version fields must be integers")
        version = ".".join(map(str, fields))
        if version != "5.8.3":
            problems.append("Expected UE 5.8.3; found " + version)
    except (OSError, ValueError, AttributeError) as error:
        problems.append("Cannot read Engine/Build/Build.version: " + str(error))
    try:
        if project.suffix.lower() != ".uproject" or not isinstance(read_json(project), dict):
            raise ValueError("expected a .uproject JSON object")
    except (OSError, ValueError) as error:
        problems.append("Invalid project: " + str(error))
    build_script = engine / "Engine/Build/BatchFiles/Linux/Build.sh"
    if not build_script.is_file():
        problems.append("Missing Linux Build.sh: " + str(build_script))
    editor = None
    rejected_editors = []
    host_machine = platform.machine().lower()
    expected_machine = {"x86_64": 62, "amd64": 62, "aarch64": 183, "arm64": 183}.get(host_machine)
    for name in ("UnrealEditor-Cmd", "UnrealEditor"):
        path = engine / "Engine/Binaries/Linux" / name
        try:
            with path.open("rb") as source:
                header = source.read(20)
            if (len(header) != 20 or header[:6] != b"\x7fELF\x02\x01"
                    or int.from_bytes(header[16:18], "little") not in (2, 3)):
                raise ValueError("not a little-endian ELF64 executable")
            if system == "Linux" and (expected_machine is None
                    or int.from_bytes(header[18:20], "little") != expected_machine):
                raise ValueError("ELF architecture does not match this host")
            if system == "Linux" and not os.access(path, os.X_OK):
                raise ValueError("missing executable permission")
            editor = path
            break
        except (OSError, ValueError) as error:
            rejected_editors.append(str(path) + ": " + str(error))
    if editor is None:
        problems.append("No usable Linux UnrealEditor-Cmd or UnrealEditor ELF was found.")
    if system == "Linux" and shutil.which("bash") is None:
        problems.append("bash is required for Linux Build.sh.")
    limits = cgroup_info() if system == "Linux" else {"available": False}
    memory_bytes = limits.get("memory_limit_bytes")
    if memory_bytes is not None and memory_bytes <= 4 * 1024 ** 3:
        warnings.append("Memory limit is at most 4 GiB. Build/run sequentially; success is not guaranteed, but this is not a hard block.")
    warnings.append("NullRHI/nosound tests do not prove visual, audio, or complete interactive acceptance.")
    return {"schema_version": 1, "status": "ready" if not problems else "blocked",
            "checked_at": utc_now(), "os": system, "machine": host_machine, "uid": uid,
            "engine": str(engine), "project": str(project), "engine_version": version,
            "editor": str(editor) if editor else None, "build_script": str(build_script),
            "cgroup": limits, "problems": problems, "warnings": warnings,
            "editor_probe_errors": rejected_editors,
            "boundary": "File/environment preflight only; no UE process or build has run."}


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def execute(command, cwd, output, timeout):
    started_clock = time.monotonic()
    record = {"command": command, "cwd": str(cwd), "started_at": utc_now(),
              "timeout_seconds": timeout, "exit_code": None, "timed_out": False,
              "interrupted": False, "launch_error": None, "stdout": "stdout.log"}
    write_json(output / "run.json", record)
    with (output / "stdout.log").open("wb") as log:
        try:
            process = subprocess.Popen(command, cwd=str(cwd), stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as error:
            record["launch_error"] = str(error)
        else:
            record["pid"] = process.pid
            try:
                record["exit_code"] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record["timed_out"] = True
                stop_group(process)
                record["exit_code"] = process.returncode
            except KeyboardInterrupt:
                record["interrupted"] = True
                stop_group(process)
                record["exit_code"] = process.returncode
    record["finished_at"] = utc_now()
    record["elapsed_seconds"] = round(time.monotonic() - started_clock, 3)
    write_json(output / "run.json", record)
    return record


def inspect_report(path, expected_count):
    result = {"path": str(path), "expected_count": expected_count, "observed_count": 0,
              "passed": 0, "failed": 0, "unfinished": 0, "problems": [], "tests": []}
    problems = result["problems"]
    try:
        report = read_json(path)
        if not isinstance(report, dict) or not isinstance(report.get("tests"), list):
            raise ValueError("expected a report object containing a tests array")
        tests = report["tests"]
        result["observed_count"] = len(tests)
        if not tests:
            problems.append("No tests matched or executed.")
        if len(tests) != expected_count:
            problems.append("Test count does not match --expected-count.")
        names = set()
        counts = {"succeeded": 0, "succeededWithWarnings": 0, "failed": 0,
                  "notRun": 0, "inProcess": 0}
        for test in tests:
            if not isinstance(test, dict):
                raise ValueError("test entries must be objects")
            name, state = test.get("fullTestPath"), test.get("state")
            if not isinstance(name, str) or not name.strip() or name in names:
                problems.append("Missing or duplicate fullTestPath: " + str(name))
            names.add(str(name))
            errors, warnings = test.get("errors"), test.get("warnings")
            if type(errors) is not int or errors < 0 or type(warnings) is not int or warnings < 0:
                raise ValueError("test errors/warnings must be non-negative integers")
            entries = test.get("entries", [])
            if not isinstance(entries, list):
                raise ValueError("test entries must be an array")
            logged_error = any(isinstance(entry, dict) and isinstance(entry.get("event"), dict)
                               and entry["event"].get("type") == "Error" for entry in entries)
            if state == "Success":
                counts["succeededWithWarnings" if warnings else "succeeded"] += 1
                if errors or logged_error:
                    result["failed"] += 1
                    problems.append("Success test contains errors: " + str(name))
                else:
                    result["passed"] += 1
            elif state == "Fail":
                counts["failed"] += 1
                result["failed"] += 1
            else:
                result["unfinished"] += 1
                if state in ("NotRun", "InProcess"):
                    counts["notRun" if state == "NotRun" else "inProcess"] += 1
                else:
                    problems.append("Unknown test state: " + str(state))
            result["tests"].append({"name": name, "state": state,
                                    "errors": errors, "warnings": warnings})
        for key, count in counts.items():
            if type(report.get(key)) is not int or report[key] != count:
                problems.append("Report summary mismatch: " + key)
        if result["failed"] or result["unfinished"]:
            problems.append("One or more tests failed or did not finish.")
    except (OSError, ValueError, TypeError) as error:
        problems.append("Missing or invalid UE report: " + str(error))
    result["all_passed"] = not problems and result["passed"] == expected_count
    return result


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def automation_filter(value):
    if not value.strip() or not re.fullmatch(r"[A-Za-z0-9_.+*/: -]+", value):
        raise argparse.ArgumentTypeError("use a test name/prefix; quotes, commas, semicolons and control characters are not allowed")
    return value.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("doctor", "build", "automation"):
        sub = commands.add_parser(action)
        sub.add_argument("--engine", type=Path, required=True, help="UE root containing Engine/")
        sub.add_argument("--project", type=Path, required=True, help="Lyra.uproject path")
        if action != "doctor":
            sub.add_argument("--output", type=Path, required=True, help="new output directory; never overwritten")
            sub.add_argument("--timeout", type=positive_int, default=900 if action == "automation" else 3600)
        if action == "automation":
            sub.add_argument("--filter", type=automation_filter, required=True)
            sub.add_argument("--expected-count", type=positive_int, required=True)
    args = parser.parse_args(argv)
    preflight = doctor(args.engine, args.project)
    if args.action == "doctor" or preflight["status"] != "ready":
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 0 if preflight["status"] == "ready" else 2
    if os.path.lexists(args.output):
        parser.error("--output already exists; choose a new directory")
    output = args.output.resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        parser.error("cannot create output directory: " + str(error))
    write_json(output / "doctor.json", preflight)
    project = Path(preflight["project"])
    if args.action == "build":
        command = ["bash", preflight["build_script"], "LyraEditor", "Linux", "Development",
                   "-Project=" + str(project), "-WaitMutex", "-NoHotReloadFromIDE", "-MaxParallelActions=1"]
    else:
        command = [preflight["editor"], str(project), "-unattended", "-nullrhi", "-nosound",
                   "-NoSourceControl", "-ExecCmds=Automation RunTests " + args.filter,
                   "-TestExit=Automation Test Queue Empty", "-ReportExportPath=" + str(output / "report"),
                   "-abslog=" + str(output / "ue.log")]
    print("Running real UE; logs: " + str(output), flush=True)
    run = execute(command, project.parent, output, args.timeout)
    passed = (run["exit_code"] == 0 and not run["timed_out"]
              and not run["interrupted"] and run["launch_error"] is None)
    result = {"schema_version": 1, "action": args.action, "passed": passed,
              "run": run, "engine_version": preflight["engine_version"],
              "scope": "Actual process result only; no benchmark score or visual/audio acceptance is inferred."}
    if args.action == "automation":
        result["filter"] = args.filter
        result["automation"] = inspect_report(output / "report/index.json", args.expected_count)
        result["passed"] = passed and result["automation"]["all_passed"]
    result["status"] = "passed" if result["passed"] else "not_passed"
    write_json(output / "result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
