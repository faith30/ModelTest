"""Own and clean Linux build descendants, including children that call setsid()."""

import ctypes
import json
import os
from pathlib import Path
import signal
import sys
import time


def identity(pid):
    try:
        fields = Path("/proc/{}/stat".format(pid)).read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "ppid": int(fields[1]), "pgid": int(fields[2]),
                "sid": int(fields[3]), "starttime": int(fields[19]), "state": fields[0]}
    except (OSError, ValueError, IndexError):
        return None


class BuildProcessTree:
    def __init__(self):
        if not sys.platform.startswith("linux") or not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
            raise RuntimeError("Linux pidfd support is required for safe build descendant cleanup")
        self.root = os.getpid()
        self.libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        if self.libc.prctl(37, ctypes.byref(previous), 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "PR_GET_CHILD_SUBREAPER failed")
        self.previous_subreaper = previous.value
        fd = os.pidfd_open(self.root)
        os.close(fd)
        if self.libc.prctl(36, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "PR_SET_CHILD_SUBREAPER failed")
        self.previous_term = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, self.interrupt)
        self.seen = {}

    @staticmethod
    def interrupt(signum, frame):
        raise KeyboardInterrupt("Build wrapper received SIGTERM")

    def descendants(self):
        processes = {}
        for entry in Path("/proc").iterdir():
            if entry.name.isdigit():
                item = identity(int(entry.name))
                if item is not None:
                    processes[item["pid"]] = item
        selected = {self.root}
        while True:
            added = {pid for pid, item in processes.items() if item["ppid"] in selected} - selected
            if not added:
                break
            selected.update(added)
        result = [processes[pid] for pid in selected - {self.root}]
        for item in result:
            self.seen[(item["pid"], item["starttime"])] = item
        return result

    def still_owned(self, item):
        current = identity(item["pid"])
        if current is None or current["starttime"] != item["starttime"]:
            return False
        visited = set()
        while current and current["pid"] not in visited:
            visited.add(current["pid"])
            if current["ppid"] == self.root:
                return True
            current = identity(current["ppid"])
        return False

    def send(self, item, sig):
        if not self.still_owned(item):
            return False
        try:
            fd = os.pidfd_open(item["pid"])
        except ProcessLookupError:
            return False
        try:
            # Recheck after opening: an fd can otherwise refer to a reused PID.
            if not self.still_owned(item):
                return False
            signal.pidfd_send_signal(fd, sig)
            return True
        except ProcessLookupError:
            return False
        finally:
            os.close(fd)

    def cleanup(self):
        previous_int = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        sent, reaped, errors = [], [], []
        signaled = set()
        remaining = []
        try:
            for sig, grace in ((signal.SIGTERM, 2), (signal.SIGKILL, 5)):
                deadline = time.monotonic() + grace
                while True:
                    remaining = self.descendants()
                    for item in remaining:
                        try:
                            pid, status = os.waitpid(item["pid"], os.WNOHANG)
                            if pid:
                                reaped.append({"pid": pid, "starttime": item["starttime"], "wait_status": status})
                        except ChildProcessError:
                            pass
                    remaining = self.descendants()
                    if not remaining:
                        break
                    for item in remaining:
                        key = (item["pid"], item["starttime"], sig)
                        if key in signaled:
                            continue
                        signaled.add(key)
                        try:
                            if self.send(item, sig):
                                sent.append({"pid": item["pid"], "starttime": item["starttime"], "signal": sig.name})
                        except OSError as error:
                            errors.append(str(error))
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.05)
                if not remaining:
                    break
            return {"complete": not remaining and not errors, "root_pid": self.root,
                    "subreaper_enabled": True, "observed": list(self.seen.values()),
                    "signals": sent, "reaped": reaped, "remaining": remaining, "errors": errors,
                    "boundary": "Tracks only this wrapper's descendants. SIGTERM/SIGINT, timeout and normal completion are handled; wrapper SIGKILL or container termination cannot run cleanup."}
        finally:
            signal.signal(signal.SIGTERM, self.previous_term)
            signal.signal(signal.SIGINT, previous_int)
            self.libc.prctl(36, self.previous_subreaper, 0, 0, 0)


def self_test():
    """Linux-only fake subprocess test; never invokes UE or awards a build pass."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory(prefix="lyra-process-cleanup-") as directory:
        results = []
        for mode in ("timeout", "orphan", "signal"):
            folder = Path(directory) / mode
            folder.mkdir()
            worker = subprocess.run([sys.executable, __file__, "--test-worker", mode, str(folder)],
                                    capture_output=True, text=True, timeout=30)
            if worker.returncode:
                raise RuntimeError("{} worker failed: {} {}".format(mode, worker.stdout, worker.stderr))
            record = json.loads((folder / "run.json").read_text())
            children = [json.loads((folder / (role + ".json")).read_text()) for role in ("parent", "child", "grandchild")]
            for item in children:
                current = identity(item["pid"])
                if current and current["starttime"] == item["starttime"]:
                    raise AssertionError("Fixture descendant remains: " + str(item))
            for item in children[1:]:
                assert item["sid"] == item["pid"] and item["pgid"] == item["pid"]
            assert record["process_cleanup"]["complete"]
            assert any(item["signal"] == "SIGKILL" for item in record["process_cleanup"]["signals"])
            assert record["timed_out"] is (mode == "timeout")
            assert record["interrupted"] is (mode == "signal")
            results.append({"mode": mode, "passed": True, "fixture_processes": children,
                            "cleanup": record["process_cleanup"]})
        print(json.dumps({"self_test": "cross_session_fake_descendants", "ue_executed": False,
                          "cases": results}, indent=2))


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
    elif len(sys.argv) == 4 and sys.argv[1] == "--test-worker":
        import run_lyra_build
        import headless_ue
        mode, folder = sys.argv[2], Path(sys.argv[3])
        os.environ["LYRA_CLEANUP_TEST_WRAPPER_PID"] = str(os.getpid())
        command = [sys.executable, str(Path(__file__).resolve()), "--fixture", "parent", mode, str(folder)]
        run_lyra_build.measured_execute(headless_ue.execute, command, folder, folder, 3 if mode == "timeout" else 15)
    elif len(sys.argv) == 5 and sys.argv[1] == "--fixture":
        import subprocess
        role, mode, folder = sys.argv[2], sys.argv[3], Path(sys.argv[4])
        signal.alarm(20)
        if role != "parent":
            os.setsid()
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        next_role = {"parent": "child", "child": "grandchild"}.get(role)
        if next_role:
            subprocess.Popen([sys.executable, __file__, "--fixture", next_role, mode, str(folder)])
        (folder / (role + ".json")).write_text(json.dumps(identity(os.getpid())))
        if role == "parent":
            while not (folder / "grandchild.json").is_file():
                time.sleep(0.01)
            if mode == "orphan":
                os._exit(0)
            if mode == "signal":
                os.kill(int(os.environ["LYRA_CLEANUP_TEST_WRAPPER_PID"]), signal.SIGTERM)
        while True:
            time.sleep(1)
    else:
        raise SystemExit("Use --self-test")
