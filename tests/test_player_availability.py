import unittest
from datetime import timedelta
from tests.test_solo import sample, NOW
from scripts.analyze import create_analysis
from scripts.player_availability import build, verify_report
from scripts.league_history import team_form

class PlayerSourceTests(unittest.TestCase):
    def setUp(self):
        self.analysis=create_analysis(sample())
        self.verified={"team":"Home 1","player":"Exempelspelare (testdata)",
                "status":"out","publisher":"Testklubb",
                "source_url":"https://example.org/official/test",
                "reported_at_utc":(NOW-timedelta(hours=2)).isoformat(),
                "checked_at_utc":(NOW-timedelta(hours=1)).isoformat(),
                "verified_by":"manual_source_review"}

    def test_source_must_precede_observation(self):
        self.assertTrue(verify_report(self.verified,NOW))
        r={**self.verified,"checked_at_utc":(NOW+timedelta(hours=1)).isoformat()}
        self.assertFalse(verify_report(r,NOW))
        r={**self.verified,"source_url":"http://example.org"}
        self.assertFalse(verify_report(r,NOW))
        r={**self.verified,"verified_by":"unknown"}
        self.assertFalse(verify_report(r,NOW))

    def test_no_source_never_means_all_players_available(self):
        result=build(self.analysis,[],NOW+timedelta(minutes=1))
        self.assertEqual(result["reports_included"],0)
        self.assertEqual(result["matches"][0]["home"]["coverage"],"ej verifierat – okänt")
        self.assertNotIn("skadefri",result["matches"][0]["home"]["coverage"])

    def test_valid_report_is_source_linked_but_model_not_changed(self):
        report=build(self.analysis,[self.verified],NOW+timedelta(minutes=1))
        self.assertEqual(report["reports_included"],1)
        src=report["matches"][0]["home"]["reported_absences"][0]
        self.assertEqual(src["source_url"],self.verified["source_url"])
        self.assertEqual(src["status_label"],"Rapporterad frånvaro")

    def test_recent_matches_never_include_current_day(self):
        games=[]
        for i in range(1,8):
            games.append({"date":f"2026-11-{i:02d}","home":"home 1","away":"away 1",
                          "home_goals":i%4,"away_goals":1,"league":"en.1"})
        games.append({"date":"2026-11-12","home":"home 1","away":"away 1",
                      "home_goals":9,"away_goals":0,"league":"en.1"})
        data=team_form("Home 1","2026-11-12",games,"home")
        self.assertEqual(len(data["last5_matches"]),5)
        self.assertNotIn("2026-11-12",[r["date"] for r in data["last5_matches"]])
        self.assertEqual(data["last5_matches"][0]["date"],"2026-11-07")
        self.assertEqual(data["last5_matches"][0]["opponent"],"away 1")

if __name__=="__main__":
    unittest.main()
