"""Disposable process tests for run_model_session; never starts UE or a model.

Run with: python -B -m unittest -v test_run_model_session
Linux integration cases use only a temporary Git repository and Python fixtures.
"""

import hashlib
import importlib
import json
import os
from datetime import datetime, timedelta
from enum import IntEnum
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


sys.dont_write_bytecode = True
SCRIPT = Path(__file__).resolve().with_name("run_model_session.py")
LINUX_PROCESS_SUPPORT = (
    sys.platform.startswith("linux")
    and hasattr(os, "pidfd_open")
    and hasattr(signal, "pidfd_send_signal")
)


FIXTURE = r'''
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

mode, role, folder, heartbeat = sys.argv[1:]
folder, heartbeat = Path(folder), Path(heartbeat)
signal.alarm(30)

def save(name, value):
    target = folder / name
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    os.replace(temporary, target)

fields = Path("/proc/{}/stat".format(os.getpid())).read_bytes().rsplit(b")", 1)[1].split()
save(role + ".json", {
    "pid": os.getpid(), "ppid": os.getppid(),
    "pgid": os.getpgrp(), "sid": os.getsid(0),
    "starttime": int(fields[19]),
})

if role == "parent":
    prompt = sys.stdin.buffer.read()
    (folder / "received-prompt.bin").write_bytes(prompt)
    sys.stdout.buffer.write(b"PROMPT-BEGIN\n" + prompt + b"\nPROMPT-END\n")
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(b"FIXTURE-STDERR\n")
    sys.stderr.buffer.flush()
    if mode in ("completed", "failed"):
        raise SystemExit(0 if mode == "completed" else 7)
else:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

next_role = {"parent": "child", "child": "grandchild"}.get(role)
if next_role:
    subprocess.Popen(
        [sys.executable, __file__, mode, next_role, str(folder), str(heartbeat)],
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

if role == "parent":
    while (not (folder / "grandchild.json").exists()
           or not heartbeat.exists() or heartbeat.stat().st_size == 0):
        time.sleep(0.01)
    save("ready.json", {"ready": True})
    if mode == "orphan":
        os._exit(0)

with heartbeat.open("ab", buffering=0) as stream:
    while True:
        stream.write((role + "\n").encode("ascii"))
        time.sleep(0.02)
'''


def process_identity(pid):
    """Independent /proc readback; do not trust the launcher's cleanup report."""
    try:
        fields = Path("/proc/{}/stat".format(pid)).read_bytes().rsplit(b")", 1)[1].split()
        return {"pid": pid, "starttime": int(fields[19]), "state": fields[0]}
    except (OSError, ValueError, IndexError):
        return None


class FixtureSignal(IntEnum):
    SIGKILL = 9
    SIGSTOP = 19


class FakeTree:
    """A process-tree protocol fake; no operating-system signal is sent."""
    def __init__(self, items=(), accept_signals=True):
        self.root = 4000000
        self.items = [dict(item) for item in items]
        self.accept_signals = accept_signals
        self.seen = {}
        self.sent = []

    def descendants(self):
        for item in self.items:
            self.seen[(item["pid"], item["starttime"])] = dict(item)
        return [dict(item) for item in self.items]

    def send(self, item, signum):
        self.sent.append((item["pid"], signum))
        if not self.accept_signals:
            return False
        if signum == FixtureSignal.SIGSTOP:
            for current in self.items:
                if current["pid"] == item["pid"]:
                    current["state"] = "T"
        elif signum == FixtureSignal.SIGKILL:
            self.items = [current for current in self.items if current["pid"] != item["pid"]]
        return True


