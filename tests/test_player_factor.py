import unittest
from datetime import timedelta
from scripts.analyze import create_analysis
from scripts.solo import derive
from scripts.player_availability import build as availability_build, verify_report
from scripts.player_factor import build, importance, validate
from scripts.player_provider import resolve_fixture, injury_status
from tests.test_solo import sample, NOW


class PlayerFactorTests(unittest.TestCase):
    def setUp(self):
        self.base=create_analysis(sample())
        self.solo=derive(self.base,NOW)
        self.now=NOW+timedelta(minutes=1)
        self.record={
            "draw_number":9999,"match_number":1,
            "team":"Home 1","player":"Test key player",
            "provider_player_id":34,"provider_team_id":22,"provider_fixture_id":987,
            "status":"out","publisher":"API-Football",
            "source_url":"https://v3.football.api-sports.io/injuries?fixture=987",
            "reported_at_utc":(NOW-timedelta(minutes=5)).isoformat(),
            "checked_at_utc":(NOW-timedelta(minutes=5)).isoformat(),
            "verified_by":"api_football",
            "stats":{"starts":18,"appearances":20,"minutes":1650,
                     "team_matches":20,"goals":12,"assists":5,
                     "position":"Attacker","complete":True}
        }

    def test_importance_rewards_core_player(self):
        self.assertGreater(importance(self.record),0.75)
        reserve={**self.record,"stats":{**self.record["stats"],
                 "starts":1,"appearances":7,"minutes":145,"goals":0,"assists":0}}
        self.assertLess(importance(reserve),importance(self.record))
        self.assertIsNone(importance({**self.record,"stats":None}))

    def test_scenario_keeps_original_models_and_budget(self):
        self.assertTrue(verify_report(self.record,NOW))
        avail=availability_build(self.base,[self.record],self.now)
        scenario=build(self.base,avail,self.solo,created=self.now)
        self.assertTrue(validate(scenario,self.base,avail,self.solo))
        self.assertGreater(scenario["used_player_count"],0)
        self.assertLess(scenario["matches"][0]["player_p"][0],self.base["matches"][0]["p"][0])
        self.assertGreater(scenario["matches"][0]["player_p"][2],self.base["matches"][0]["p"][2])
        self.assertAlmostEqual(sum(scenario["matches"][0]["player_p"]),1.0,places=7)
        self.assertEqual(self.base["matches"][0]["p"],scenario["matches"][0]["market_p"])
        for s in scenario["systems"]:
            from math import prod
            self.assertEqual(s["cost"],prod(len(c) for c in s["player_choices"]))
            self.assertEqual(s["cost"],prod(len(c) for c in s["original_choices"]))

    def test_unverified_future_or_no_stats_never_adjusts(self):
        future={**self.record,"checked_at_utc":(NOW+timedelta(hours=1)).isoformat()}
        self.assertFalse(verify_report(future,NOW))
        a=availability_build(self.base,[future],self.now)
        s=build(self.base,a,self.solo,created=self.now)
        self.assertEqual(s["used_player_count"],0)
        self.assertEqual(s["matches"][0]["player_p"],self.base["matches"][0]["p"])
        unknown={**self.record,"stats":None}
        a=availability_build(self.base,[unknown],self.now)
        s=build(self.base,a,self.solo,created=self.now)
        self.assertEqual(s["used_player_count"],0)

    def test_tampering_is_rejected(self):
        a=availability_build(self.base,[self.record],self.now)
        s=build(self.base,a,self.solo,created=self.now)
        s["matches"][0]["player_p"]=[0.1,0.2,0.7]
        self.assertFalse(validate(s,self.base,a,self.solo))

    def test_fixture_matching_is_exact_pair_and_kickoff(self):
        kickoff=(NOW+timedelta(days=1)).isoformat()
        fixture={"fixture":{"id":987,"date":kickoff},
                 "teams":{"home":{"id":22,"name":"Home 1"},
                          "away":{"id":23,"name":"Away 1"}},
                 "league":{"id":39,"season":2026}}
        match={"home":"Home 1","away":"Away 1","match_start":kickoff}
        self.assertEqual(resolve_fixture(match,[fixture])["fixture"]["id"],987)
        self.assertIsNone(resolve_fixture({**match,"away":"Away 2"},[fixture]))
        self.assertIsNone(resolve_fixture(match,[fixture,fixture]))
        self.assertEqual(injury_status({"player":{"reason":"Suspension"}}),"suspended")


if __name__=="__main__":
    unittest.main()
