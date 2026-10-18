import copy
import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "score_ue_report.py"
SPEC = importlib.util.spec_from_file_location("score_ue_report", MODULE_PATH)
scorer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scorer)
SHA = "a" * 40
DEVICE = "01234567-89ab-cdef-0123-456789abcdef"


def build(platform="Linux"):
    return {"target_platform": platform, "build_exit_code": 0, "candidate_sha": SHA,
            "source_sha256": "b" * 64, "engine_version": "5.8.3", "binary_sha256": "c" * 64,
            "build_log_sha256": "d" * 64}


def report(platform="Linux"):
    return {"devices": [{"instance": DEVICE, "platform": platform}], "succeeded": 23,
            "succeededWithWarnings": 0, "failed": 0, "notRun": 0, "inProcess": 0,
            "tests": [{"fullTestPath": path, "state": "Success", "errors": 0, "warnings": 0,
                       "deviceInstance": [DEVICE], "entries": []} for path in scorer.EXPECTED_PATHS]}


class ScoreUEReportTests(unittest.TestCase):
    def test_complete_linux_report_is_final(self):
        result = scorer.score_report(report(), build(), SHA)
        self.assertTrue(result["valid_evidence"], result["problems"])
        self.assertTrue(result["final_pass"])
        self.assertEqual(result["score"], 100)

    def test_missing_duplicate_unexpected_and_zero_tests_fail_closed(self):
        variants = []
        missing = report()
        missing["tests"].pop()
        missing["succeeded"] -= 1
        variants.append(missing)
        duplicate = report()
        duplicate["tests"].append(copy.deepcopy(duplicate["tests"][0]))
        variants.append(duplicate)
        unexpected = report()
        unexpected["tests"][0]["fullTestPath"] = "Unrelated.Test"
        variants.append(unexpected)
        empty = report()
        empty["tests"] = []
        empty["succeeded"] = 0
        variants.append(empty)
        for value in variants:
            with self.subTest(count=len(value["tests"])):
                result = scorer.score_report(value, build(), SHA)
                self.assertFalse(result["valid_evidence"])
                self.assertFalse(result["final_pass"])
                self.assertEqual(result["score"], 0)

    def test_windows_needs_flag_and_remains_not_final(self):
        rejected = scorer.score_report(report("Windows"), build("Win64"), SHA)
        self.assertFalse(rejected["valid_evidence"])
        accepted = scorer.score_report(report("Windows"), build("Win64"), SHA, True)
        self.assertTrue(accepted["valid_evidence"], accepted["problems"])
        self.assertEqual(accepted["score"], 100)
        self.assertEqual(accepted["status"], "calibration_pass")
        self.assertFalse(accepted["is_final"])
        self.assertFalse(accepted["final_pass"])

    def test_build_failure_missing_hash_and_wrong_candidate_reject(self):
        failed = build()
        failed["build_exit_code"] = 1
        missing = build()
        del missing["binary_sha256"]
        mismatch = build()
        mismatch["candidate_sha"] = "e" * 40
        for value in (failed, missing, mismatch):
            with self.subTest(value=value):
                result = scorer.score_report(report(), value, SHA)
                self.assertFalse(result["valid_evidence"])
                self.assertEqual(result["score"], 0)

    def test_skipped_and_in_process_are_incomplete(self):
        for state in ("Skipped", "NotRun", "InProcess"):
            value = report()
            value["tests"][0]["state"] = state
            value["succeeded"] -= 1
            result = scorer.score_report(value, build(), SHA)
            self.assertFalse(result["valid_evidence"])
            self.assertEqual(result["incomplete_tests"], [scorer.EXPECTED_PATHS[0]])

    def test_real_case_failure_keeps_valid_partial_score(self):
        value = report()
        value["tests"][0].update(state="Fail", errors=2)
        value["succeeded"] -= 1
        value["failed"] = 1
        result = scorer.score_report(value, build(), SHA)
        self.assertTrue(result["valid_evidence"], result["problems"])
        self.assertEqual(result["score"], 95)
        self.assertEqual(result["status"], "final_fail")
        self.assertFalse(result["final_pass"])

    def test_success_with_errors_gets_no_credit(self):
        value = report()
        value["tests"][0]["errors"] = 1
        result = scorer.score_report(value, build(), SHA)
        self.assertTrue(result["valid_evidence"])
        self.assertEqual(result["score"], 95)

    def test_platform_must_belong_to_actual_test_device(self):
        value = report("Windows")
        value["devices"].append({"instance": "f" * 32, "platform": "Linux"})
        result = scorer.score_report(value, build(), SHA)
        self.assertFalse(result["valid_evidence"])
        value = report()
        value["tests"][0]["deviceInstance"] = ["f" * 32]
        result = scorer.score_report(value, build(), SHA)
        self.assertFalse(result["valid_evidence"])

    def test_summary_mismatch_and_bool_counts_reject(self):
        value = report()
        value["succeeded"] = 0
        self.assertFalse(scorer.score_report(value, build(), SHA)["valid_evidence"])
        value = report()
        value["tests"][0]["errors"] = False
        self.assertFalse(scorer.score_report(value, build(), SHA)["valid_evidence"])


if __name__ == "__main__":
    unittest.main()
