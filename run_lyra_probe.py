#!/usr/bin/env python3
"""Load the actual compiled Lyra baseline in Linux UE; no functional score is inferred."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from headless_ue import doctor, positive_int, read_json
from run_editor_probe import (cgroup_directory, cgroup_snapshot, memory_sample,
                              read_optional, save, stop_group, utc_now)


ASSETS = (
    "/Game/DefaultGameData.DefaultGameData",
    "/ShooterExplorer/Input/Abilities/GA_Interact.GA_Interact",
    "/ShooterExplorer/Maps/L_InventoryTestMap.L_InventoryTestMap",
)
NATIVE_CLASS = "/Script/LyraGame.LyraGameplayAbility_Interact"
MODULES = ("LyraGame", "LyraEditor")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Generated only in the new evidence directory, never added to the Lyra project.
UE_SCRIPT = r'''import hashlib
import json
import os
from pathlib import Path
import re

def digest_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def main():
    config = json.loads(os.environ["LYRA_BASELINE_PROBE_CONFIG"])
    report = {"schema_version": 1, "probe": "real_lyra_baseline_load",
              "status": "running", "executed_in_real_unreal": False,
              "engine_version": None, "project_directory": None,
              "process_id": os.getpid(), "effective_uid": os.geteuid(),
              "executable": os.path.realpath("/proc/self/exe"),
              "native_class": None, "loaded_modules": {}, "assets": [],
              "boundary": "Actual baseline module/asset loading only. No save, gameplay, Experience activation, visual/audio acceptance, or score."}
    with open(config["output"], "x", encoding="utf-8") as stream:
        def checkpoint():
            stream.seek(0)
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.truncate()
            stream.flush()
        checkpoint()
        try:
            import unreal
            if os.geteuid() == 0:
                raise RuntimeError("Unreal must run as non-root")
            report["engine_version"] = str(unreal.SystemLibrary.get_engine_version())
            report["raw_project_directory"] = str(unreal.SystemLibrary.get_project_directory())
            if not report["raw_project_directory"].strip():
                raise RuntimeError("Unreal returned an empty project directory")
            report["project_directory"] = str(Path(report["raw_project_directory"]).resolve())
            if not re.match(r"^5\.8\.3(?:[-+ ]|$)", report["engine_version"]):
                raise RuntimeError("Unexpected actual engine version")
            if Path(report["project_directory"]).resolve() != Path(config["project_directory"]).resolve():
                raise RuntimeError("Unreal loaded a different project directory")
            if report["executable"] != os.path.realpath(config["editor"]):
                raise RuntimeError("Unexpected actual UE executable")
            native_class = unreal.load_class(None, config["native_class"])
            if native_class is None:
                raise RuntimeError("Lyra interaction native class failed to load")
            report["native_class"] = str(native_class.get_path_name())
            checkpoint()
            maps = Path("/proc/self/maps").read_text(encoding="utf-8")
            for name, expected in config["modules"].items():
                mapped = []
                for line in maps.splitlines():
                    parts = line.split(None, 5)
                    if len(parts) != 6 or "x" not in parts[1] or not parts[5].startswith("/"):
                        continue
                    path = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), parts[5])
                    if path.endswith(" (deleted)"):
                        continue
                    if os.path.realpath(path) == expected["path"]:
                        mapped.append(line)
                if not mapped:
                    raise RuntimeError("Project module has no executable mapping: " + name)
                actual_hash = digest_file(expected["path"])
                report["loaded_modules"][name] = {"path": expected["path"],
                                                   "sha256": actual_hash,
                                                   "executable_mapping_lines": mapped}
                if actual_hash != expected["sha256"]:
                    raise RuntimeError("Project module changed during probe: " + name)
                checkpoint()
            for asset_path in config["assets"]:
                asset = unreal.load_object(None, asset_path)
                if asset is None:
                    raise RuntimeError("Asset failed to load: " + asset_path)
                report["assets"].append({"requested_path": asset_path,
                                         "loaded_path": str(asset.get_path_name()),
                                         "class": str(asset.get_class().get_name())})
                checkpoint()
            report["status"] = "completed"
            report["executed_in_real_unreal"] = True
        except BaseException as error:
            report["status"] = "failed"
            report["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            checkpoint()
    print("LYRA_BASELINE_PROBE_COMPLETED " + config["output"])

if __name__ == "__main__":
    main()
'''


def validate_probe(path, config):
    problems, data = [], None
    try:
        data = read_json(path)
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1 or data.get("probe") != "real_lyra_baseline_load":
            problems.append("Invalid probe identity/schema")
        if data.get("status") != "completed" or data.get("executed_in_real_unreal") is not True or "error" in data:
            problems.append("Real Lyra probe did not complete")
        if not isinstance(data.get("engine_version"), str) or not re.match(r"^5\.8\.3(?:[-+ ]|$)", data["engine_version"]):
            problems.append("Actual UE version is not 5.8.3")
        if not isinstance(data.get("project_directory"), str) or Path(data["project_directory"]).resolve() != Path(config["project_directory"]).resolve():
            problems.append("Actual Lyra project directory mismatch")
        if type(data.get("process_id")) is not int or data["process_id"] <= 0 or type(data.get("effective_uid")) is not int or data["effective_uid"] != os.geteuid() or data["effective_uid"] == 0:
            problems.append("Invalid actual UE process/user evidence")
        if data.get("executable") != str(Path(config["editor"]).resolve()):
            problems.append("Actual UE executable mismatch")
        if data.get("native_class") != NATIVE_CLASS:
            problems.append("Lyra native interaction class was not loaded")
        if not isinstance(data.get("boundary"), str) or not data["boundary"]:
            problems.append("Missing diagnostic boundary")
        loaded = data.get("loaded_modules")
        if not isinstance(loaded, dict) or set(loaded) != set(MODULES):
            raise ValueError("missing LyraGame/LyraEditor module evidence")
        for name, expected in config["modules"].items():
            module = loaded[name]
            if not isinstance(module, dict) or module.get("path") != expected["path"] or module.get("sha256") != expected["sha256"] or sha256(Path(expected["path"])) != expected["sha256"]:
                problems.append("Loaded project module identity mismatch: " + name)
            mappings = module.get("executable_mapping_lines") if isinstance(module, dict) else None
            if not isinstance(mappings, list) or not mappings:
                problems.append("Missing executable module mapping: " + name)
                continue
            for line in mappings:
                parts = line.split(None, 5) if isinstance(line, str) else []
                if len(parts) != 6 or "x" not in parts[1]:
                    problems.append("Invalid executable module mapping: " + name)
                    continue
                mapped_path = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), parts[5])
                if mapped_path.endswith(" (deleted)") or not Path(mapped_path).is_absolute() or str(Path(mapped_path).resolve()) != expected["path"]:
                    problems.append("Executable mapping names a different module: " + name)
        assets = data.get("assets")
        if not isinstance(assets, list) or len(assets) != len(ASSETS):
            raise ValueError("missing required baseline asset evidence")
        for item, expected_path in zip(assets, ASSETS):
            if not isinstance(item, dict) or item.get("requested_path") != expected_path or item.get("loaded_path") != expected_path or not isinstance(item.get("class"), str) or not item["class"]:
                problems.append("Required baseline asset did not load: " + expected_path)
    except (OSError, ValueError, TypeError) as error:
        problems.append("Missing or invalid probe.json: " + str(error))
    return {"valid": not problems, "problems": problems, "probe": data}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True, help="actual compiled Lyra.uproject")
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory; never overwritten")
    parser.add_argument("--timeout", type=positive_int, default=600)
    args = parser.parse_args(argv)
    preflight = doctor(args.engine, args.project)
    project = Path(preflight["project"])
    modules = {}
    for name in MODULES:
        path = project.parent / "Binaries/Linux" / ("libUnrealEditor-" + name + ".so")
        if not path.is_file():
            preflight["problems"].append("Build the real LyraEditor target first; missing " + str(path))
        else:
            try:
                modules[name] = {"path": str(path.resolve()), "sha256": sha256(path)}
            except OSError as error:
                preflight["problems"].append("Cannot read project module: " + str(error))
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
    except OSError as error:
        parser.error("cannot create evidence directory: " + str(error))
    save(output / "doctor.json", preflight)
    script = output / "lyra_probe_inside_ue.py"
    script.write_text(UE_SCRIPT, encoding="utf-8")
    config = {"output": str(output / "probe.json"), "project_directory": str(project.parent),
              "editor": preflight["editor"], "native_class": NATIVE_CLASS,
              "assets": list(ASSETS), "modules": modules}
    save(output / "probe-config.json", config)
    command = ["/usr/bin/time", "-v", "-o", str(output / "memory.txt"), preflight["editor"], str(project),
               "-run=pythonscript", "-EnablePlugins=PythonScriptPlugin,EditorScriptingUtilities",
               "-script=" + str(script), "-unattended", "-nullrhi", "-nosound", "-NoSourceControl",
               "-abslog=" + str(output / "ue.log")]
    env = os.environ.copy()
    env.update(LYRA_BASELINE_PROBE_CONFIG=json.dumps(config), LC_ALL="C")
    cgroup = cgroup_directory()
    before = cgroup_snapshot(cgroup)
    save(output / "cgroup-before.json", before)
    started = time.monotonic()
    run = {"schema_version": 1, "status": "running", "passed": False, "command": command,
           "cwd": str(project.parent), "started_at": utc_now(), "timeout_seconds": args.timeout,
           "exit_code": None, "timed_out": False, "interrupted": False, "launch_error": None,
           "probe_script_sha256": sha256(script), "project_file_sha256": sha256(project)}
    save(output / "run.json", run)
    print("Running actual Lyra baseline loading; evidence: " + str(output), flush=True)
    sampled_max, sample_count = None, 0
    with (output / "stdout.log").open("wb") as log, (output / "memory-samples.jsonl").open("w", encoding="utf-8") as samples:
        try:
            process = subprocess.Popen(command, cwd=project.parent, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as error:
            run["launch_error"] = str(error)
        else:
            run["time_process_id"] = process.pid
            save(output / "run.json", run)
            try:
                while True:
                    sample = memory_sample(cgroup, started)
                    samples.write(json.dumps(sample) + "\n")
                    samples.flush()
                    sample_count += 1
                    current = sample["memory_current_bytes"]
                    if current is not None:
                        sampled_max = max(sampled_max or 0, current)
                    remaining = args.timeout - (time.monotonic() - started)
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
                cleanup = stop_group(process)
                if cleanup:
                    run.setdefault("cleanup_signals", []).extend(cleanup)
                run["exit_code"] = process.wait()
    after = cgroup_snapshot(cgroup)
    save(output / "cgroup-after.json", after)
    run["finished_at"] = utc_now()
    run["elapsed_seconds"] = round(time.monotonic() - started, 3)
    for key in ("events", "local_events"):
        run["cgroup_" + key + "_delta"] = {name: after[key][name] - before[key][name]
                                            for name in before[key].keys() & after[key].keys()}
    time_text = read_optional(output / "memory.txt")
    rss = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", time_text or "")
    run["memory"] = {"sample_count": sample_count, "max_sampled_cgroup_memory_current_bytes": sampled_max,
                     "time_max_resident_set_kbytes": int(rss.group(1)) if rss else None,
                     "time_report_available": time_text is not None,
                     "boundary": "Cgroup includes all processes and file cache; samples can miss peaks. memory.peak is lifetime, not this run. GNU time RSS is not aggregate container memory and can be absent after timeout. Exit -9/137 alone is not proof of OOM; event deltas do not attribute an OOM to a specific process."}
    validation = validate_probe(output / "probe.json", config)
    run["probe_validation"] = validation
    run["project_file_unchanged"] = sha256(project) == run["project_file_sha256"]
    run["probe_script_unchanged"] = sha256(script) == run["probe_script_sha256"]
    run["passed"] = (run["exit_code"] == 0 and not run["timed_out"] and not run["interrupted"]
                     and run["launch_error"] is None and validation["valid"] and rss is not None
                     and run["project_file_unchanged"] and run["probe_script_unchanged"])
    run["status"] = "passed" if run["passed"] else "not_passed"
    run["scope"] = "Actual Lyra baseline project, native modules and specified asset loading only. No gameplay, Experience activation, functional acceptance, asset saving, or benchmark score."
    save(output / "run.json", run)
    save(output / "result.json", run)
    (output / "exit-code.txt").write_text(str(run["exit_code"]) + "\n", encoding="utf-8")
    print(json.dumps(run, ensure_ascii=False, indent=2))
    return 0 if run["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
