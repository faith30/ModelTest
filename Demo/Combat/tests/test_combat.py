import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from combat import simulate


def event_types(step):
    return [event["type"] for event in step["events"]]


class CombatTests(unittest.TestCase):
    def test_damage_healing_and_overheal(self):
        result = simulate({"actions": [{"type": "damage", "amount": 30},
                                       {"type": "heal", "amount": 20},
                                       {"type": "heal", "amount": 50}]})
        self.assertEqual([step["after"]["health"] for step in result["steps"]], [70, 90, 100])
        self.assertEqual(result["state"]["death_state"], "NotDead")
        self.assertEqual(result["steps"][0]["action"]["self_destruct"], False)

    def test_immunity_blocks_normal_but_not_tagged_damage(self):
        result = simulate({"initial": {"damage_immunity": True}, "actions": [
            {"type": "damage", "amount": 30},
            {"type": "damage", "amount": 100, "self_destruct": True}]})
        blocked, tagged = result["steps"]
        self.assertEqual(blocked["before"], blocked["after"])
        self.assertEqual(event_types(blocked), ["damage_blocked"])
        self.assertEqual(tagged["after"]["health"], 0)
        self.assertIn("out_of_health", event_types(tagged))
        self.assertEqual(tagged["after"]["death_state"], "NotDead")

    def test_out_of_health_is_rearmed_by_healing_without_reviving(self):
        result = simulate({"actions": [
            {"type": "damage", "amount": 150}, {"type": "damage", "amount": 10},
            {"type": "start_death"}, {"type": "finish_death"},
            {"type": "heal", "amount": 25}, {"type": "damage", "amount": 25}]})
        steps = result["steps"]
        self.assertIn("out_of_health", event_types(steps[0]))
        self.assertNotIn("out_of_health", event_types(steps[1]))
        self.assertNotIn("health_changed", event_types(steps[1]))
        self.assertEqual(steps[4]["after"]["health"], 25)
        self.assertFalse(steps[4]["after"]["out_of_health"])
        self.assertEqual(steps[4]["after"]["death_state"], "DeathFinished")
        self.assertIn("out_of_health", event_types(steps[5]))

    def test_death_transition_guards_are_idempotent(self):
        result = simulate({"actions": [{"type": kind} for kind in [
            "finish_death", "start_death", "start_death", "finish_death", "finish_death", "start_death"]]})
        self.assertEqual([step["after"]["death_state"] for step in result["steps"]], [
            "NotDead", "DeathStarted", "DeathStarted", "DeathFinished", "DeathFinished", "DeathFinished"])
        self.assertEqual([event_types(step)[0] for step in result["steps"]], [
            "no_op", "death_started", "no_op", "death_finished", "no_op", "no_op"])
        self.assertEqual(result["state"]["health"], 100)

    def test_max_health_clamp_and_increase_without_healing(self):
        result = simulate({"actions": [{"type": "set_max_health", "value": value}
                                       for value in (40, 200, 0, -5)]})
        self.assertEqual([(step["after"]["health"], step["after"]["max_health"])
                          for step in result["steps"]], [(40, 40), (40, 200), (1, 1), (1, 1)])
        self.assertFalse(result["state"]["out_of_health"])

    def test_initial_clamp_zero_and_empty_actions(self):
        result = simulate({"initial": {"health": 100, "max_health": -10}, "actions": []})
        self.assertEqual(result["state"]["health"], 1)
        self.assertEqual(result["state"]["max_health"], 1)
        zero = simulate({"initial": {"health": 0}, "actions": [{"type": "damage", "amount": 5}]})
        self.assertTrue(zero["initial"]["out_of_health"])
        self.assertNotIn("out_of_health", event_types(zero["steps"][0]))

    def test_caller_and_snapshots_are_independent(self):
        payload = {"initial": {"health": 80}, "actions": [{"type": "damage", "amount": 20}]}
        original = copy.deepcopy(payload)
        result = simulate(payload)
        self.assertEqual(payload, original)
        result["steps"][0]["after"]["health"] = 777
        result["steps"][0]["action"]["amount"] = 777
        self.assertEqual(result["state"]["health"], 60)
        self.assertEqual(result["initial"]["health"], 80)
        self.assertEqual(payload, original)

    def test_reject_invalid_numbers_and_boolean_numbers(self):
        for value in (True, "5", None, float("nan"), float("inf"), -float("inf"), 1e10, 10 ** 400, -1):
            with self.subTest(value=str(value)):
                with self.assertRaises(ValueError):
                    simulate({"actions": [{"type": "damage", "amount": value}]})
        for initial in ({"health": -1}, {"health": True}, {"max_health": False},
                        {"max_health": float("nan")}, {"damage_immunity": 1}):
            with self.subTest(initial=initial), self.assertRaises(ValueError):
                simulate({"initial": initial, "actions": []})
        with self.assertRaises(ValueError):
            simulate({"actions": [{"type": "heal", "amount": -1}]})
        with self.assertRaises(ValueError):
            simulate({"actions": [{"type": "set_max_health", "value": -1e10}]})

    def test_reject_unknown_missing_and_wrong_type_fields(self):
        bad = [None, [], {}, {"actions": {}}, {"actions": [], "typo": 1},
               {"initial": None, "actions": []}, {"initial": {"death_state": "NotDead"}, "actions": []}]
        bad_actions = [None, {}, {"type": []}, {"type": "unknown"}, {"type": "damage"},
                       {"type": "damage", "amount": 1, "typo": 1},
                       {"type": "damage", "amount": 1, "self_destruct": "true"},
                       {"type": "set_immunity", "enabled": 1},
                       {"type": "start_death", "amount": 1}]
        bad.extend({"actions": [action]} for action in bad_actions)
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                simulate(payload)

    def test_action_limit_and_full_validation_before_execution(self):
        valid = {"actions": [{"type": "heal", "amount": 0}] * 200}
        self.assertEqual(len(simulate(valid)["steps"]), 200)
        with self.assertRaises(ValueError):
            simulate({"actions": valid["actions"] + [{"type": "start_death"}]})
        payload = {"actions": [{"type": "damage", "amount": 90}, {"type": "heal"}]}
        original = copy.deepcopy(payload)
        with self.assertRaisesRegex(ValueError, r"actions\[2\]"):
            simulate(payload)
        self.assertEqual(payload, original)

    def test_bundled_scenarios_are_valid(self):
        path = Path(__file__).resolve().parents[1] / "scenarios.json"
        scenarios = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(set(scenarios), {"normal", "immunity", "lethal", "max_health"})
        expected = {"normal": (100, "NotDead"), "immunity": (0, "NotDead"),
                    "lethal": (25, "DeathFinished"), "max_health": (1, "NotDead")}
        for name, scenario in scenarios.items():
            with self.subTest(scenario=name):
                result = simulate({"initial": scenario["initial"], "actions": scenario["actions"]})
                self.assertEqual((result["state"]["health"], result["state"]["death_state"]), expected[name])
                self.assertEqual(set(result["state"]), {"health", "max_health", "damage_immunity", "out_of_health", "death_state"})
                for step in result["steps"]:
                    self.assertTrue(all(set(event) == {"type", "message"} for event in step["events"]))


if __name__ == "__main__":
    unittest.main()
