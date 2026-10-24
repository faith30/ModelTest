"""Boundary checks for review aggregation, not tests of candidate animation behavior."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "score_review", Path(__file__).resolve().parents[1] / "tools" / "score_review.py")
score = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(score)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.candidate = self.root / "candidate"
        self.candidate.mkdir()
        (self.candidate / "controller.py").write_text(
            "# source reviewed as text only\ntransition = 'start_to_cycle'\nphase = 0.5\n", encoding="utf-8")
        (self.candidate / "assets.json").write_text('{"curve": "Distance"}\n', encoding="utf-8")
        self.rubric = {
            "items": [{"id": "I1", "category": "graph", "weight": 60},
                      {"id": "I2", "category": "resources", "weight": 40}],
            "gates": [{"id": "G1", "cap": 50}, {"id": "G2", "cap": 30}],
        }

    def evidence(self):
        return [{"path": "controller.py", "line_start": 2, "line_end": 2,
                 "quote": "transition = 'start_to_cycle'"}]

    def reviewed(self):
        review = score.init_review(self.rubric, self.candidate)
        review["items"] = {name: {"status": "pass", "evidence": self.evidence()} for name in ("I1", "I2")}
        review["gates"] = {name: {"status": "pass", "confirmed": True,
                                  "reason": "Reviewer inspected the relevant candidate scope.",
                                  "reviewed_paths": ["controller.py", "assets.json"]} for name in ("G1", "G2")}
        return review

    def test_init_and_omitted_entries_remain_unreviewed(self):
        review = score.init_review(self.rubric, self.candidate)
        result = score.score_review(self.rubric, review, self.candidate)
        self.assertIsNone(result["final_score"])
        self.assertEqual(result["reviewed_subscore"], 0)
        self.assertEqual(result["coverage"]["weight_fraction"], 0)
        review = self.reviewed()
        del review["items"]["I2"]
        del review["gates"]["G2"]
        result = score.score_review(self.rubric, review, self.candidate)
        self.assertIsNone(result["final_score"])
        self.assertEqual(result["reviewed_subscore"], 60)
        self.assertEqual(result["unreviewed_items"], ["I2"])
        self.assertEqual(result["unreviewed_gates"], ["G2"])

    def test_pass_partial_and_item_deductions(self):
        review = self.reviewed()
        review["items"]["I2"].update(status="partial", awarded=15.5, reason="Resource behavior is partly specified.")
        result = score.score_review(self.rubric, review, self.candidate)
        self.assertEqual(result["final_score"], 75.5)
        self.assertEqual(result["items"][1]["deduction"], 24.5)
        self.assertEqual(result["categories"]["resources"]["reviewed_subscore"], 15.5)

    def test_missing_and_incorrect_need_audited_scope(self):
        review = self.reviewed()
        review["items"]["I1"] = {"status": "missing", "reason": "No implementation in inspected files.",
                                   "reviewed_paths": ["controller.py"]}
        review["items"]["I2"] = {"status": "incorrect", "reason": "The cited behavior contradicts the contract.",
                                   "evidence": self.evidence()}
        result = score.score_review(self.rubric, review, self.candidate)
        self.assertEqual(result["final_score"], 0)
        self.assertEqual(result["reviewed_deductions"], 100)
        for changed in ({"reviewed_paths": []}, {"reason": ""}):
            with self.subTest(changed=changed):
                invalid = copy.deepcopy(review)
                invalid["items"]["I1"].update(changed)
                with self.assertRaises(score.ReviewError):
                    score.score_review(self.rubric, invalid, self.candidate)

    def test_gates_take_minimum_cap_without_double_deduction(self):
        review = self.reviewed()
        for gate in review["gates"].values():
            gate["status"] = "fail"
        result = score.score_review(self.rubric, review, self.candidate)
        self.assertEqual(result["raw_score"], 100)
        self.assertEqual(result["effective_cap"], 30)
        self.assertEqual(result["final_score"], 30)
        self.assertEqual(result["cap_deduction"], 70)
        self.assertTrue(all(item["deduction"] == 0 for item in result["items"]))
        for status in ("pass", "fail"):
            with self.subTest(unsubstantiated_status=status):
                invalid = copy.deepcopy(review)
                invalid["gates"]["G1"].update(status=status, reviewed_paths=[], evidence=[])
                with self.assertRaisesRegex(score.ReviewError, "confirmed gate finding"):
                    score.score_review(self.rubric, invalid, self.candidate)
                invalid["gates"]["G1"]["reviewed_paths"] = ["missing.py"]
                with self.assertRaises(score.ReviewError):
                    score.score_review(self.rubric, invalid, self.candidate)
                invalid["gates"]["G1"].update(reviewed_paths=[], evidence=self.evidence())
                score.score_review(self.rubric, invalid, self.candidate)

    def test_unconfirmed_gate_prevents_final_score(self):
        review = self.reviewed()
        review["gates"]["G1"].update(status="fail", confirmed=False)
        result = score.score_review(self.rubric, review, self.candidate)
        self.assertIsNone(result["final_score"])
        self.assertEqual(result["raw_score"], 100)
        self.assertEqual(result["effective_cap"], 100)
        self.assertEqual(result["unreviewed_gates"], ["G1"])
        review["gates"]["G1"].update(status="unreviewed", confirmed=True)
        with self.assertRaises(score.ReviewError):
            score.score_review(self.rubric, review, self.candidate)

    def test_digest_detects_changed_bytes_renames_and_new_files(self):
        for change in ("content", "rename", "addition"):
            with self.subTest(change=change):
                review = self.reviewed()
                asset = self.candidate / "assets.json"
                original = asset.read_bytes()
                if change == "content":
                    asset.write_bytes(original + b" ")
                elif change == "rename":
                    asset.rename(self.candidate / "renamed.json")
                else:
                    (self.candidate / "extra.txt").write_text("added", encoding="utf-8")
                with self.assertRaisesRegex(score.ReviewError, "hash mismatch"):
                    score.score_review(self.rubric, review, self.candidate)
                if change == "rename":
                    (self.candidate / "renamed.json").rename(asset)
                elif change == "addition":
                    (self.candidate / "extra.txt").unlink()
                else:
                    asset.write_bytes(original)

    def test_evidence_checks_exact_line_interval_and_containment(self):
        (self.root / "outside.txt").write_text("transition = 'start_to_cycle'", encoding="utf-8")
        bad = [{"quote": "not in this file"}, {"line_start": 1, "line_end": 1},
               {"line_end": 99}, {"line_start": True}, {"line_start": 0},
               {"path": "../outside.txt"}, {"path": str(self.root / "outside.txt")},
               {"path": "C:/outside.txt"}, {"path": "nested\\file.txt"}, {"path": "."}]
        for replacement in bad:
            with self.subTest(replacement=replacement):
                review = self.reviewed()
                review["items"]["I1"]["evidence"][0].update(replacement)
                with self.assertRaises(score.ReviewError):
                    score.score_review(self.rubric, review, self.candidate)
        review = self.reviewed()
        review["items"]["I1"]["evidence"] = []
        with self.assertRaises(score.ReviewError):
            score.score_review(self.rubric, review, self.candidate)
        link = self.candidate / "escape.txt"
        try:
            os.symlink(self.root / "outside.txt", link)
        except (OSError, NotImplementedError):
            # Windows may not grant symlink creation. Other containment checks still run.
            return
        with self.assertRaisesRegex(score.ReviewError, "symlink/reparse"):
            score.candidate_tree(self.candidate)

    def test_invalid_status_unknown_ids_and_numeric_awards(self):
        for award in (-1, 0, 40, 41, float("nan"), float("inf"), True, "10"):
            with self.subTest(award=award):
                review = self.reviewed()
                review["items"]["I2"].update(status="partial", awarded=award, reason="Partial.")
                with self.assertRaises(score.ReviewError):
                    score.score_review(self.rubric, review, self.candidate)
        for mapping in ("items", "gates"):
            review = self.reviewed()
            review[mapping]["UNKNOWN"] = {"status": "pass"}
            with self.assertRaisesRegex(score.ReviewError, "Unknown"):
                score.score_review(self.rubric, review, self.candidate)
        review = self.reviewed()
        review["items"]["I1"]["status"] = "looks_good"
        with self.assertRaises(score.ReviewError):
            score.score_review(self.rubric, review, self.candidate)
        for mutation in ("duplicate", "negative_weight", "cap_too_high"):
            rubric = copy.deepcopy(self.rubric)
            if mutation == "duplicate":
                rubric["items"].append(copy.deepcopy(rubric["items"][0]))
            elif mutation == "negative_weight":
                rubric["items"][0]["weight"] = -1
            else:
                rubric["gates"][0]["cap"] = 101
            with self.assertRaises(score.ReviewError):
                score.validate_rubric(rubric)

    def test_json_rejects_duplicate_ids_nan_and_infinite_exponents(self):
        path = self.root / "bad-review.json"
        for payload in ('{"items":{"I1":{},"I1":{}}}', '{"value":NaN}',
                        '{"value":Infinity}', '{"value":1e309}'):
            with self.subTest(payload=payload):
                path.write_text(payload, encoding="utf-8")
                with self.assertRaises(score.ReviewError):
                    score.read_json(path)

    def test_cli_template_score_roundtrip_and_protected_paths(self):
        rubric_path, review_path, output = (self.root / name for name in ("rubric.json", "review.json", "score.json"))
        rubric_path.write_text(json.dumps(self.rubric), encoding="utf-8")
        common = ["--rubric", str(rubric_path), "--candidate", str(self.candidate)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(score.main(common + ["--init-review", "--output", str(review_path)]), 0)
            self.assertEqual(score.main(common + ["--init-review", "--output", str(review_path)]), 2)
            template = score.read_json(review_path)
            reviewed = self.reviewed()
            reviewed["rubric_sha256"] = template["rubric_sha256"]
            review_path.write_text(json.dumps(reviewed), encoding="utf-8")
            self.assertEqual(score.main(common + ["--review", str(review_path), "--output", str(output)]), 0)
            self.assertEqual(score.read_json(output)["final_score"], 100)
            del reviewed["rubric_sha256"]
            review_path.write_text(json.dumps(reviewed), encoding="utf-8")
            self.assertEqual(score.main(common + ["--review", str(review_path), "--output", str(output)]), 2)
            reviewed["rubric_sha256"] = template["rubric_sha256"]
            review_path.write_text(json.dumps(reviewed), encoding="utf-8")
            self.assertEqual(score.main(common + ["--review", str(review_path), "--output", str(review_path)]), 2)
            inside = self.candidate / "score.json"
            self.assertEqual(score.main(common + ["--review", str(review_path), "--output", str(inside)]), 2)
            self.assertFalse(inside.exists())
            rubric_path.write_text(json.dumps(self.rubric) + "\n", encoding="utf-8")
            self.assertEqual(score.main(common + ["--review", str(review_path), "--output", str(output)]), 2)


if __name__ == "__main__":
    unittest.main()
