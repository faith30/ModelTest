#!/usr/bin/env python3
"""Run a staged Linux LyraServer and gate its trusted UE report score.

Run as a non-root Linux user. The package and build manifest must be produced
by the evaluator; hashes bind these inputs but are not remote attestation.
This wrapper does not compile, repair candidate code, or invent UE results.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import signal
import subprocess
import sys
import time


EXPECTED_CASE_COUNT = 23
TEST_PREFIX = "Lyra.Benchmark.Death"
CONFIG_OVERRIDES = (
    "-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GameInstanceClass=/Script/LyraGame.LyraGameInstance",
    "-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase",
    "-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultServerGameMode=/Script/Engine.GameModeBase",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_json(data):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"Nonfinite JSON value: {value}")

    return json.loads(data.decode("utf-8-sig"),
                      object_pairs_hook=unique_pairs, parse_constant=reject_constant)


def load_json(path):
    return parse_json(path.read_bytes())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_environment():
    if platform.system() != "Linux" or not hasattr(os, "geteuid"):
        raise ValueError("This runner requires Linux; local Windows runs are calibration only.")
    if os.geteuid() == 0:
        raise ValueError(
            "Run this wrapper as a non-root Linux user. UE x86_64 rejects root "
            "before main() (UnixPlatformMemory.cpp, UE_DO_ROOT_PRIVILEGE_CHECK); "
            "a command-line AllowRoot flag does not bypass that check."
        )
    if platform.machine().lower() not in ("x86_64", "amd64"):
        raise ValueError("The staged target must run on Linux x86_64.")


def package_file(package_root, relative_name):
    if not isinstance(relative_name, str) or not relative_name.strip():
        raise ValueError("Build manifest requires binary_relpath relative to the LinuxServer directory")
    relative = PurePosixPath(relative_name.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts or ":" in relative_name:
        raise ValueError("Package file paths must stay inside --package-root")
    resolved = (package_root / Path(*relative.parts)).resolve(strict=True)
    if not resolved.is_relative_to(package_root) or not resolved.is_file():
        raise ValueError("Package file must resolve to a regular file inside --package-root")
    return resolved, relative.as_posix()


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("Build manifest must be an object")
    for field, pattern in (
        ("candidate_sha", r"(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})"),
        ("source_sha256", r"[a-fA-F0-9]{64}"),
        ("binary_sha256", r"[a-fA-F0-9]{64}"),
        ("build_log_sha256", r"[a-fA-F0-9]{64}"),
    ):
        if not isinstance(manifest.get(field), str) or not re.fullmatch(pattern, manifest[field]):
            raise ValueError(f"Build manifest requires a valid {field}")
    if type(manifest.get("build_exit_code")) is not int or manifest["build_exit_code"] != 0:
        raise ValueError("Build manifest must record build_exit_code=0")
    if manifest.get("target_platform") != "Linux":
        raise ValueError("Build manifest must record target_platform=Linux")
    if not isinstance(manifest.get("engine_version"), str) or not manifest["engine_version"].strip():
        raise ValueError("Build manifest requires engine_version")


def inspect_package(package_root, manifest):
    binary, relative_binary = package_file(package_root, manifest.get("binary_relpath"))
    launcher, _ = package_file(package_root, "LyraServer.sh")
    with binary.open("rb") as source:
        header = source.read(20)
    if (len(header) != 20 or header[:6] != b"\x7fELF\x02\x01"
            or int.from_bytes(header[16:18], "little") not in (2, 3)
            or int.from_bytes(header[18:20], "little") != 62):
        raise ValueError("Manifest binary is not an ELF64 little-endian x86_64 executable")
    binary_hash = file_sha256(binary)
    if binary_hash != manifest["binary_sha256"].lower():
        raise ValueError("Staged binary SHA256 does not match the build manifest")
    # UE's staged shell entry invokes this exact quoted path and forwards "$@".
    # Checking the invocation avoids silently hashing an unrelated staged ELF.
    invocation = r'^\s*"\$UE_PROJECT_ROOT/' + re.escape(relative_binary) + r'"\s+[^\n]*"\$@"\s*;?\s*$'
    if not re.search(invocation, launcher.read_text(encoding="utf-8-sig"), re.MULTILINE):
        raise ValueError("LyraServer.sh does not invoke the manifest binary using the expected UE staged launcher form")
    launcher_hash = file_sha256(launcher)
    if "launcher_sha256" in manifest and str(manifest["launcher_sha256"]).lower() != launcher_hash:
        raise ValueError("Staged launcher SHA256 does not match launcher_sha256")
    return binary, launcher, binary_hash, launcher_hash


def stop_process_group(process):
    """Terminate the whole session, including children left behind by sh."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # The shell may exit before its children; always kill any remaining group.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_process(command, cwd, log_path, timeout):
    started = utc_now()
    started_clock = time.monotonic()
    result = {"command": command, "cwd": str(cwd), "started_at": started,
              "exit_code": None, "timed_out": False, "interrupted": False,
              "launch_error": None}
    with log_path.open("wb") as log:
        try:
            process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        except OSError as error:
            result["launch_error"] = str(error)
        else:
            result["process_group_id"] = process.pid
            try:
                result["exit_code"] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                result["timed_out"] = True
                stop_process_group(process)
                result["exit_code"] = process.returncode
            except KeyboardInterrupt:
                result["interrupted"] = True
                stop_process_group(process)
                result["exit_code"] = process.returncode
    result["finished_at"] = utc_now()
    result["elapsed_seconds"] = round(time.monotonic() - started_clock, 3)
    result["stdout_sha256"] = file_sha256(log_path)
    return result


