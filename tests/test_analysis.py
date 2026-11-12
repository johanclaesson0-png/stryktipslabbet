import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.collect import parse_draw, parse_result, write_json
from scripts.analyze import (
    BUDGET, analyze_all, correct_rows, create_analysis, create_settlement,
    optimize, probabilities, settle_all, system_rows, valid_analysis
)

NOW = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)


def coupon():
    events = []
    for i in range(1, 14):
        events.append({
            "eventNumber": i,
            "match": {
                "participants": [
                    {"type": "home", "name": "Hemmalag " + str(i)},
                    {"type": "away", "name": "Bortalag " + str(i)},
                ],
                "matchStart": (NOW + timedelta(days=1)).isoformat(),
            },
            "odds": {"one": "2,20", "x": "3,30", "two": "3,10"},
            "svenskaFolket": {"one": 45, "x": 25, "two": 30},
        })
    return {"draw": {
        "drawNumber": 9999, "productName": "Stryktipset", "productId": 1,
        "drawState": "Open", "regCloseTime": (NOW + timedelta(hours=12)).isoformat(),
        "drawEvents": events
    }}


def result():
    return {"result": {
        "productName": "Stryktipset", "drawNumber": 9999,
        "events": [{"eventNumber": i, "outcome": "1"} for i in range(1, 14)],
        "distribution": [{"name": str(i) + " rätt", "amount": {"10": 100, "11": 300,
                         "12": 1000, "13": 50000}[str(i)]} for i in (10, 11, 12, 13)],
    }}


class AutomaticAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.snap = parse_draw(coupon(), 9999, NOW)
        self.snap["sha256"] = "a" * 64

    def test_normalized_odds(self):
        p = probabilities([1.5, 5.0, 8.0])
        self.assertAlmostEqual(sum(p), 1.0, 12)
        self.assertGreater(p[0], p[1])

    def test_three_consistent_systems_under_budget(self):
        a = create_analysis(self.snap)
        self.assertTrue(valid_analysis(a, NOW))
        self.assertEqual([s["key"] for s in a["systems"]], ["balanserad", "varde", "skrall"])
        for s in a["systems"]:
            self.assertLessEqual(s["cost"], BUDGET)
            self.assertEqual(s["cost"], system_rows(tuple(
                sum(1 << "1X2".index(c) for c in choice) for choice in s["choices"]
            )))
            self.assertGreater(s["p13_estimate"], 0)

    def test_budget_optimizer_prefers_all_coverage_if_budget_allows(self):
        cost, masks = optimize([[0.4, 0.3, 0.3]] * 13, budget=1_600_000)
        self.assertEqual(cost, 3 ** 13)
        self.assertEqual(masks, (7,) * 13)

    def test_outcomes_frozen_and_independent(self):
        a = create_analysis(self.snap)
        self.assertNotIn("outcome", json.dumps(a))
        self.assertNotIn("payouts", json.dumps(a))

    def test_correct_rows_multiplicities(self):
        c = ["1X"] + ["1"] * 12
        dist = correct_rows(c, "1" * 13)
        self.assertEqual(dist[13], 1)
        self.assertEqual(dist[12], 1)
        self.assertEqual(sum(dist), 2)

    def test_reject_after_close_snapshot(self):
        self.snap["observed_at_utc"] = (NOW + timedelta(hours=13)).isoformat()
        with self.assertRaises(ValueError):
            create_analysis(self.snap)

    def test_no_double_count_and_settlement(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            folder = data / "snapshots" / "9999"
            write_json(folder / "real-observation.json", self.snap)
            self.assertEqual(analyze_all(data, NOW), 1)
            self.assertEqual(analyze_all(data, NOW), 0)
            saved = json.loads((data / "analysis" / "9999.json").read_text())
            self.assertTrue(valid_analysis(saved, NOW))
            real = parse_result(result(), 9999, NOW + timedelta(days=3))
            write_json(data / "results" / "9999.json", real)
            self.assertEqual(settle_all(data, NOW + timedelta(days=3)), 1)
            self.assertEqual(settle_all(data, NOW + timedelta(days=3)), 0)
            paid = json.loads((data / "settlements" / "9999.json").read_text())
            self.assertEqual(paid["draw_number"], 9999)
            self.assertTrue(paid["hypothetical"])
            self.assertEqual(len(paid["systems"]), 3)
            for s in paid["systems"]:
                self.assertAlmostEqual(s["paid"] - s["cost"], s["net"], places=2)

    def test_invalid_result_not_settled(self):
        a = create_analysis(self.snap)
        real = parse_result(result(), 9999, NOW + timedelta(days=3))
        real["draw_number"] = 9998
        with self.assertRaises(ValueError):
            create_settlement(a, real)


if __name__ == "__main__":
    unittest.main()
