import unittest
from datetime import datetime, timedelta, timezone
from scripts.collect import parse_draw, parse_result
from scripts.analyze import create_analysis
from scripts.solo import derive, validate, settle

NOW = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)


def sample():
    events = [{
        "eventNumber": i,
        "match": {
            "participants": [
                {"type": "home", "name": "Home "+str(i)},
                {"type": "away", "name": "Away "+str(i)}
            ],
            "matchStart": (NOW + timedelta(days=1)).isoformat()
        },
        "odds": {"one": 2.10, "x": 3.25, "two": 3.55},
        "svenskaFolket": {"one": 50, "x": 25, "two": 25},
    } for i in range(1, 14)]
    return parse_draw({"draw": {
        "drawNumber": 9999, "productName": "Stryktipset", "productId": 1,
        "drawState": "Open",
        "regCloseTime": (NOW + timedelta(hours=12)).isoformat(),
        "drawEvents": events
    }}, 9999, NOW)


class PersonalModeTests(unittest.TestCase):
    def setUp(self):
        self.original = create_analysis(sample())
        self.personal = derive(self.original, NOW)

    def test_96_kr_systems_and_origin(self):
        self.assertTrue(validate(self.personal, self.original))
        for s in self.personal["systems"]:
            self.assertLessEqual(s["cost"], 100)
            self.assertEqual(s["cost"], 96)
            self.assertEqual(len(s["choices"]), 13)

    def test_no_lookahead_or_fake_payouts(self):
        text = str(self.personal)
        self.assertNotIn("outcome", text)
        self.assertNotIn("payouts", text)
        self.assertTrue(self.personal["derived_before_close"])

    def test_after_close_label_when_reconstructing(self):
        late = derive(self.original, NOW + timedelta(days=2))
        self.assertFalse(late["derived_before_close"])
        self.assertTrue(validate(late, self.original))

    def test_reject_tampered_row_cost(self):
        self.personal["systems"][0]["cost"] = 200
        self.assertFalse(validate(self.personal, self.original))

    def test_official_result_settlement(self):
        doc = {"result": {
            "productName": "Stryktipset", "drawNumber": 9999,
            "events": [{"eventNumber": i, "outcome": "1"} for i in range(1, 14)],
            "distribution": [{"name": str(i)+" rätt", "amount": 100} for i in (10, 11, 12, 13)]
        }}
        result = parse_result(doc, 9999, NOW + timedelta(days=3))
        settlement = settle(self.personal, result)
        self.assertEqual(len(settlement["systems"]), 3)
        for s in settlement["systems"]:
            self.assertEqual(s["net"], s["paid"]-s["cost"])


if __name__ == "__main__":
    unittest.main()