def completion_codes(log_path):
    codes = []
    pattern = re.compile(r"\*{4} TEST COMPLETE\. EXIT CODE: (-?\d+) \*{4}")
    with log_path.open("r", encoding="utf-8", errors="replace") as log:
        for line in log:
            codes.extend(int(match) for match in pattern.findall(line))
    return codes


def gate_result(runtime, scorer_run, report_score, integrity_problems):
    problems = list(integrity_problems)
    status = "invalid_evidence"
    result = {"schema_version": 1, "candidate_sha": runtime["candidate_sha"],
              "status": status, "valid_evidence": False, "is_final": False,
              "final_pass": False, "score": 0, "expected_case_count": EXPECTED_CASE_COUNT,
              "runtime_exit_code": runtime["exit_code"], "problems": problems,
              "groups": [],
              "scope": "Real Linux UE Automation execution; this does not prove multi-machine replication or game presentation.",
              "provenance_boundary": "Evaluator-produced build and report required. File hashes do not independently attest execution.",
              "report_score_path": "report-score/score.json", "runtime_path": "runtime.json"}
    if runtime["timed_out"]:
        status = "runtime_timeout"
        problems.append("UE exceeded the timeout; the whole process group was terminated")
    elif runtime["interrupted"]:
        status = "runtime_interrupted"
        problems.append("UE run was interrupted")
    elif runtime["launch_error"]:
        status = "runtime_launch_failed"
        problems.append("UE launcher could not start: " + runtime["launch_error"])
    elif runtime["exit_code"] not in (0, 255):
        status = "runtime_crash_or_error"
        problems.append(f"Unexpected UE process exit code: {runtime['exit_code']}")

    if not isinstance(report_score, dict):
        report_score = {}
        problems.append("Trusted scorer did not produce a readable score.json")
    result["observed_case_score"] = report_score.get("observed_case_score", 0)
    result["passed_case_count"] = report_score.get("passed_case_count", 0)
    if report_score.get("valid_evidence") is not True:
        problems.append("UE report/build evidence did not pass the trusted scorer")
    if report_score.get("is_final") is not True or report_score.get("calibration_only") is not False:
        problems.append("Scorer result is not a final Linux evaluation")
    groups = report_score.get("groups", [])
    cases = [case for group in groups if isinstance(group, dict)
             for case in group.get("cases", [])] if isinstance(groups, list) else []
    if (report_score.get("expected_case_count") != EXPECTED_CASE_COUNT
            or len(cases) != EXPECTED_CASE_COUNT
            or any(not isinstance(case, dict) or case.get("state") not in ("Success", "Fail") for case in cases)):
        problems.append("A complete terminal report for all 23 fixed cases is required")
    failed_cases = sum(case.get("passed") is not True for case in cases if isinstance(case, dict))
    if scorer_run is None or scorer_run.get("timed_out") or scorer_run.get("interrupted") or scorer_run.get("launch_error"):
        problems.append("Trusted scorer did not finish normally")
    elif scorer_run["exit_code"] != (1 if failed_cases else 0):
        problems.append(f"Trusted scorer exit code is inconsistent with the report: {scorer_run['exit_code']}")

    expected_exit = 255 if failed_cases else 0
    expected_marker = -1 if failed_cases else 0
    if runtime["exit_code"] != expected_exit:
        problems.append(f"UE exit code must be {expected_exit} for the observed case results")
    if runtime.get("automation_completion_codes") != [expected_marker]:
        problems.append("UE stdout must contain exactly one matching Automation TEST COMPLETE marker")
        if runtime["exit_code"] == 255 and status == "invalid_evidence":
            status = "runtime_crash_or_error"
    if not problems:
        result.update(valid_evidence=True, is_final=True,
                      final_pass=not failed_cases, score=report_score["score"],
                      status="final_test_failure" if failed_cases else "final_pass")
    else:
        result["status"] = status
    if isinstance(groups, list):
        for group in groups:
            if isinstance(group, dict):
                group_result = dict(group)
                group_result["score"] = group.get("observed_score", 0) if result["valid_evidence"] else 0
                result["groups"].append(group_result)
    return result


