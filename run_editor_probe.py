#!/usr/bin/env python3
"""Run the real UE 5.8.3 Python probe, retaining bounded memory and exit evidence."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

# Importing a sibling tool must not write caches into the installed kit.
sys.dont_write_bytecode = True
from headless_ue import doctor, positive_int, read_json


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_optional(path):
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def key_values(text):
    result = {}
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            result[parts[0]] = int(parts[1])
    return result


def cgroup_directory():
    root = Path("/sys/fs/cgroup")
    membership = read_optional(Path("/proc/self/cgroup")) or ""
    for line in membership.splitlines():
        if line.startswith("0::"):
            relative = Path(line[3:].lstrip("/"))
            if ".." not in relative.parts:
                candidate = root / relative
                if (candidate / "memory.current").is_file():
                    return candidate
    # Namespaced containers commonly expose their own cgroup at this root.
    return root


def cgroup_snapshot(directory):
    names = ("memory.current", "memory.max", "memory.peak", "memory.stat",
             "memory.events", "memory.events.local", "memory.swap.current",
             "memory.swap.max", "memory.swap.peak", "memory.swap.events", "cpu.max")
    raw = {name: read_optional(directory / name) for name in names}
    return {"captured_at": utc_now(), "directory": str(directory), "raw": raw,
            "events": key_values(raw["memory.events"]),
            "local_events": key_values(raw["memory.events.local"]),
            "stat": key_values(raw["memory.stat"]),
            "peak_boundary": "memory.peak/swap.peak are cgroup lifetime values; not reset and not this run's peak."}


def memory_sample(directory, started_clock):
    current = read_optional(directory / "memory.current")
    swap = read_optional(directory / "memory.swap.current")
    stat = key_values(read_optional(directory / "memory.stat"))
    return {"captured_at": utc_now(), "elapsed_seconds": round(time.monotonic() - started_clock, 3),
            "memory_current_bytes": int(current) if current and current.isdigit() else None,
            "swap_current_bytes": int(swap) if swap and swap.isdigit() else None,
            "anon_bytes": stat.get("anon"), "file_bytes": stat.get("file")}


def stop_group(process):
    sent = []
    for sig, wait_seconds in ((signal.SIGTERM, 5), (signal.SIGKILL, None)):
        try:
            os.killpg(process.pid, sig)
            sent.append(sig.name)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=wait_seconds)
        except subprocess.TimeoutExpired:
            pass
    return sent


def validate_probe(path, project_directory):
    problems = []
    data = None
    try:
        data = read_json(path)
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        required = ("schema_version", "probe", "status", "executed_in_real_unreal",
                    "engine_version", "required_engine_version_prefix", "project_directory",
                    "process_id", "api_presence", "score", "boundary")
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError("missing fields: " + ", ".join(missing))
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            problems.append("Invalid probe schema_version")
        if data["probe"] != "real_ue_editor_python_api_presence":
            problems.append("Unexpected probe identity")
        if data["status"] != "completed" or data["executed_in_real_unreal"] is not True:
            problems.append("The real Unreal Python probe did not complete")
        if data["required_engine_version_prefix"] != "5.8.3" or not isinstance(data["engine_version"], str) or not re.match(r"^5\.8\.3(?:[-+ ]|$)", data["engine_version"]):
            problems.append("Unexpected actual engine version")
        if type(data["process_id"]) is not int or data["process_id"] <= 0:
            problems.append("Invalid probe process_id")
        actual_project = data["project_directory"]
        if not isinstance(actual_project, str) or not actual_project.strip():
            problems.append("Missing actual Unreal project directory")
        else:
            actual_path = Path(actual_project)
            if not actual_path.is_absolute():
                actual_path = project_directory / actual_path
            if actual_path.resolve() != project_directory.resolve():
                problems.append("Unreal loaded a different project directory")
        if data["score"] is not None or not isinstance(data["boundary"], str) or not data["boundary"]:
            problems.append("Invalid diagnostic boundary or unexpected score")
        if "error" in data:
            problems.append("Probe recorded an error")
        expected = {
            "SystemLibrary": ("get_engine_version", "get_project_directory"),
            "PythonScriptLibrary": ("is_python_available", "is_python_initialized", "execute_python_command"),
            "BlueprintEditorLibrary": ("find_graph", "list_graphs", "compile_blueprint", "create_blueprint_asset_with_parent", "add_member_variable"),
            "BlueprintGraphEditor": ("get_graph_editor", "get_graph_editor_by_name", "create_and_edit_function_graph"),
            "UMGToolSet": ("get_widgets", "create_widget_blueprint", "add_widget", "compile_widget_blueprint"),
        }
        apis = data["api_presence"]
        if not isinstance(apis, dict):
            raise ValueError("api_presence must be an object")
        for name, methods in expected.items():
            item = apis.get(name)
            if not isinstance(item, dict) or type(item.get("class_exposed")) is not bool or not isinstance(item.get("methods_exposed"), dict):
                problems.append("Incomplete API evidence: " + name)
                continue
            for method in methods:
                if type(item["methods_exposed"].get(method)) is not bool:
                    problems.append("Missing API evidence: " + name + "." + method)
            if name == "SystemLibrary" and (item["class_exposed"] is not True or any(item["methods_exposed"].get(method) is not True for method in methods)):
                problems.append("Required SystemLibrary query APIs unavailable")
    except (OSError, ValueError, TypeError) as error:
        problems.append("Missing or invalid probe.json: " + str(error))
    return {"valid": not problems, "problems": problems, "probe": data}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new directory; never overwritten")
    parser.add_argument("--timeout", type=positive_int, default=300)
    args = parser.parse_args(argv)
    kit = Path(__file__).resolve().parent
    template, script = kit / "editor-probe/Probe.uproject", kit / "editor_probe.py"
    preflight = doctor(args.engine, template)
    if not script.is_file():
        preflight["problems"].append("Missing editor_probe.py")
    if not Path("/usr/bin/time").is_file() or not os.access("/usr/bin/time", os.X_OK):
        preflight["problems"].append("GNU /usr/bin/time is required")
    if preflight["problems"]:
        preflight["status"] = "blocked"
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 2
    if os.path.lexists(args.output):
        parser.error("output already exists; choose a new directory")
    output = args.output.resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
        project_directory = output / "project"
        project_directory.mkdir()
        project = project_directory / "Probe.uproject"
        shutil.copyfile(template, project)
    except OSError as error:
        parser.error("cannot prepare new output: " + str(error))
    save(output / "doctor.json", preflight)
    cgroup = cgroup_directory()
    before = cgroup_snapshot(cgroup)
    save(output / "cgroup-before.json", before)
    command = ["/usr/bin/time", "-v", "-o", str(output / "memory.txt"), preflight["editor"],
               str(project), "-run=pythonscript", "-script=" + str(script), "-unattended",
               "-nullrhi", "-nosound", "-NoShaderCompile", "-NoSourceControl",
               "-abslog=" + str(output / "ue.log")]
    env = os.environ.copy()
    env.update(LYRA_EDITOR_PROBE_OUTPUT=str(output / "probe.json"), LC_ALL="C")
    started_clock = time.monotonic()
    run = {"schema_version": 1, "status": "running", "passed": False, "command": command,
           "cwd": str(project_directory), "started_at": utc_now(), "timeout_seconds": args.timeout,
           "exit_code": None, "timed_out": False, "interrupted": False, "launch_error": None}
    save(output / "run.json", run)
    print("Running real Unreal Editor probe; evidence: " + str(output), flush=True)
    sampled_max = None
    sample_count = 0
    with (output / "stdout.log").open("wb") as log, (output / "memory-samples.jsonl").open("w", encoding="utf-8") as samples:
        try:
            process = subprocess.Popen(command, cwd=project_directory, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as error:
            run["launch_error"] = str(error)
        else:
            run["time_process_id"] = process.pid
            save(output / "run.json", run)
            try:
                while True:
                    sample = memory_sample(cgroup, started_clock)
                    samples.write(json.dumps(sample) + "\n")
                    samples.flush()
                    sample_count += 1
                    current = sample["memory_current_bytes"]
                    if current is not None:
                        sampled_max = max(sampled_max or 0, current)
                    remaining = args.timeout - (time.monotonic() - started_clock)
                    if remaining <= 0:
                        run["timed_out"] = True
                        run["cleanup_signals"] = stop_group(process)
                        break
                    try:
                        process.wait(timeout=min(1, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        pass
            except KeyboardInterrupt:
                run["interrupted"] = True
                run["cleanup_signals"] = stop_group(process)
            finally:
                # time can be killed while its UE child remains alive. Reap the
                # leader and clean any remaining group even after leader exit.
                cleanup = stop_group(process)
                if cleanup:
                    run.setdefault("cleanup_signals", []).extend(cleanup)
                run["exit_code"] = process.wait()
    after = cgroup_snapshot(cgroup)
    save(output / "cgroup-after.json", after)
    run["finished_at"] = utc_now()
    run["elapsed_seconds"] = round(time.monotonic() - started_clock, 3)
    run["cgroup_events_delta"] = {key: after["events"][key] - before["events"][key]
                                  for key in before["events"].keys() & after["events"].keys()}
    run["cgroup_local_events_delta"] = {key: after["local_events"][key] - before["local_events"][key]
                                        for key in before["local_events"].keys() & after["local_events"].keys()}
    time_text = read_optional(output / "memory.txt")
    rss = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", time_text or "")
    run["memory"] = {
        "sample_count": sample_count, "max_sampled_cgroup_memory_current_bytes": sampled_max,
        "time_max_resident_set_kbytes": int(rss.group(1)) if rss else None,
        "time_report_available": time_text is not None,
        "boundary": "Cgroup samples include every process and file cache, not UE alone; 1-second sampling may miss peaks. memory.peak is lifetime, not this run. GNU time max RSS is not simultaneous aggregate cgroup memory. Timeout can kill time before its final report is written. Exit -9/137 alone does not prove OOM; event deltas are shared-cgroup evidence, not per-process attribution.",
    }
    validation = validate_probe(output / "probe.json", project_directory)
    run["probe_validation"] = validation
    run["passed"] = (run["exit_code"] == 0 and not run["timed_out"] and not run["interrupted"]
                     and run["launch_error"] is None and validation["valid"] and rss is not None)
    run["status"] = "passed" if run["passed"] else "not_passed"
    run["scope"] = "Only real UE Python commandlet startup and API exposure; no Lyra build, asset edits, feature acceptance, or score."
    save(output / "run.json", run)
    save(output / "result.json", run)
    (output / "exit-code.txt").write_text(str(run["exit_code"]) + "\n", encoding="utf-8")
    print(json.dumps(run, ensure_ascii=False, indent=2))
    return 0 if run["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
