"""Local integration tests using a disposable Git repository and a real LFS object."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().with_name("suite.py")


def run(*args, cwd=None, ok=True):
    result = subprocess.run(list(map(str, args)), cwd=cwd, capture_output=True,
                            encoding="utf-8", errors="replace")
    if ok and result.returncode:
        raise AssertionError("{}\n{}\n{}".format(args, result.stdout, result.stderr))
    return result


def git(*args, cwd=None):
    return run("git", *args, cwd=cwd).stdout.strip()


class SuiteIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        git("lfs", "version")
        cls.temporary = tempfile.TemporaryDirectory(prefix="lyra-suite-test-")
        cls.root = Path(cls.temporary.name)
        cls.remote = cls.root / "remote.git"
        cls.source = cls.root / "fixture"
        cls.kit = cls.root / "kit"
        cls.kit.mkdir()
        git("init", "--bare", cls.remote)
        git("init", "-b", "codex/test-interaction", cls.source)
        git("config", "user.name", "Suite Fixture", cwd=cls.source)
        git("config", "user.email", "fixture@example.invalid", cwd=cls.source)
        git("lfs", "install", "--local", cwd=cls.source)
        git("lfs", "track", "*.dat", cwd=cls.source)
        cls.payload = b"Small plain-text fixture tracked through Git LFS.\n" * 10
        (cls.source / "asset.dat").write_bytes(cls.payload)
        task_dir = cls.source / "Benchmarks" / "interaction"
        task_dir.mkdir(parents=True)
        protected = []
        for name in ["TASK.md", "scope.json", "baseline-validation.json"]:
            (task_dir / name).write_text("Original fixture specification.\n", encoding="utf-8")
            protected.append("Benchmarks/interaction/" + name)
        git("add", ".gitattributes", "asset.dat", "Benchmarks", cwd=cls.source)
        git("commit", "-m", "Single root task fixture", cwd=cls.source)
        cls.baseline = git("rev-parse", "HEAD", cwd=cls.source)
        git("remote", "add", "origin", cls.remote, cwd=cls.source)
        git("push", "origin", "HEAD", cwd=cls.source)
        (cls.kit / "prompt.txt").write_text("Implement this fixture task.\n", encoding="utf-8")
        cls.metadata = cls.kit / "suite.json"
        cls.metadata.write_text(json.dumps({
            "repository": str(cls.remote), "model": "deepseek-v4-pro", "wall_time_seconds": 2700,
            "features": {"interaction": {
                "branch": "codex/test-interaction", "starting_commit": cls.baseline,
                "prompt_file": "prompt.txt", "task_file": protected[0],
                "protected_files": protected,
            }},
        }), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        # Git objects can be read-only on Windows; TemporaryDirectory handles this.
        cls.temporary.cleanup()

    def setUp(self):
        self.name = self._testMethodName.replace("_", "-")
        self.workspace = self.root / "runs" / ("interaction-" + self.name)
        self.cli("prepare", "interaction", "--root", self.workspace.parent,
                 "--name", self.name, "--metadata", self.metadata)
        # Identities belong only to the disposable test clone, never the tool itself.
        git("config", "user.name", "Suite Fixture", cwd=self.workspace)
        git("config", "user.email", "fixture@example.invalid", cwd=self.workspace)

    def cli(self, *args, ok=True):
        return run(sys.executable, SCRIPT, *args, ok=ok)

    def session(self):
        return json.loads(self.workspace.with_name(self.workspace.name + ".session.json").read_text(encoding="utf-8"))

    def commit(self, path, text):
        (self.workspace / path).write_text(text, encoding="utf-8")
        git("add", path, cwd=self.workspace)
        git("commit", "-m", "Fixture result", cwd=self.workspace)

    def test_prepare_snapshot_and_lfs(self):
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.workspace), self.baseline)
        self.assertEqual(git("rev-list", "--count", "HEAD", cwd=self.workspace), "1")
        self.assertEqual(git("remote", cwd=self.workspace), "")
        self.assertEqual((self.workspace / "asset.dat").read_bytes(), self.payload)
        self.assertEqual(self.session()["lfs_files_checked"], 1)
        duplicate = self.cli("prepare", "interaction", "--root", self.workspace.parent,
                             "--name", self.name, "--metadata", self.metadata, ok=False)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("overwrite", duplicate.stderr)

    def test_repeated_start_is_rejected(self):
        self.cli("start", self.workspace)
        first = self.session()["started_at_utc"]
        repeated = self.cli("start", self.workspace, ok=False)
        self.assertNotEqual(repeated.returncode, 0)
        self.assertIn("already started", repeated.stderr)
        self.assertEqual(self.session()["started_at_utc"], first)

    def test_modified_task_is_rejected(self):
        self.cli("start", self.workspace)
        self.commit("Benchmarks/interaction/TASK.md", "Altered requirements\n")
        result = self.cli("submit", self.workspace, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Protected task/baseline file was modified", result.stderr)
        self.assertEqual(git("ls-remote", "--heads", self.remote, self.session()["result_branch"]), "")

    def test_committed_result_is_published_without_score(self):
        self.cli("start", self.workspace)
        self.commit("SOLUTION.md", "Fixture solution notes\n")
        self.cli("submit", self.workspace)
        head = git("rev-parse", "HEAD", cwd=self.workspace)
        remote = git("ls-remote", "--heads", self.remote, self.session()["result_branch"])
        self.assertEqual(remote.split()[0], head)
        report = json.loads(self.workspace.with_name(self.workspace.name + ".result.json").read_text(encoding="utf-8"))
        self.assertEqual(report["result_commit"], head)
        self.assertIsNone(report["score"])
        self.assertEqual(report["ue_runtime"], "not_verified")
        self.assertEqual(report["evaluation_status"], "submitted_not_evaluated")
        self.assertEqual(git("remote", cwd=self.workspace), "")

    def test_dirty_submission_is_rejected(self):
        self.cli("start", self.workspace)
        self.commit("SOLUTION.md", "Fixture solution notes\n")
        (self.workspace / "forgotten.cpp").write_text("Uncommitted work\n", encoding="utf-8")
        result = self.cli("submit", self.workspace, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not clean", result.stderr)
        self.assertEqual(git("ls-remote", "--heads", self.remote, self.session()["result_branch"]), "")

    def test_non_fast_forward_submission_is_rejected(self):
        self.cli("start", self.workspace)
        self.commit("SOLUTION.md", "Local result\n")
        branch = self.session()["result_branch"]
        git("switch", "-c", branch, self.baseline, cwd=self.source)
        (self.source / "REMOTE.md").write_text("Competing remote result\n", encoding="utf-8")
        git("add", "REMOTE.md", cwd=self.source)
        git("commit", "-m", "Independent result", cwd=self.source)
        git("push", "origin", "HEAD:refs/heads/" + branch, cwd=self.source)
        remote_head = git("rev-parse", "HEAD", cwd=self.source)
        result = self.cli("submit", self.workspace, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(git("ls-remote", "--heads", self.remote, branch).split()[0], remote_head)
        self.assertFalse(self.workspace.with_name(self.workspace.name + ".result.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
