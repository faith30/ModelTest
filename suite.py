#!/usr/bin/env python3
"""Prepare, time, and publish a Lyra feature task. No model or UE is run here."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone


class SuiteError(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value=None):
    return (value or utc_now()).isoformat(timespec="seconds")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise SuiteError("Cannot read JSON {}: {}".format(path, exc)) from exc


def write_json(path, data):
    temporary = Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def git(*args, cwd=None, env=None):
    try:
        result = subprocess.run(
            ["git", *map(str, args)], cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace", check=False,
        )
    except OSError as exc:
        raise SuiteError("Cannot run Git: {}".format(exc)) from exc
    if result.returncode:
        details = (result.stderr.strip() or result.stdout.strip())[-6000:]
        raise SuiteError("git {} failed ({}):\n{}".format(args[0], result.returncode, details))
    return result.stdout.strip()


def kit_file(kit, relative):
    path = (kit / relative).resolve()
    if not path.is_relative_to(kit) or not path.is_file():
        raise SuiteError("Missing or invalid kit file: {}".format(relative))
    return path


def repo_path(value):
    path = str(value).replace("\\", "/")
    if not path or path.startswith("/") or ":" in path or ".." in path.split("/"):
        raise SuiteError("Invalid repository-relative path: {}".format(value))
    return path


def sidecar(workspace, suffix):
    return workspace.parent / (workspace.name + suffix)


def clean_head(workspace):
    if git("status", "--porcelain", "--untracked-files=all", cwd=workspace):
        raise SuiteError("Working tree is not clean. Review and commit your intended changes first; this tool never stages or commits files.")
    return git("rev-parse", "HEAD", cwd=workspace)


def check_lfs(workspace):
    print("Checking Git LFS objects and checkout...", flush=True)
    git("lfs", "fsck", cwd=workspace)
    count = 0
    for line in git("lfs", "ls-files", "--long", cwd=workspace).splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) ([*-]) (.+)", line)
        if not match:
            raise SuiteError("Unexpected Git LFS listing: {}".format(line))
        _, marker, name = match.groups()
        path = workspace / name
        if marker != "*" or not path.is_file():
            raise SuiteError("Git LFS file has not been downloaded: {}".format(name))
        with path.open("rb") as stream:
            if stream.read(128).startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise SuiteError("Git LFS pointer remains in checkout: {}".format(name))
        count += 1
    return count


def load_session(workspace):
    workspace = Path(workspace).expanduser().resolve()
    session_path = sidecar(workspace, ".session.json")
    session = read_json(session_path)
    if Path(session["workspace"]).resolve() != workspace:
        raise SuiteError("Session workspace does not match this directory.")
    return workspace, session_path, session


def prepare(args):
    metadata_path = Path(args.metadata).expanduser().resolve()
    kit = metadata_path.parent
    metadata = read_json(metadata_path)
    features = metadata["features"]
    if args.feature not in features:
        raise SuiteError("Unknown feature. Available: {}".format(", ".join(features)))
    feature = features[args.feature]
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}", args.name):
        raise SuiteError("Name must contain 1-64 letters, numbers, dots, underscores, or hyphens.")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", args.feature):
        raise SuiteError("Invalid feature name in metadata.")
    branch = "codex/deepseek-{}-{}".format(args.feature, args.name)
    git("check-ref-format", "--branch", branch)
    git("lfs", "version")
    expected = feature["starting_commit"].lower()
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise SuiteError("starting_commit must be a full 40-character Git SHA.")
    duration = metadata["wall_time_seconds"]
    if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
        raise SuiteError("wall_time_seconds must be a positive integer.")
    prompt_source = kit_file(kit, feature["prompt_file"])
    prompt_bytes = prompt_source.read_bytes()
    prompt_sha = hashlib.sha256(prompt_bytes).hexdigest()
    if feature.get("prompt_sha256") and prompt_sha != feature["prompt_sha256"].lower():
        raise SuiteError("Prompt SHA-256 does not match suite.json.")
    task_file = repo_path(feature["task_file"])
    protected = list(dict.fromkeys([task_file, *feature.get("protected_files", [])]))
    protected = [repo_path(path) for path in protected]
    root = Path(args.root).expanduser().resolve()
    workspace = root / (args.feature + "-" + args.name)
    for path in [workspace, sidecar(workspace, ".session.json"),
                 sidecar(workspace, ".prompt.txt"), sidecar(workspace, ".result.json")]:
        if path.exists():
            raise SuiteError("Refusing to overwrite existing path: {}".format(path))
    root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    print("Cloning {} into {}...".format(feature["branch"], workspace), flush=True)
    git("clone", "--single-branch", "--no-tags", "--branch", feature["branch"],
        metadata["repository"], workspace, env=env)
    actual = git("rev-parse", "HEAD", cwd=workspace)
    if actual != expected:
        raise SuiteError("Baseline SHA mismatch: expected {}, got {}. Leave this checkout unused.".format(expected, actual))
    if git("rev-list", "--count", "HEAD", cwd=workspace) != "1":
        raise SuiteError("Baseline must contain exactly one root commit; this checkout has history.")
    if git("rev-list", "--parents", "-n", "1", "HEAD", cwd=workspace).split() != [expected]:
        raise SuiteError("Baseline commit has a parent.")
    protected_blobs = {path: git("rev-parse", "HEAD:" + path, cwd=workspace) for path in protected}
    print("Downloading Git LFS content (this may take several minutes)...", flush=True)
    git("lfs", "pull", "--include=", "--exclude=", cwd=workspace)
    lfs_count = check_lfs(workspace)
    git("switch", "-c", branch, cwd=workspace)
    clean_head(workspace)
    git("remote", "remove", "origin", cwd=workspace)
    prompt_path = sidecar(workspace, ".prompt.txt")
    prompt_path.write_bytes(prompt_bytes)
    session = {
        "schema_version": 1, "feature": args.feature, "name": args.name,
        "model": metadata["model"], "workspace": str(workspace),
        "origin_url": metadata["repository"], "result_branch": branch,
        "baseline_branch": feature["branch"], "starting_commit": expected,
        "wall_time_seconds": duration, "prepared_at_utc": timestamp(),
        "prompt_file": str(prompt_path), "prompt_sha256": prompt_sha,
        "task_file": task_file, "protected_blobs": protected_blobs,
        "lfs_files_checked": lfs_count,
        "environment": {
            "system": platform.system(), "machine": platform.machine(),
            "python": platform.python_version(),
            "ue_executable_on_path": next((value for value in (
                shutil.which("UnrealEditor"), shutil.which("UnrealEditor-Cmd"),
                shutil.which("UE4Editor")) if value), None),
            "ue_compilation": "not_verified", "ue_runtime": "not_verified",
        },
        "notes": [
            "The origin remote was removed to reduce accidental access to other branches; this is not a security sandbox.",
            "No model, UE compilation, runtime test, or scoring was performed by prepare.",
        ],
    }
    write_json(sidecar(workspace, ".session.json"), session)
    print("Prepared: {}\nBaseline: {}\nLFS files checked: {}\nPrompt: {}".format(
        workspace, expected, lfs_count, prompt_path))
    print("Open ONLY this workspace in VS Code. When ready, run:\n  python3 {} start {}".format(
        Path(__file__).resolve(), workspace))
    print("UE compilation/runtime are NOT VERIFIED. Preparation does not start the model or the timer.")


def start(args):
    workspace, session_path, session = load_session(args.workspace)
    if session.get("started_at_utc"):
        raise SuiteError("This session was already started; the timer cannot be reset.")
    if clean_head(workspace) != session["starting_commit"]:
        raise SuiteError("The workspace must still be at its exact baseline before starting.")
    if git("branch", "--show-current", cwd=workspace) != session["result_branch"]:
        raise SuiteError("Check out the prepared result branch before starting.")
    now = utc_now()
    session["started_at_utc"] = timestamp(now)
    session["deadline_at_utc"] = timestamp(now + timedelta(seconds=session["wall_time_seconds"]))
    write_json(session_path, session)
    print("Started (UTC): {}\nDeadline (UTC): {}\nPrompt: {}".format(
        session["started_at_utc"], session["deadline_at_utc"], session["prompt_file"]))
    print("Paste the prompt into a fresh {} session now.".format(session["model"]))
    print("This records a deadline only. It DOES NOT automatically stop the VS Code agent; stop it manually at the deadline.")


def status(args):
    workspace, _, session = load_session(args.workspace)
    print("Workspace: {}\nHEAD: {}\nResult branch: {}".format(
        workspace, git("rev-parse", "HEAD", cwd=workspace), session["result_branch"]))
    print("Working tree: {}".format("dirty" if git("status", "--porcelain", cwd=workspace) else "clean"))
    if session.get("deadline_at_utc"):
        seconds = int((datetime.fromisoformat(session["deadline_at_utc"]) - utc_now()).total_seconds())
        print("Deadline (UTC): {}\nTimer: {}".format(session["deadline_at_utc"],
              "EXPIRED ({} seconds ago)".format(-seconds) if seconds < 0 else "{} seconds remaining".format(seconds)))
    else:
        print("Timer: not started")
    print("UE compilation/runtime: NOT VERIFIED; score: NOT EVALUATED")


def submit(args):
    workspace, _, session = load_session(args.workspace)
    if not session.get("started_at_utc"):
        raise SuiteError("Run start before working and submitting.")
    head = clean_head(workspace)
    if head == session["starting_commit"]:
        raise SuiteError("No result commit exists. Review and commit your changes yourself before submitting.")
    if git("branch", "--show-current", cwd=workspace) != session["result_branch"]:
        raise SuiteError("Check out the prepared result branch before submitting.")
    git("merge-base", "--is-ancestor", session["starting_commit"], head, cwd=workspace)
    for path, expected_blob in session["protected_blobs"].items():
        try:
            actual_blob = git("rev-parse", head + ":" + path, cwd=workspace)
        except SuiteError as exc:
            raise SuiteError("Protected task/baseline file was deleted: {}".format(path)) from exc
        if actual_blob != expected_blob:
            raise SuiteError("Protected task/baseline file was modified: {}".format(path))
    check_lfs(workspace)
    now = utc_now()
    elapsed = (now - datetime.fromisoformat(session["started_at_utc"])).total_seconds()
    deadline_passed = now > datetime.fromisoformat(session["deadline_at_utc"])
    print("Publishing {} to {}...".format(head, session["result_branch"]), flush=True)
    # Give the LFS hook a named remote for this command only. Persisting an origin
    # is unnecessary; an ordinary push still rejects non-fast-forward updates.
    git("-c", "remote.suite-submit.url=" + session["origin_url"],
        "push", "suite-submit", "HEAD:refs/heads/" + session["result_branch"], cwd=workspace)
    result = {
        "schema_version": 1, "feature": session["feature"], "model": session["model"],
        "repository": session["origin_url"], "result_branch": session["result_branch"],
        "starting_commit": session["starting_commit"], "result_commit": head,
        "prompt_sha256": session["prompt_sha256"], "started_at_utc": session["started_at_utc"],
        "deadline_at_utc": session["deadline_at_utc"], "submitted_at_utc": timestamp(now),
        "seconds_until_submission": round(elapsed, 3), "submitted_after_deadline": deadline_passed,
        "deadline_enforcement": "manual_only", "protected_files_unchanged": True,
        "ue_compilation": "not_verified", "ue_runtime": "not_verified", "score": None,
        "evaluation_status": "submitted_not_evaluated",
        "note": "Submission time does not prove when model work stopped. This tool does not establish build success, runtime behavior, or a score.",
    }
    result_path = sidecar(workspace, ".result.json")
    write_json(result_path, result)
    print("Published: {}\nResult record: {}".format(session["result_branch"], result_path))
    if deadline_passed:
        print("Submission occurred AFTER the recorded deadline; the result record marks this explicitly.")
    print("Submitted only. UE compilation/runtime: NOT VERIFIED. Score: NOT EVALUATED.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare", help="Clone and verify one fresh feature baseline")
    command.add_argument("feature")
    command.add_argument("--root", default="/workspace/lyra-runs")
    command.add_argument("--name", default="deepseek-r1")
    command.add_argument("--metadata", default=str(Path(__file__).resolve().with_name("suite.json")))
    command.set_defaults(action=prepare)
    for name, action, help_text in [
        ("start", start, "Record the task deadline; does not start or stop the model"),
        ("status", status, "Show Git and timer status"),
        ("submit", submit, "Push your committed result; does not build or score"),
    ]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("workspace")
        command.set_defaults(action=action)
    args = parser.parse_args(argv)
    try:
        args.action(args)
    except (SuiteError, OSError, KeyError, TypeError, ValueError) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
