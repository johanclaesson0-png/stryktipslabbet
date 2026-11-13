import unittest
from datetime import datetime, timedelta, timezone
from tests.test_solo import sample, NOW
from scripts.analyze import create_analysis
from scripts.league_history import key_team, parse_source, team_form, build_features, result_for

class LeagueHistoryTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(key_team("Manchester U"), key_team("Manchester United FC"))
        self.assertEqual(key_team("Brighton"), key_team("Brighton & Hove Albion FC"))
        self.assertEqual(key_team("Queens Park Rangers"), key_team("QPR"))
        self.assertNotEqual(key_team("Bristol City"), key_team("Bristol Rovers"))

    def test_parse_only_known_finished_matches(self):
        doc={"matches":[
          {"date":"2026-11-%02d"%(i+1),"team1":"Manchester United FC","team2":"AFC Bournemouth",
           "score":{"ft":[1,0]}} for i in range(20)
        ] + [{"date":"2026-12-01","team1":"A","team2":"B","score":{}}]}
        out=parse_source(doc,"2026-27","en.1",NOW)
        self.assertEqual(len(out["matches"]),20)
        self.assertEqual(out["matches"][0]["home"],"manchester united")
        self.assertTrue(all(x["date"]!="2026-12-01" for x in out["matches"]))

    def test_no_today_or_future_results_in_form(self):
        db=[
          {"date":"2026-11-09","home":"manchester united","away":"arsenal","home_goals":2,"away_goals":1},
          {"date":"2026-11-12","home":"arsenal","away":"manchester united","home_goals":4,"away_goals":0},
          {"date":"2026-11-13","home":"manchester united","away":"arsenal","home_goals":10,"away_goals":0},
          {"date":"2026-11-14","home":"manchester united","away":"arsenal","home_goals":10,"away_goals":0},
        ]
        form=team_form("Manchester U","2026-11-13",db,"home")
        self.assertEqual(form["last5"]["n"],2)
        self.assertEqual(form["last5"]["goals_for_per_game"],1)
        self.assertEqual(form["venue5"]["n"],1)
        self.assertEqual(form["venue5"]["goals_for_per_game"],2)

    def test_missing_team_is_explicit(self):
        a=create_analysis(sample())
        db=[{"date":"2026-11-09","home":"liverpool","away":"chelsea","home_goals":2,"away_goals":0}]
        features=build_features(a,db,1,created=NOW+timedelta(minutes=1))
        self.assertEqual(len(features["matches"]),13)
        self.assertEqual(features["missing_matches"],13)
        self.assertLess(features["created_at_utc"],features["reg_close_time"])
        self.assertEqual(features["cutoff_date_exclusive"],"2026-11-12")

    def test_result_for_team_away(self):
        game={"date":"2026-10-01","home":"team a","away":"team b","home_goals":0,"away_goals":3}
        r=result_for("team b",game)
        self.assertEqual(r["points"],3)
        self.assertEqual(r["gf"],3)
        self.assertEqual(r["venue"],"away")

    def test_reject_post_close_form_creation(self):
        a=create_analysis(sample())
        with self.assertRaises(ValueError):
            build_features(a,[],0,created=NOW+timedelta(days=1))

if __name__=="__main__":
    unittest.main()
