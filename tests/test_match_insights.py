import copy
import unittest
from datetime import timedelta

from tests.test_solo import NOW, sample
from scripts.analyze import create_analysis
from scripts.match_insights import (
    build, history_index, last_games, recent_h2h,
    team_digest, table_position, validate
)


def league_db():
    data=[]
    # 6 results, all known before the Nov 12 observation
    for day in range(1,7):
        data.append({"date":f"2026-11-{day:02d}",
          "home":"home 1", "away":"away 1",
          "home_goals":2, "away_goals":0,
          "league":"en.1","season":"2026-27"})
    data += [
        {"date":"2026-11-08","home":"away 1","away":"home 1",
         "home_goals":1,"away_goals":1,"league":"en.1","season":"2026-27"},
        {"date":"2026-11-12","home":"home 1","away":"away 1",
         "home_goals":0,"away_goals":8,"league":"en.1","season":"2026-27"},
        {"date":"2026-11-13","home":"home 1","away":"away 1",
         "home_goals":0,"away_goals":8,"league":"en.1","season":"2026-27"},
    ]
    return data


class DeepInsightsTests(unittest.TestCase):
    def setUp(self):
        self.base=create_analysis(sample())
        self.db=league_db()

    def test_strict_cutoff_and_recent_facts(self):
        r=build(self.base,self.db,1,NOW+timedelta(minutes=1))
        self.assertTrue(validate(r,self.base))
        self.assertEqual(r["cutoff_date_exclusive"],"2026-11-12")
        h=r["matches"][0]["home_facts"]
        self.assertEqual(h["last_match_date"],"2026-11-08")
        self.assertEqual(h["days_since_last_match_at_observation"],4)
        self.assertEqual(h["last10_matches"][0]["opponent"],"away 1")
        self.assertEqual(h["last10_matches"][0]["outcome"],"O")
        self.assertNotIn("2026-11-12",[x["date"] for x in h["last10_matches"]])
        self.assertEqual(h["unbeaten_streak"],7)
        self.assertGreater(h["matches_last_14_days"],0)

    def test_future_results_do_not_change_old_insights(self):
        before=build(self.base,self.db,1,NOW+timedelta(minutes=1))
        changed=copy.deepcopy(self.db)
        changed[-1]["home_goals"]=20
        changed[-2]["home_goals"]=20
        after=build(self.base,changed,1,NOW+timedelta(minutes=1))
        self.assertEqual(before["matches"],after["matches"])

    def test_no_false_opposition_strength_when_missing(self):
        r=build(self.base,self.db,1,NOW+timedelta(minutes=1))
        self.assertIsNone(r["matches"][1]["home_facts"]["opponent_pre_form_ppg_last5"])
        self.assertEqual(r["matches"][1]["home_facts"]["last10_matches"],[])

    def test_h2h_only_before_cutoff(self):
        ix=history_index(self.db)
        h2h=recent_h2h(ix,"Home 1","Away 1","2026-11-12")
        self.assertEqual(len(h2h),5)
        self.assertTrue(all(x["date"]<"2026-11-12" for x in h2h))

    def test_inferred_table_is_not_official(self):
        ix=history_index(self.db)
        t=table_position(self.db,ix,"Home 1","2026-11-12")
        self.assertIsNotNone(t)
        self.assertIn("ej officiell",t["method"])
        self.assertEqual(t["season"],"2026-27")
        self.assertIsNone(table_position(self.db,ix,"Home 1","2027-05-01"))

    def test_report_requires_before_close(self):
        with self.assertRaises(ValueError):
            build(self.base,self.db,1,NOW+timedelta(days=2))

    def test_report_rejects_tampering(self):
        r=build(self.base,self.db,1,NOW+timedelta(minutes=1))
        r["matches"][0]["home_facts"]["last10_matches"][0]["date"]="2026-11-15"
        self.assertFalse(validate(r,self.base))


if __name__=="__main__":
    unittest.main()
