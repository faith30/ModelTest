#!/usr/bin/env python3
"""Score evaluator-produced UE Automation reports for the 23 Lyra death cases.

Schema verified against UE 5.8 AutomationControllerManager.h,
AutomationDeviceClusterManager.h, AutomationState.h and JsonObjectConverter.cpp.
No candidate code or scripts are executed by this parser.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import uuid


PREFIX = "Lyra.Benchmark.Death."
MANIFEST = {
    "DirectFinished": ["SkipStartedNotification", "DuplicateFinishedSnapshot",
                       "ThenDuplicateMethods", "AfterPrematureFinish"],
    "StepSequence": ["ReplicatedStart", "ReplicatedStartAndFinish",
                     "LocalStartReplicatedFinish", "ReplicatedStartLocalFinish"],
    "Idempotence": ["FinishBeforeStart", "DuplicateStart", "DuplicateFinish",
                    "StartAfterFinished", "RepeatedSequence"],
    "PredictionAhead": ["StartedReceivesNotDead", "FinishedReceivesStarted",
                        "FinishedReceivesNotDead", "RepeatedOlderState", "TwoOlderStates"],
    "ASCNull": ["LocalSequence", "DirectFinished", "FinishBeforeStart",
                "DuplicateMethods", "PredictionAhead"],
}
EXPECTED_PATHS = tuple(PREFIX + group + "." + case
                       for group, cases in MANIFEST.items() for case in cases)
SCOPE = ("Real UE Automation execution of ULyraHealthComponent with a real UWorld, "
         "ASC, gameplay tags and dynamic delegates. OnRep_DeathState is driven "
         "directly by the fixture; this does not prove multi-machine network "
         "replication, gameplay presentation, or complete-game correctness.")
PROVENANCE = ("The report and build manifest must come from the trusted evaluator. "
              "This parser checks their structure and consistency; metadata hashes "
              "alone do not independently attest a binary or remote execution.")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def valid_sha(value, lengths):
    return isinstance(value, str) and len(value) in lengths and bool(re.fullmatch(r"[0-9a-fA-F]+", value))


def count(value):
    return type(value) is int and value >= 0


def instance_id(value):
    if not isinstance(value, str):
        raise ValueError("Device instance must be a GUID string")
    return str(uuid.UUID(value))


def score_report(report, build, candidate_sha, allow_non_linux_calibration=False):
    problems = []
    result = {"schema_version": 1, "scope": SCOPE, "provenance_boundary": PROVENANCE,
              "candidate_sha": candidate_sha, "calibration_only": bool(allow_non_linux_calibration),
              "is_final": False, "final_pass": False, "valid_evidence": False,
              "status": "invalid_evidence", "score": 0, "observed_case_score": 0,
              "expected_case_count": len(EXPECTED_PATHS), "passed_case_count": 0,
              "groups": [], "problems": problems, "missing_tests": [],
              "duplicate_tests": [], "unexpected_tests": [], "incomplete_tests": []}
    if not valid_sha(candidate_sha, (40, 64)):
        problems.append("--candidate-sha must be a complete hexadecimal Git commit ID")
    if not isinstance(build, dict):
        problems.append("Build manifest must be an object")
        build = {}
    result["build_manifest"] = build
    if not valid_sha(build.get("candidate_sha"), (40, 64)) or build.get("candidate_sha", "").lower() != candidate_sha.lower():
        problems.append("Build manifest candidate_sha does not match the evaluated candidate")
    if type(build.get("build_exit_code")) is not int or build.get("build_exit_code") != 0:
        problems.append("Build did not demonstrably succeed: build_exit_code must be integer 0")
    for field in ("source_sha256", "binary_sha256", "build_log_sha256"):
        if not valid_sha(build.get(field), (64,)):
            problems.append(f"Build manifest requires a valid {field}")
    if not isinstance(build.get("engine_version"), str) or not build.get("engine_version", "").strip():
        problems.append("Build manifest requires engine_version")
    target = build.get("target_platform")
    if not isinstance(target, str) or not target.strip():
        problems.append("Build manifest requires target_platform")
    elif not allow_non_linux_calibration and target != "Linux":
        problems.append("Final evaluation requires target_platform=Linux")

    if not isinstance(report, dict):
        problems.append("UE index.json must be an object")
        report = {}
    devices = report.get("devices")
    device_map = {}
    if not isinstance(devices, list) or not devices:
        problems.append("UE report requires a nonempty devices array")
        devices = []
    for index, device in enumerate(devices):
        if not isinstance(device, dict):
            problems.append(f"devices[{index}] must be an object")
            continue
        try:
            identifier = instance_id(device.get("instance"))
        except (ValueError, AttributeError):
            problems.append(f"devices[{index}].instance is not a valid GUID")
            continue
        platform = device.get("platform")
        if not isinstance(platform, str) or not platform.strip():
            problems.append(f"devices[{index}] has no platform")
            continue
        if identifier in device_map:
            problems.append(f"Duplicate device instance: {identifier}")
        device_map[identifier] = platform
    result["device_platforms"] = sorted(set(device_map.values()))

    tests = report.get("tests")
    if not isinstance(tests, list):
        problems.append("UE report requires a tests array")
        tests = []
    if not tests:
        problems.append("UE report contains zero tests")
    buckets = {}
    for index, item in enumerate(tests):
        if not isinstance(item, dict) or not isinstance(item.get("fullTestPath"), str):
            problems.append(f"tests[{index}] must have fullTestPath")
            continue
        buckets.setdefault(item["fullTestPath"], []).append(item)
    result["missing_tests"] = sorted(set(EXPECTED_PATHS) - set(buckets))
    result["duplicate_tests"] = sorted(path for path, entries in buckets.items() if len(entries) != 1)
    result["unexpected_tests"] = sorted(set(buckets) - set(EXPECTED_PATHS))
    for field in ("missing_tests", "duplicate_tests", "unexpected_tests"):
        if result[field]:
            problems.append(f"{field}: {len(result[field])}")

    state_counts = Counter()
    success_with_warnings = 0
    used_platforms = set()
    for group, case_names in MANIFEST.items():
        group_result = {"name": group, "maximum": 20, "observed_score": 0,
                        "passed": 0, "total": len(case_names), "cases": []}
        for case_name in case_names:
            path = PREFIX + group + "." + case_name
            entries = buckets.get(path, [])
            case_result = {"full_test_path": path, "passed": False, "state": None,
                           "errors": None, "warnings": None, "platforms": []}
            if len(entries) != 1:
                case_result["reason"] = "missing" if not entries else "duplicate"
                group_result["cases"].append(case_result)
                continue
            item = entries[0]
            state, errors, warnings = item.get("state"), item.get("errors"), item.get("warnings")
            case_result.update({"state": state, "errors": errors, "warnings": warnings})
            if state not in ("Success", "Fail"):
                result["incomplete_tests"].append(path)
                problems.append(f"{path}: nonterminal or skipped state {state!r}")
            if isinstance(state, str):
                state_counts[state] += 1
            if not count(errors) or not count(warnings):
                problems.append(f"{path}: errors and warnings must be nonnegative integers")
            if state == "Success" and count(warnings) and warnings > 0:
                success_with_warnings += 1
            references = item.get("deviceInstance")
            platforms = []
            if not isinstance(references, list) or not references:
                problems.append(f"{path}: missing deviceInstance array")
            else:
                for reference in references:
                    try:
                        identifier = instance_id(reference)
                    except (ValueError, AttributeError):
                        problems.append(f"{path}: invalid deviceInstance GUID")
                        continue
                    if identifier not in device_map:
                        problems.append(f"{path}: references an unreported device")
                    else:
                        platforms.append(device_map[identifier])
            case_result["platforms"] = platforms
            used_platforms.update(platforms)
            if not allow_non_linux_calibration and any(not value.lower().startswith("linux") for value in platforms):
                problems.append(f"{path}: actual test device is not Linux")
            case_result["passed"] = state == "Success" and count(errors) and errors == 0 and count(warnings)
            if case_result["passed"]:
                group_result["passed"] += 1
                result["passed_case_count"] += 1
            else:
                case_result["reason"] = "state must be Success and errors must be 0"
            group_result["cases"].append(case_result)
        group_result["observed_score"] = round(20 * group_result["passed"] / group_result["total"], 2)
        result["groups"].append(group_result)
    result["used_test_platforms"] = sorted(used_platforms)
    result["observed_case_score"] = round(sum(group["observed_score"] for group in result["groups"]), 2)

    # UE stores skipped tests separately from these aggregate counters. Skips are
    # rejected above; the remaining counters must describe this exact manifest.
    expected_counters = {"succeeded": state_counts["Success"] - success_with_warnings,
                         "succeededWithWarnings": success_with_warnings,
                         "failed": state_counts["Fail"], "notRun": 0, "inProcess": 0}
    for field, expected_value in expected_counters.items():
        if not count(report.get(field)) or report.get(field) != expected_value:
            problems.append(f"UE summary {field} must be {expected_value}, got {report.get(field)!r}")
    if not used_platforms:
        problems.append("No actual test execution platform established")
    result["valid_evidence"] = not problems
    if result["valid_evidence"]:
        result["score"] = result["observed_case_score"]
        result["is_final"] = not allow_non_linux_calibration
        result["final_pass"] = result["is_final"] and result["score"] == 100
        result["status"] = ("final_" if result["is_final"] else "calibration_") + ("pass" if result["score"] == 100 else "fail")
    return result


def strict_load(path):
    def pairs(entries):
        value = {}
        for key, item in entries:
            if key in value:
                raise ValueError("Duplicate JSON key: " + key)
            value[key] = item
        return value

    def reject_constant(value):
        raise ValueError("Nonfinite JSON value: " + value)

    data = Path(path).read_bytes()
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=reject_constant), digest(data)


def write_result(output, result):
    output.mkdir(parents=True, exist_ok=True)
    (output / "score.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Lyra real UE evaluation", "", f"Status: **{result['status']}**",
             f"Valid score: **{result['score']}/100**", f"Final pass: **{result['final_pass']}**", "",
             "Calibration only; **not a final Linux result**." if result["calibration_only"] else "Final evaluation requires complete Linux runtime and build evidence.", "",
             SCOPE, "", PROVENANCE, "", f"Candidate: `{result['candidate_sha']}`",
             f"Cases passed: {result['passed_case_count']}/{result['expected_case_count']}", "",
             "| Group | Observed points | Passed |", "| --- | ---: | ---: |"]
    for group in result["groups"]:
        lines.append(f"| {group['name']} | {group['observed_score']}/20 | {group['passed']}/{group['total']} |")
    if not result["valid_evidence"]:
        lines += ["", "Observed case points are diagnostic only; evidence validation failed.", ""]
        lines += ["- " + problem for problem in result["problems"]]
    for field in ("missing_tests", "duplicate_tests", "unexpected_tests", "incomplete_tests"):
        if result[field]:
            lines += ["", field + ":", ""] + ["- " + path for path in result[field]]
    failed = [case for group in result["groups"] for case in group["cases"] if not case["passed"]]
    if failed:
        lines += ["", "Cases without credit:", ""]
        lines += [f"- {case['full_test_path']}: {case.get('reason', case['state'])}" for case in failed]
    (output / "score.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="UE Automation index.json")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--build-manifest", type=Path, required=True)
    parser.add_argument("--allow-non-linux-calibration", action="store_true",
                        help="Permit local platform calibration; always marks not_final")
    args = parser.parse_args(argv)
    load_errors = []
    inputs = []
    for path in (args.report, args.build_manifest):
        try:
            inputs.append(strict_load(path))
        except (OSError, UnicodeError, ValueError, RecursionError) as error:
            load_errors.append(f"Unable to read {path}: {error}")
            inputs.append(({}, None))
    result = score_report(inputs[0][0], inputs[1][0], args.candidate_sha, args.allow_non_linux_calibration)
    result["problems"].extend(load_errors)
    result["report_sha256"] = inputs[0][1]
    result["build_manifest_sha256"] = inputs[1][1]
    result["scorer_sha256"] = digest(Path(__file__).read_bytes())
    if load_errors:
        result.update(valid_evidence=False, is_final=False, final_pass=False, status="invalid_evidence", score=0)
    write_result(args.output, result)
    print(f"{result['status']}: {result['score']}/100; final_pass={result['final_pass']}")
    print(str(args.output.resolve() / "score.md"))
    if not result["valid_evidence"]:
        return 2
    return 0 if result["score"] == 100 else 1


if __name__ == "__main__":
    raise SystemExit(main())