def write_summary(output, result):
    write_json(output / "result.json", result)
    lines = ["# Lyra Linux runtime evaluation", "",
             f"Status: **{result['status']}**", "",
             f"Valid score: **{result['score']}/100**", "",
             f"Final pass: **{result['final_pass']}**", "",
             f"Candidate: `{result['candidate_sha']}`", "",
             f"UE exit code: `{result['runtime_exit_code']}`", "",
             "The authoritative runtime-gated result is result.json. The report-score directory contains scorer diagnostics only.", "",
             result["scope"], "", result["provenance_boundary"]]
    if result["groups"]:
        lines += ["", "| Group | Valid points | Observed points | Cases passed |",
                  "| --- | ---: | ---: | ---: |"]
        for group in result["groups"]:
            lines.append(f"| {group.get('name')} | {group['score']}/{group.get('maximum')} | "
                         f"{group.get('observed_score')} | {group.get('passed')}/{group.get('total')} |")
    if result["problems"]:
        lines += ["", "Evidence problems:", ""] + ["- " + item for item in result["problems"]]
    (output / "result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, required=True, help="Staged LinuxServer directory")
    parser.add_argument("--build-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New output directory; must not exist")
    parser.add_argument("--score-script", type=Path, default=Path(__file__).with_name("score_ue_report.py"),
                        help="Fixed trusted evaluator scorer; never a candidate-provided script")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    try:
        check_environment()
        if not 0 < args.timeout <= 86400:
            raise ValueError("--timeout must be positive and at most 86400 seconds")
        package_root = args.package_root.resolve(strict=True)
        if not package_root.is_dir():
            raise ValueError("--package-root must be a directory")
        build_path = args.build_manifest.resolve(strict=True)
        build_bytes = build_path.read_bytes()
        manifest = parse_json(build_bytes)
        manifest_hash = hashlib.sha256(build_bytes).hexdigest()
        validate_manifest(manifest)
        binary, launcher, binary_hash, launcher_hash = inspect_package(package_root, manifest)
        scorer = args.score_script.resolve(strict=True)
        if not scorer.is_file() or scorer.suffix != ".py" or scorer.is_relative_to(package_root):
            raise ValueError("--score-script must be a trusted Python file outside the staged package")
        scorer_hash = file_sha256(scorer)
        output = args.output.resolve()
        if output.exists() or args.output.is_symlink():
            raise ValueError("--output already exists; choose a new run directory (no reports are overwritten)")
        if output.is_relative_to(package_root):
            raise ValueError("--output must be outside the staged package")
        # mkdir is intentionally exclusive, including when another runner races us.
        output.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        print(f"Preflight failed: {error}", file=sys.stderr)
        return 2

    manifest_copy = output / "build-manifest.json"
    manifest_copy.write_bytes(build_bytes)
    report_dir = output / "ue-report"
    report_dir.mkdir()
    log_path = output / "stdout.log"
    ue_log = output / "ue.log"
    command = ["sh", str(launcher), "/Engine/Maps/Entry?game=/Script/Engine.GameModeBase",
               "-nullrhi", "-nosound", "-unattended", "-stdout", "-FullStdOutLogOutput",
               *CONFIG_OVERRIDES,
               f"-ExecCmds=Automation RunTests StartsWith:{TEST_PREFIX}; Quit",
               f"-ReportExportPath={report_dir}", f"-abslog={ue_log}"]
    runtime = run_process(command, package_root, log_path, args.timeout)
    runtime.update(schema_version=1, candidate_sha=manifest["candidate_sha"],
                   platform=platform.uname()._asdict(), uid=os.geteuid(),
                   package_root=str(package_root), binary_path=str(binary),
                   binary_relpath=manifest["binary_relpath"], binary_sha256=binary_hash,
                   launcher_sha256=launcher_hash, scorer_path=str(scorer), scorer_sha256=scorer_hash,
                   build_manifest_sha256=manifest_hash,
                   runner_sha256=file_sha256(Path(__file__).resolve()), timeout_seconds=args.timeout,
                   automation_completion_codes=completion_codes(log_path))
    integrity_problems = []
    for name, path, expected_hash in (("binary", binary, binary_hash), ("launcher", launcher, launcher_hash),
                                      ("scorer", scorer, scorer_hash), ("build_manifest", manifest_copy, manifest_hash)):
        try:
            actual = file_sha256(path)
            runtime[name + "_sha256_after_run"] = actual
            if actual != expected_hash:
                integrity_problems.append(f"{name} changed during the UE run")
        except OSError as error:
            integrity_problems.append(f"Unable to recheck {name}: {error}")
    for name, path in (("ue_log", ue_log), ("report", report_dir / "index.json")):
        runtime[name + "_sha256"] = file_sha256(path) if path.is_file() else None

    scorer_run = None
    report_score = None
    # Never execute a scorer that changed while the candidate process ran.
    if runtime.get("scorer_sha256_after_run") == scorer_hash and not runtime["interrupted"]:
        scorer_command = [sys.executable, str(scorer), "--report", str(report_dir / "index.json"),
                          "--output", str(output / "report-score"),
                          "--candidate-sha", manifest["candidate_sha"],
                          "--build-manifest", str(manifest_copy)]
        scorer_run = run_process(scorer_command, scorer.parent, output / "scorer.log", 60)
        try:
            report_score = load_json(output / "report-score" / "score.json")
        except (OSError, ValueError, UnicodeError, RecursionError) as error:
            integrity_problems.append(f"Unable to read scorer output: {error}")
    runtime["scorer_run"] = scorer_run
    write_json(output / "runtime.json", runtime)
    result = gate_result(runtime, scorer_run, report_score, integrity_problems)
    result["runtime_sha256"] = file_sha256(output / "runtime.json")
    result["report_sha256"] = runtime["report_sha256"]
    result["binary_sha256"] = binary_hash
    write_summary(output, result)
    print(f"{result['status']}: valid_evidence={result['valid_evidence']}; score={result['score']}/100")
    print(output / "result.json")
    if not result["valid_evidence"]:
        return 2
    return 0 if result["final_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
