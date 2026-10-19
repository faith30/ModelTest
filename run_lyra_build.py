#!/usr/bin/env python3
"""Build the complete Linux LyraEditor target with time and cgroup evidence."""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import sys
import threading
import time

sys.dont_write_bytecode = True
import headless_ue
from run_editor_probe import (
    cgroup_directory, cgroup_snapshot, memory_sample, read_optional, save,
)


def cleanup_group(record):
    """The time leader may exit while a compiler child remains in its group."""
    pid = record.get("pid")
    if pid is None:
        return []
    sent = []
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            break
        sent.append(sig.name)
        if sig == signal.SIGTERM:
            time.sleep(0.25)
    return sent


def measured_execute(execute, command, cwd, output, timeout):
    build_environment = {
        name: os.environ.get(name)
        for name in ("DOTNET_gcServer", "DOTNET_GCHeapHardLimit", "DOTNET_GCConserveMemory")
    }
    cgroup = cgroup_directory()
    before = cgroup_snapshot(cgroup)
    save(output / "cgroup-before.json", before)
    started_clock = time.monotonic()
    finished = threading.Event()
    sampled = {"count": 0, "max_current_bytes": None, "errors": []}

    def sample_until_finished(stream):
        try:
            while True:
                sample = memory_sample(cgroup, started_clock)
                stream.write(json.dumps(sample) + "\n")
                stream.flush()
                sampled["count"] += 1
                value = sample["memory_current_bytes"]
                if value is not None:
                    sampled["max_current_bytes"] = max(sampled["max_current_bytes"] or 0, value)
                if finished.wait(1):
                    break
        except Exception as error:
            sampled["errors"].append(str(error))

    measured = ["/usr/bin/time", "-v", "-o", str(output / "memory.txt"), *command]
    # headless_ue.execute retains the actual build exit code, launches one new
    # process group, and applies its existing TERM/KILL timeout handling.
    with (output / "memory-samples.jsonl").open("x", encoding="utf-8") as samples:
        sampler = threading.Thread(target=sample_until_finished, args=(samples,))
        sampler.start()
        try:
            record = execute(measured, cwd, output, timeout)
            record["build_environment"] = build_environment
            record["remaining_group_cleanup_signals"] = cleanup_group(record)
        finally:
            finished.set()
            sampler.join()
    after = cgroup_snapshot(cgroup)
    save(output / "cgroup-after.json", after)
    record["cgroup_events_delta"] = {
        key: after["events"][key] - before["events"][key]
        for key in before["events"].keys() & after["events"].keys()
    }
    record["cgroup_local_events_delta"] = {
        key: after["local_events"][key] - before["local_events"][key]
        for key in before["local_events"].keys() & after["local_events"].keys()
    }
    report = read_optional(output / "memory.txt")
    rss = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", report or "")
    record["memory"] = {
        "sample_count": sampled["count"], "sampling_errors": sampled["errors"],
        "max_sampled_cgroup_memory_current_bytes": sampled["max_current_bytes"],
        "time_max_resident_set_kbytes": int(rss.group(1)) if rss else None,
        "time_report_available": report is not None,
        "boundary": (
            "Cgroup values include all processes and file cache; 1-second samples can miss peaks. "
            "memory.peak is a cgroup lifetime value and was not reset. GNU time max RSS is not "
            "simultaneous aggregate cgroup memory. Timeout or signals can prevent its final report. "
            "Exit -9/137 alone does not prove OOM; event deltas are shared-cgroup evidence, "
            "not per-process attribution."
        ),
    }
    record["build_scope"] = (
        "The complete LyraEditor Linux Development target via headless_ue build; "
        "existing build caches may be reused. No feature runtime tests or benchmark score."
    )
    save(output / "run.json", record)
    (output / "exit-code.txt").write_text(str(record["exit_code"]) + "\n", encoding="utf-8")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path, help="full Lyra.uproject")
    parser.add_argument("--output", required=True, type=Path, help="new evidence directory; never overwritten")
    parser.add_argument("--timeout", type=headless_ue.positive_int, default=3600)
    parser.add_argument("--no-pch", action="store_true", help="pass -NoPCH to bypass all precompiled headers")
    parser.add_argument("--no-shared-pch", action="store_true", help="pass -NoSharedPCH to disable shared precompiled headers")
    parser.add_argument("--no-uba", action="store_true",
                        help="pass -NoUBA; in UE 5.8.3 this disables detours, not UBAExecutor")
    args = parser.parse_args(argv)
    if os.path.lexists(args.output):
        parser.error("--output already exists; choose a new directory")
    original_doctor, original_execute = headless_ue.doctor, headless_ue.execute

    def doctor(engine, project):
        result = original_doctor(engine, project)
        if not Path("/usr/bin/time").is_file() or not os.access("/usr/bin/time", os.X_OK):
            result["problems"].append("GNU /usr/bin/time is required")
        if project.name != "Lyra.uproject" or not (project.parent / "Source/LyraEditor.Target.cs").is_file():
            result["problems"].append("Expected the full Lyra project with Source/LyraEditor.Target.cs")
        if result["problems"]:
            result["status"] = "blocked"
        return result

    # Reuse the authoritative build command, preflight, execution and result
    # policy without editing the shared helper or launching a nested wrapper.
    def execute(command, cwd, output, timeout):
        build_command = list(command)
        if args.no_pch:
            build_command.append("-NoPCH")
        if args.no_shared_pch:
            build_command.append("-NoSharedPCH")
        if args.no_uba:
            build_command.append("-NoUBA")
        return measured_execute(original_execute, build_command, cwd, output, timeout)

    headless_ue.doctor = doctor
    headless_ue.execute = execute
    previous_locale = os.environ.get("LC_ALL")
    os.environ["LC_ALL"] = "C"
    try:
        return headless_ue.main([
            "build", "--engine", str(args.engine), "--project", str(args.project),
            "--output", str(args.output), "--timeout", str(args.timeout),
        ])
    finally:
        headless_ue.doctor, headless_ue.execute = original_doctor, original_execute
        if previous_locale is None:
            os.environ.pop("LC_ALL", None)
        else:
            os.environ["LC_ALL"] = previous_locale


if __name__ == "__main__":
    raise SystemExit(main())
