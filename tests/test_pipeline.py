import unittest
from datetime import datetime, timedelta, timezone
from scripts.collect import choose_draw, parse_draw, parse_result, should_collect
from scripts.publish import valid_snapshot, valid_result

NOW = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)


def sample():
    events = []
    for i in range(1, 14):
        events.append({
            "eventNumber": i,
            "match": {
                "participants": [
                    {"type": "home", "name": f"Hemmalag {i}"},
                    {"type": "away", "name": f"Bortalag {i}"}
                ],
                "matchStart": (NOW + timedelta(days=1)).isoformat(),
            },
            "odds": {"one": "2,20", "x": "3,30", "two": "3,10"},
            "svenskaFolket": {"one": 45, "x": 25, "two": 30},
        })
    return {"draw": {
        "drawNumber": 9999, "productName": "Stryktipset", "productId": 1,
        "drawState": "Open",
        "regCloseTime": (NOW + timedelta(hours=12)).isoformat(),
        "drawEvents": events
    }}


class TestDataIntegrity(unittest.TestCase):
    def test_choose_future_draw(self):
        d = {"draws": [
            {"drawState": "Finished", "regCloseTime": NOW.isoformat(), "drawNumber": 1},
            {"drawState": "Open", "regCloseTime": (NOW + timedelta(hours=12)).isoformat(), "drawNumber": 2},
        ]}
        self.assertEqual(choose_draw(d, NOW), 2)

    def test_accept_valid_pre_close_snapshot(self):
        d = parse_draw(sample(), 9999, NOW)
        self.assertTrue(valid_snapshot(d, NOW))

    def test_reject_future_dated_observation(self):
        d = parse_draw(sample(), 9999, NOW)
        self.assertFalse(valid_snapshot(d, NOW - timedelta(seconds=1)))

    def test_reject_observation_at_stop(self):
        with self.assertRaises(ValueError):
            parse_draw(sample(), 9999, NOW + timedelta(hours=12))

    def test_reject_missing_odds(self):
        d = sample()
        del d["draw"]["drawEvents"][0]["odds"]
        with self.assertRaises(ValueError):
            parse_draw(d, 9999, NOW)

    def test_reject_wrong_draw_number(self):
        with self.assertRaises(ValueError):
            parse_draw(sample(), 9998, NOW)

    def test_reject_12_events(self):
        d = sample()
        d["draw"]["drawEvents"].pop()
        with self.assertRaises(ValueError):
            parse_draw(d, 9999, NOW)

    def test_skip_fresh_snapshot(self):
        snap = parse_draw(sample(), 9999, NOW)
        self.assertFalse(should_collect(snap, NOW + timedelta(minutes=30)))

    def test_result_validation(self):
        doc = {"result": {
            "productName": "Stryktipset", "drawNumber": 9999,
            "events": [{"eventNumber": i, "outcome": "1"} for i in range(1, 14)],
            "distribution": [{"name": str(i) + " rätt", "amount": "100,00"}
                             for i in (10, 11, 12, 13)]
        }}
        when = NOW + timedelta(days=2)
        outcome = parse_result(doc, 9999, when)
        self.assertTrue(valid_result(outcome, {9999: NOW + timedelta(hours=12)}, when))
        self.assertFalse(valid_result(outcome, {9999: NOW + timedelta(days=3)}, when))


if __name__ == "__main__":
    unittest.main()