class ModelSessionCleanupLogicTests(unittest.TestCase):
    """Run on Windows as well as Linux; fake /proc ownership and waitpid."""
    @classmethod
    def setUpClass(cls):
        cls.runner = importlib.import_module("run_model_session")

    def setUp(self):
        self.waitpid = mock.patch.object(self.runner.os, "waitpid", return_value=(0, 0), create=True)
        self.waitpid_mock = self.waitpid.start()
        self.addCleanup(self.waitpid.stop)
        self.wait_options = mock.patch.object(self.runner.os, "WNOHANG", 1, create=True)
        self.wait_options.start()
        self.addCleanup(self.wait_options.stop)
        self.signals = mock.patch.multiple(
            self.runner.signal, SIGSTOP=FixtureSignal.SIGSTOP,
            SIGKILL=FixtureSignal.SIGKILL, create=True,
        )
        self.signals.start()
        self.addCleanup(self.signals.stop)

    @staticmethod
    def item():
        return {"pid": 4000001, "ppid": 4000000, "starttime": 123, "state": "R"}

    def test_empty_tree_is_complete(self):
        result = self.runner.freeze_and_kill(FakeTree(), timeout=0)
        self.assertIs(result["complete"], True)
        self.assertEqual(result["remaining"], [])

    def test_residual_running_process_cannot_report_complete(self):
        tree = FakeTree([self.item()], accept_signals=False)
        result = self.runner.freeze_and_kill(tree, timeout=0)
        self.assertIs(result["complete"], False)
        self.assertEqual([item["pid"] for item in result["remaining"]], [4000001])

    def test_successful_freeze_precedes_kill(self):
        tree = FakeTree([self.item()])
        result = self.runner.freeze_and_kill(tree, timeout=0.1)
        self.assertIs(result["complete"], True, result)
        self.assertEqual(result["remaining"], [])
        signals = [signum for _, signum in tree.sent]
        self.assertIn(FixtureSignal.SIGSTOP, signals)
        self.assertIn(FixtureSignal.SIGKILL, signals)
        self.assertLess(signals.index(FixtureSignal.SIGSTOP), signals.index(FixtureSignal.SIGKILL))

    def test_popen_child_is_reaped_by_poll_without_losing_exit_status(self):
        item = self.item()
        item["state"] = "Z"
        tree = FakeTree([item])
        process = mock.Mock(pid=item["pid"], returncode=None)

        def poll():
            tree.items = []
            process.returncode = 7
            return process.returncode

        process.poll.side_effect = poll
        result = self.runner.freeze_and_kill(tree, timeout=0, process=process)
        self.assertIs(result["complete"], True, result)
        self.assertEqual(process.returncode, 7)
        process.poll.assert_called()
        self.waitpid_mock.assert_not_called()


