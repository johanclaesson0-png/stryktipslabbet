import copy
import unittest
from datetime import datetime, timedelta, timezone

from tests.test_solo import sample, NOW
from scripts.analyze import create_analysis
from scripts.solo import derive as derive_solo
from scripts.spikvakt import (
    SPIKE_LIMIT, DRAW_LIMIT, VERSION, build, exact_cost_optimizer,
    risk_report, settle, validate
)
from scripts.collect import parse_result

class SpikvaktTests(unittest.TestCase):
    def setUp(self):
        self.analysis = create_analysis(sample())
        self.solo = derive_solo(self.analysis, NOW)
        self.report = build(self.analysis, self.solo, created=NOW + timedelta(minutes=2))

    def test_frozen_source_validates_without_outcome(self):
        self.assertTrue(validate(self.report, self.analysis, self.solo))
        self.assertEqual(self.report["version"], VERSION)
        self.assertLess(self.report["created_at_utc"], self.report["reg_close_time"])
        self.assertNotIn("outcome", str(self.report))
        self.assertNotIn("payouts", str(self.report))

    def test_same_row_cost_for_all_comparisons(self):
        for group in self.report["budgets"]:
            self.assertEqual([x["key"] for x in group["experiments"]], ["safe", "draw"])
            self.assertIn(group["budget"], (100, 1800))
            for alt in group["experiments"]:
                self.assertEqual(alt["cost"], group["baseline_cost"])
                self.assertEqual(alt["cost"], self._product(alt["choices"]))
                self.assertEqual(len(alt["choices"]), 13)
                self.assertGreater(alt["estimated_p13"], 0)
            self.assertEqual(group["baseline_cost"], self._product(group["baseline_choices"]))

    @staticmethod
    def _product(choices):
        n = 1
        for c in choices:
            n *= len(c)
        return n

    def test_optimizer_fails_if_cost_cannot_be_reached(self):
        with self.assertRaises(ValueError):
            exact_cost_optimizer([[.6, .25, .15]] * 13, 5, "safe")

    def test_no_retrospective_experiments(self):
        with self.assertRaises(ValueError):
            build(self.analysis, self.solo, NOW + timedelta(days=1))
        with self.assertRaises(ValueError):
            build(self.analysis, self.solo, NOW - timedelta(minutes=5))

    def test_reject_tampering(self):
        bad = copy.deepcopy(self.report)
        bad["budgets"][0]["experiments"][0]["cost"] += 1
        self.assertFalse(validate(bad, self.analysis, self.solo))
        bad = copy.deepcopy(self.report)
        bad["created_at_utc"] = (NOW + timedelta(days=1)).isoformat()
        self.assertFalse(validate(bad, self.analysis, self.solo))

    def test_spike_and_draw_reporting(self):
        p = [{"p": [.44, .30, .26], "home": "H", "away": "B"}] * 13
        results = risk_report(["1"] * 13, p)
        self.assertEqual(len(results["spikes"]), 13)
        self.assertEqual(len(results["possible_draws"]), 13)
        self.assertTrue(results["spikes"][0]["high_risk"])
        self.assertEqual(results["possible_draws"][0]["extra_row_cost_to_include_x_alone"], 2)
        self.assertEqual(results["spikes"][0]["suggested_second_sign"], "X")
        self.assertEqual(results["spikes"][0]["cost_if_added_without_rebalancing"], 2)
        self.assertAlmostEqual(results["spikes"][0]["extra_outcome_probability"], .30)
        self.assertEqual(SPIKE_LIMIT, .55)
        self.assertEqual(DRAW_LIMIT, .27)

    def test_result_settlement_separate_and_hypothetical(self):
        d = {"result": {"productName": "Stryktipset", "drawNumber": 9999,
             "events": [{"eventNumber": i, "outcome": "1"} for i in range(1, 14)],
             "distribution": [{"name": str(i) + " rätt", "amount": 100} for i in (10, 11, 12, 13)]}}
        result = parse_result(d, 9999, NOW + timedelta(days=3))
        settled = settle(self.report, result)
        self.assertTrue(settled["hypothetical"])
        self.assertEqual(len(settled["budgets"]), 2)
        for group in settled["budgets"]:
            self.assertEqual(len(group["experiments"]), 2)
            for exp in group["experiments"]:
                self.assertAlmostEqual(exp["net"], exp["paid"] - exp["cost"], places=2)

if __name__ == "__main__":
    unittest.main()
