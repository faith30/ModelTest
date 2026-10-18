import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import apply_candidate as application
from prepare import COMPONENT_CPP, SOURCE_PATHS, seed_component


def git(repo, *arguments):
    result = subprocess.run(["git", "-C", str(repo), "-c", "core.hooksPath=" + str(repo / ".disabled-hooks"),
                             *arguments], capture_output=True, check=True)
    return result.stdout.decode("utf-8").strip()


class ApplyCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lyra-apply-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "candidate"
        self.repo.mkdir()
        git(self.repo, "init", "--initial-branch=task")
        git(self.repo, "config", "user.name", "Evaluation Test")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "core.autocrlf", "false")
        git(self.repo, "config", "commit.gpgsign", "false")
        self.original = (TOOLS.parents[1] / COMPONENT_CPP).read_bytes().replace(b"\r\n", b"\n")
        seeded, _ = seed_component(self.original)
        for name in SOURCE_PATHS:
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(seeded if name == COMPONENT_CPP else b"// fixed reference source\n")
        (self.repo / "TASK.md").write_text("Fixed task requirements\n", encoding="utf-8")
        self.seed = self.commit("seed")
        (self.repo / COMPONENT_CPP).write_bytes(self.original)
        (self.repo / "SOLUTION.md").write_text("Restore the three death transitions.\n", encoding="utf-8")
        self.candidate = self.commit("candidate")
        self.project = self.root / "full-project"
        self.project.mkdir()
        (self.project / "Lyra.uproject").write_text(json.dumps({"Modules": [{"Name": "LyraGame"}]}), encoding="utf-8")
        for name in SOURCE_PATHS:
            target = self.project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.original.replace(b"\n", b"\r\n") if name == COMPONENT_CPP else b"// reference\n")
        (self.project / "Source/LyraGame/LyraGame.Build.cs").write_text("// existing build rules\n", encoding="utf-8")
        self.output = self.root / "application.json"

    def commit(self, message):
        git(self.repo, "add", "--all")
        git(self.repo, "commit", "-m", message)
        return git(self.repo, "rev-parse", "HEAD")

    def apply(self, candidate=None, seed=None):
        return application.apply_candidate(self.repo, seed or self.seed, candidate or self.candidate,
                                           self.project, self.output)

    def test_applies_exact_committed_bytes_and_ignores_dirty_candidate_worktree(self):
        (self.repo / COMPONENT_CPP).write_text("UNCOMMITTED INPUT MUST NOT BE USED", encoding="utf-8")
        record = self.apply()
        self.assertEqual((self.project / COMPONENT_CPP).read_bytes(), self.original)
        self.assertEqual(record["candidate_sha"], self.candidate)
        self.assertFalse(record["build_performed"])
        self.assertFalse(record["runtime_performed"])
        second = application.apply_candidate(self.repo, self.seed, self.candidate, self.project,
                                             self.root / "second.json")
        self.assertFalse(second["source_changed"])

    def test_rejects_other_tracked_file_changes(self):
        (self.repo / "TASK.md").write_text("changed", encoding="utf-8")
        invalid = self.commit("out of scope")
        with self.assertRaisesRegex(ValueError, "outside task scope"):
            self.apply(invalid)
        self.assertFalse(self.output.exists())

    def test_rejects_signature_and_outside_body_changes(self):
        changed = self.original.replace(b"void ULyraHealthComponent::StartDeath()",
                                        b"void ULyraHealthComponent::StartDeath(int Extra)", 1)
        (self.repo / COMPONENT_CPP).write_bytes(changed)
        invalid = self.commit("changed signature")
        with self.assertRaisesRegex(ValueError, "outside the three"):
            self.apply(invalid)
        (self.repo / COMPONENT_CPP).write_bytes(b"// additional production edit\n" + self.original)
        invalid = self.commit("outside function")
        with self.assertRaisesRegex(ValueError, "outside the three"):
            self.apply(invalid)

    def test_rejects_preexisting_project_edits_without_overwriting(self):
        local = self.original + b"\n// existing developer change\n"
        (self.project / COMPONENT_CPP).write_bytes(local)
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            self.apply()
        self.assertEqual((self.project / COMPONENT_CPP).read_bytes(), local)
        self.assertFalse(self.output.exists())

    def test_rejects_incomplete_ids_wrong_ancestry_and_existing_output(self):
        with self.assertRaisesRegex(ValueError, "40-character"):
            self.apply(candidate=self.candidate[:8])
        with self.assertRaisesRegex(ValueError, "not an ancestor"):
            self.apply(candidate=self.seed, seed=self.candidate)
        self.output.write_text("existing evidence", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.apply()
        self.assertEqual(self.output.read_text(encoding="utf-8"), "existing evidence")

    def test_rejects_new_executable_or_deleted_reference(self):
        (self.repo / "extra.py").write_text("print('not allowed')", encoding="utf-8")
        invalid = self.commit("extra file")
        with self.assertRaisesRegex(ValueError, "outside task scope"):
            self.apply(invalid)
        git(self.repo, "reset", "--hard", self.candidate)
        (self.repo / SOURCE_PATHS[1]).unlink()
        invalid = self.commit("deleted header")
        with self.assertRaisesRegex(ValueError, "outside task scope"):
            self.apply(invalid)


if __name__ == "__main__":
    unittest.main()
