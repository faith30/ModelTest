#!/usr/bin/env python3
"""Organiser-owned Linux CLI time budget and descendant cleanup; never a grader."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from build_process_tree import BuildProcessTree


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def git_snapshot(workspace):
    # Query this checkout, regardless of inherited Git routing variables.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_OPTIONAL_LOCKS"] = "0"

    def git(*arguments):
        result = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(workspace), *arguments],
            env=environment, capture_output=True, text=True, timeout=30, check=True)
        return result.stdout.rstrip("\n")

    top = Path(git("rev-parse", "--show-toplevel")).resolve()
    if top != workspace:
        raise ValueError("--workspace must be the exact Git checkout root")
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    return {"captured_at_utc": utc_now(), "root": str(top), "head": git("rev-parse", "HEAD"),
            "branch": git("branch", "--show-current"), "status_porcelain": status,
            "clean": not bool(status)}


def freeze_and_kill(tree, timeout=5.0, process=None):
    """Stop/KILL only owned PID identities. No post-deadline TERM write grace.

    This is a sequence of /proc observations and pidfd signals, not an atomic
    system-wide freeze. Record actual observation times and any survivors.
    """
    started = time.monotonic()
    result = {"requested_at_utc": utc_now(), "started_monotonic": started,
              "frozen_observed_at_utc": None,
              "signals": [], "errors": [], "reaped": []}
    sent = set()

    def send(item, sig):
        key = (item["pid"], item["starttime"], sig)
        if key in sent:
            return
        try:
            if tree.send(item, sig):
                sent.add(key)
                result["signals"].append({"pid": item["pid"], "starttime": item["starttime"],
                                          "signal": sig.name, "at_utc": utc_now(),
                                          "seconds_after_request": time.monotonic() - started})
        except OSError as error:
            message = "{} PID {}: {}".format(sig.name, item["pid"], error)
            if message not in result["errors"]:
                result["errors"].append(message)

    def reap(items):
        for item in items:
            try:
                if process is not None and item["pid"] == process.pid:
                    # Let Popen retain the real exit status of its own child.
                    process.poll()
                else:
                    pid, status = os.waitpid(item["pid"], os.WNOHANG)
                    if pid:
                        result["reaped"].append({"pid": pid, "starttime": item["starttime"],
                                                 "wait_status": status})
            except (ChildProcessError, ProcessLookupError):
                pass

    # Stop parents first, then rescan for children created during observation.
    # A very short bounded observation phase can establish stopped states; it
    # is not a grace period permitting normal work after the deadline.
    freeze_limit = started + min(0.25, max(0.0, timeout))
    while True:
        items = tree.descendants()
        reap(items)
        items = tree.descendants()
        for item in sorted(items, key=lambda item: (item["ppid"] != tree.root, item["pid"])):
            if item["state"] not in ("T", "t", "Z", "X"):
                send(item, signal.SIGSTOP)
        observed = tree.descendants()
        if all(item["state"] in ("T", "t", "Z", "X") for item in observed):
            result["frozen_observed_at_utc"] = utc_now()
            result["frozen_observed_monotonic"] = time.monotonic()
            result["freeze_observed_seconds_after_request"] = result["frozen_observed_monotonic"] - started
            break
        if time.monotonic() >= freeze_limit:
            break
        time.sleep(0.005)

    while True:
        remaining = tree.descendants()
        reap(remaining)
        remaining = tree.descendants()
        if not remaining:
            break
        for item in remaining:
            if item["state"] not in ("Z", "X"):
                send(item, signal.SIGSTOP)
                send(item, signal.SIGKILL)
        if time.monotonic() - started >= timeout:
            break
        time.sleep(0.01)
    # Refresh after the last signal. Survivors, including zombies not reaped,
    # are evidence of incomplete cleanup rather than an assumed success.
    reap(tree.descendants())
    remaining = tree.descendants()
    result.update({"complete": not remaining and not result["errors"],
                   "remaining": remaining, "observed": list(tree.seen.values()),
                   "finished_at_utc": utc_now(), "elapsed_seconds": time.monotonic() - started})
    return result


class SessionInterrupted(Exception):
    def __init__(self, signum):
        self.signum = signum


def run(args):
    if not sys.platform.startswith("linux"):
        raise ValueError("Execution requires Linux /proc, subreaper and pidfd support")
    workspace = args.workspace.expanduser().resolve(strict=True)
    before = git_snapshot(workspace)
    prompt = args.prompt.expanduser().resolve(strict=True).read_bytes()
    if not prompt.strip():
        raise ValueError("The complete prompt must not be empty")
    requested_output = args.output.expanduser()
    if requested_output.exists() or requested_output.is_symlink():
        raise ValueError("--output must be a new directory; refusing overwrite")
    output = requested_output.resolve()
    if output == workspace or workspace in output.parents:
        raise ValueError("--output must be outside the candidate checkout")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise ValueError("Pass the organiser's explicit command after --")
    output.mkdir(parents=True, exist_ok=False)
    (output / "prompt.txt").write_bytes(prompt)
    record = {
        "schema_version": 1, "status": "not_started", "workspace": str(workspace),
        "command": command, "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "prompt_bytes": len(prompt), "uid": os.getuid(), "euid": os.geteuid(),
        "supervisor_pid": os.getpid(), "git_before": before,
        "started_at_utc": None, "deadline_at_utc": None, "stop_requested_at_utc": None,
        "stopped_at_utc": None, "command_exit_code": None,
        "timing": {"budget_seconds": args.seconds},
        "source_write_protected": False, "model_duration_verified": False,
        "boundary": (
            "Budget begins immediately before the CLI launch attempt; it includes launch/CLI overhead, "
            "not a measured duration of model inference. Only this supervisor's descendants are owned. "
            "Signals are not an atomic filesystem freeze. stopped_at_utc is the observation of an empty "
            "owned process tree, not a filesystem last-write timestamp. External services, other users, "
            "malicious modification, supervisor SIGKILL and container termination are outside this guarantee. "
            "No suite start, commit, push, scoring, or platform snapshot is performed or inferred."
        ),
    }
    save(output / "run.json", record)
    tree = None
    process = None
    started_clock = None
    handled_signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous_signals = {sig: signal.getsignal(sig) for sig in handled_signals}

    def interrupt(signum, _frame):
        raise SessionInterrupted(signum)

    try:
        tree = BuildProcessTree()
        for sig in handled_signals:
            signal.signal(sig, interrupt)
        with (output / "prompt.txt").open("rb") as stdin, \
                (output / "stdout.log").open("xb") as stdout, \
                (output / "stderr.log").open("xb") as stderr:
            started_wall = datetime.now(timezone.utc)
            started_clock = time.monotonic()
            deadline = started_clock + args.seconds
            record["status"] = "running"
            record["started_at_utc"] = started_wall.isoformat(timespec="microseconds")
            record["deadline_at_utc"] = (started_wall + timedelta(seconds=args.seconds)).isoformat(timespec="microseconds")
            process = subprocess.Popen(command, cwd=workspace, stdin=stdin, stdout=stdout, stderr=stderr,
                                       start_new_session=True)
            record["command_pid"] = process.pid
            record["spawn_returned_at_utc"] = utc_now()
            record["timing"]["spawn_overhead_seconds"] = time.monotonic() - started_clock
            save(output / "run.json", record)
            next_observation = started_clock
            while True:
                now = time.monotonic()
                if now >= deadline:
                    record.update(status="deadline", stop_reason="deadline")
                    break
                if process.poll() is not None:
                    record.update(status="completed" if process.returncode == 0 else "failed",
                                  stop_reason="command_exit")
                    break
                if now >= next_observation:
                    tree.descendants()
                    next_observation = now + 0.5
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
    except SessionInterrupted as error:
        record.update(status="interrupted", stop_reason="signal", signal=error.signum)
    except Exception as error:
        record.update(status="failed", stop_reason="error", error="{}: {}".format(type(error).__name__, error))
    finally:
        # Once stopping starts, repeated user signals must not bypass cleanup.
        for sig in handled_signals:
            signal.signal(sig, signal.SIG_IGN)
        stop_clock = time.monotonic()
        record["stop_requested_at_utc"] = utc_now()
        if started_clock is not None:
            record["timing"].update({
                "elapsed_to_stop_request_seconds": stop_clock - started_clock,
                "stop_request_overshoot_seconds": max(0.0, stop_clock - started_clock - args.seconds)})
        try:
            if tree is not None:
                record["cleanup"] = freeze_and_kill(tree, process=process)
            else:
                record["cleanup"] = {"complete": False, "remaining": [],
                                     "errors": ["Process ownership was not established"]}
        except Exception as error:
            record["cleanup"] = {"complete": False, "remaining": None,
                                 "errors": ["{}: {}".format(type(error).__name__, error)]}
        finally:
            if tree is not None:
                tree.libc.prctl(36, tree.previous_subreaper, 0, 0, 0)
        end_clock = time.monotonic()
        if started_clock is not None:
            record["timing"].update({
                "elapsed_to_cleanup_seconds": end_clock - started_clock,
                "cleanup_end_overshoot_seconds": max(0.0, end_clock - started_clock - args.seconds)})
        if record["cleanup"]["complete"]:
            record["stopped_at_utc"] = record["cleanup"]["finished_at_utc"]
        else:
            record["status_before_cleanup_failure"] = record["status"]
            record["status"] = "cleanup_incomplete"
        if process is not None:
            record["command_exit_code"] = process.poll()
        if started_clock is not None and record["cleanup"].get("frozen_observed_at_utc"):
            record["timing"]["freeze_observation_overshoot_seconds"] = max(
                0.0, record["cleanup"]["frozen_observed_monotonic"] - started_clock - args.seconds)
        try:
            record["git_after"] = git_snapshot(workspace)
        except Exception as error:
            record["git_after"] = {"error": "{}: {}".format(type(error).__name__, error)}
            if record["status"] == "completed":
                record["status"] = "failed"
        record["recorded_at_utc"] = utc_now()
        try:
            save(output / "run.json", record)
        finally:
            for sig, previous in previous_signals.items():
                signal.signal(sig, previous)
    print(json.dumps({"status": record["status"], "record": str(output / "run.json"),
                      "cleanup_complete": record["cleanup"]["complete"]}))
    return {"completed": 0, "deadline": 124, "cleanup_incomplete": 125,
            "interrupted": 128 + record.get("signal", 0)}.get(record["status"], 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True, help="exact candidate Git checkout root")
    parser.add_argument("--prompt", type=Path, required=True, help="complete prompt, copied byte-for-byte to CLI stdin")
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory outside the checkout")
    parser.add_argument("--seconds", type=positive_int, default=2700, help="CLI wall budget, default 2700; shorter values are not a 45-minute run")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- followed by the explicit CLI and its arguments; no shell")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