@unittest.skipUnless(LINUX_PROCESS_SUPPORT, "requires Linux process identities and pidfds")
class ModelSessionProcessTests(unittest.TestCase):
    def setUp(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for the disposable fixture workspace")
        self.temporary = tempfile.TemporaryDirectory(prefix="model-session-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.state = self.root / "fixture-state"
        self.state.mkdir()
        self.output = self.root / "evidence"
        self.prompt = self.root / "prompt.txt"
        self.payload = b"\xef\xbb\xbf" + "Prompt: 保留原始字节\r\nsecond line\nlast line".encode("utf-8")
        self.prompt.write_bytes(self.payload)
        self.fixture = self.root / "fixture.py"
        self.fixture.write_text(FIXTURE, encoding="utf-8")
        self.heartbeat = self.workspace / "fixture-heartbeat.txt"
        self.processes = []
        self.addCleanup(self.emergency_cleanup)
        self.git("init", "--quiet")
        (self.workspace / "README.txt").write_text("Temporary model-session test repository.\n", encoding="utf-8")
        self.git("add", "README.txt")
        self.git("-c", "user.name=Model Session Test", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Fixture baseline")

    def git(self, *args):
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=" + str(self.root / "disabled-hooks"), *args],
            cwd=self.workspace, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def command(self, mode, seconds):
        command = [
            sys.executable, "-B", str(SCRIPT),
            "--workspace", str(self.workspace), "--prompt", str(self.prompt),
            "--output", str(self.output),
        ]
        if seconds is not None:
            command.extend(["--seconds", str(seconds)])
        return command + [
            "--",
            sys.executable, "-B", str(self.fixture), mode, "parent",
            str(self.state), str(self.heartbeat),
        ]

    def fixture_processes(self):
        return [json.loads(path.read_text(encoding="utf-8"))
                for path in sorted(self.state.glob("*.json")) if path.name != "ready.json"]

    def emergency_cleanup(self):
        """Failure-only safety net: signal only recorded, matching fixture identities."""
        if not self.state.exists():
            return
        for item in self.fixture_processes():
            current = process_identity(item["pid"])
            if current is None or current["starttime"] != item["starttime"]:
                continue
            try:
                fd = os.pidfd_open(item["pid"])
                try:
                    current = process_identity(item["pid"])
                    if current and current["starttime"] == item["starttime"]:
                        signal.pidfd_send_signal(fd, signal.SIGKILL)
                finally:
                    os.close(fd)
            except ProcessLookupError:
                pass
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                pass

    def run_cli(self, mode, seconds=10, wrapper_signal=None):
        self.expected_budget = 2700 if seconds is None else seconds
        process = subprocess.Popen(
            self.command(mode, seconds), cwd=self.root,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.processes.append(process)
        if wrapper_signal is not None:
            ready_deadline = time.monotonic() + 5
            while not (self.state / "ready.json").exists():
                if process.poll() is not None:
                    stdout, stderr = process.communicate(timeout=3)
                    self.fail("Wrapper exited before fixture readiness: {!r} {!r}".format(stdout, stderr))
                if time.monotonic() >= ready_deadline:
                    self.fail("Fixture did not become ready before the signal test deadline")
                time.sleep(0.01)
            process.send_signal(wrapper_signal)
        try:
            stdout, stderr = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            self.emergency_cleanup()
            self.fail("Wrapper exceeded the test deadline; fake processes were cleaned up")
        return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)

    def assert_record(self, expected_status):
        record = json.loads((self.output / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], expected_status, record)
        self.assertEqual(record["prompt_sha256"], hashlib.sha256(self.payload).hexdigest())
        self.assertIs(record["cleanup"]["complete"], True, record["cleanup"])
        self.assertEqual(record["cleanup"]["remaining"], [], record["cleanup"])
        self.assertIsInstance(record["timing"], dict)
        self.assertEqual(record["timing"]["budget_seconds"], self.expected_budget)
        for name in ("elapsed_to_stop_request_seconds", "stop_request_overshoot_seconds",
                     "elapsed_to_cleanup_seconds", "cleanup_end_overshoot_seconds"):
            self.assertIsInstance(record["timing"][name], (int, float), name)
            self.assertGreaterEqual(record["timing"][name], 0, name)
        self.assertLessEqual(record["timing"]["elapsed_to_stop_request_seconds"],
                             record["timing"]["elapsed_to_cleanup_seconds"])
        dates = {}
        for name in ("started_at_utc", "deadline_at_utc", "stop_requested_at_utc", "stopped_at_utc"):
            dates[name] = datetime.fromisoformat(record[name].replace("Z", "+00:00"))
            self.assertEqual(dates[name].utcoffset(), timedelta(0), name)
        self.assertLessEqual(dates["started_at_utc"], dates["stop_requested_at_utc"])
        self.assertLessEqual(dates["stop_requested_at_utc"], dates["stopped_at_utc"])
        self.assertAlmostEqual((dates["deadline_at_utc"] - dates["started_at_utc"]).total_seconds(),
                               self.expected_budget, delta=0.01)
        self.assertEqual((self.state / "received-prompt.bin").read_bytes(), self.payload)
        self.assertIn(b"PROMPT-BEGIN\n" + self.payload + b"\nPROMPT-END\n",
                      (self.output / "stdout.log").read_bytes())
        self.assertIn(b"FIXTURE-STDERR\n", (self.output / "stderr.log").read_bytes())
        self.assertNotIn(b"FIXTURE-STDERR\n", (self.output / "stdout.log").read_bytes())
        for item in self.fixture_processes():
            current = process_identity(item["pid"])
            self.assertFalse(current and current["starttime"] == item["starttime"],
                             "Fixture process remains (including zombies): {!r}".format(item))
        return record

    def assert_detached_fixture(self):
        for role in ("child", "grandchild"):
            item = json.loads((self.state / (role + ".json")).read_text(encoding="utf-8"))
            self.assertEqual(item["sid"], item["pid"])
            self.assertEqual(item["pgid"], item["pid"])

    def assert_writes_stopped(self):
        self.assertTrue(self.heartbeat.is_file(), "The writer fixture never ran")
        before = self.heartbeat.read_bytes()
        self.assertTrue(before)
        time.sleep(0.15)
        self.assertEqual(self.heartbeat.read_bytes(), before, "A fixture wrote after wrapper completion")

    def test_completed_preserves_entire_prompt_and_separate_logs(self):
        self.payload += b"\r\n" + b"Large prompt line.\r\n" * 8192 + b"last byte!"
        self.prompt.write_bytes(self.payload)
        result = self.run_cli("completed", seconds=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = self.assert_record("completed")
        self.assertEqual(record["command_exit_code"], 0)
        self.assertEqual(record["stop_reason"], "command_exit")

    def test_nonzero_command_is_failed(self):
        result = self.run_cli("failed")
        self.assertEqual(result.returncode, 1, result.stderr)
        record = self.assert_record("failed")
        self.assertEqual(record["command_exit_code"], 7)

    def test_normal_parent_exit_cleans_two_detached_generations(self):
        result = self.run_cli("orphan")
        self.assertEqual(result.returncode, 0, result.stderr)
        record = self.assert_record("completed")
        self.assertEqual(record["command_exit_code"], 0)
        self.assert_detached_fixture()
        self.assert_writes_stopped()

    def test_deadline_stops_continuous_writers(self):
        result = self.run_cli("writer", seconds=2)
        self.assertEqual(result.returncode, 124, result.stderr)
        record = self.assert_record("deadline")
        self.assertEqual(record["stop_reason"], "deadline")
        self.assertEqual(record["command_exit_code"], -signal.SIGKILL)
        self.assert_detached_fixture()
        self.assert_writes_stopped()

    def test_sigterm_stops_continuous_writers(self):
        result = self.run_cli("writer", wrapper_signal=signal.SIGTERM)
        self.assertEqual(result.returncode, 128 + signal.SIGTERM, result.stderr)
        record = self.assert_record("interrupted")
        self.assertEqual(record["stop_reason"], "signal")
        self.assertEqual(record["command_exit_code"], -signal.SIGKILL)
        self.assert_detached_fixture()
        self.assert_writes_stopped()

    def test_sigint_stops_continuous_writers(self):
        result = self.run_cli("writer", wrapper_signal=signal.SIGINT)
        self.assertEqual(result.returncode, 128 + signal.SIGINT, result.stderr)
        record = self.assert_record("interrupted")
        self.assertEqual(record["stop_reason"], "signal")
        self.assertEqual(record["command_exit_code"], -signal.SIGKILL)
        self.assert_detached_fixture()
        self.assert_writes_stopped()

    def test_existing_output_is_rejected_without_changes_or_launch(self):
        self.output.mkdir()
        sentinel = self.output / "do-not-overwrite.bin"
        sentinel.write_bytes(b"Existing evidence must remain intact.\x00\xff")
        original = sentinel.read_bytes()
        result = self.run_cli("completed")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_bytes(), original)
        self.assertEqual(list(self.output.iterdir()), [sentinel])
        self.assertEqual(list(self.state.iterdir()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
