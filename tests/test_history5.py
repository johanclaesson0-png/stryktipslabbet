import unittest
from pathlib import Path
from scripts.history5 import read_rounds, summarize, pre_match_p, START

ROOT = Path(__file__).resolve().parents[1]

class FiveYearsHistoryTests(unittest.TestCase):
    def test_import_is_exactly_five_years_of_complete_draws(self):
        rows=read_rounds(ROOT / "data" / "history" / "stryktipset-five-years.csv")
        self.assertGreaterEqual(len(rows),250)
        self.assertEqual(rows[0]["date"],START)
        self.assertEqual(len({r["draw"] for r in rows}),len(rows))
        self.assertTrue(all(len(r["matches"])==13 for r in rows))

    def test_elo_uses_only_ratings_passed_to_it(self):
        a=pre_match_p("home","away",{}, {})
        b=pre_match_p("home","away",{}, {})
        self.assertEqual(a,b)
        self.assertAlmostEqual(sum(a),1,places=9)
        c=pre_match_p("home","away",{"home":1800},{"home":15})
        self.assertGreater(c[0],a[0])

    def test_summary_separates_early_training_and_later_tests(self):
        rows=read_rounds(ROOT / "data" / "history" / "stryktipset-five-years.csv")
        report=summarize(rows)
        self.assertEqual(report["schema"],"stryktipslabbet-five-years-v1")
        self.assertEqual(report["rounds"],len(rows))
        self.assertEqual(report["matches"],len(rows)*13)
        self.assertEqual(len(report["archive"]),len(rows))
        self.assertEqual(sum(report["outcomes"].values()),len(rows)*13)
        self.assertTrue(report["backtest"]["test_draws"]<len(rows))
        self.assertGreater(report["backtest"]["test_draws"],150)
        self.assertTrue(all(x["date"]<="2026-11-13" for x in report["archive"]))
if __name__=="__main__":
    unittest.main()
