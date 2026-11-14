"""V17 regression: fixture identity, status, source timing, no silent guessing."""
import copy
import unittest
from datetime import timedelta

from scripts.analyze import create_analysis
from scripts.solo import derive
from scripts.api_football_adapter import (
    APIClient, candidate_fixtures, english_leagues, get_players, matching_fixture, season_for
)
from scripts.player_impact import (
    SCHEMA, build, ranked_players, sensitivity, side_impact, source_ok
)
from tests.test_solo import NOW, sample


def sample_players():
    return [
        {"id": i, "name": "Player " + str(i), "position": "Forward" if i == 1 else "Midfielder",
         "appearances": 18, "starts": 15-i, "minutes": 1500-30*i,
         "goals": 8 if i == 1 else 1, "assists": 5 if i == 1 else 0}
        for i in range(1, 9)
    ]


class EnglishPlayerImpactTests(unittest.TestCase):
    def setUp(self):
        self.base = create_analysis(sample())
        self.personal = derive(self.base,NOW)
        self.report_time = NOW + timedelta(minutes=2)
        self.feed = {
            "schema": SCHEMA,
            "provider": "API-Football",
            "draw_number": self.base["draw_number"],
            "source_snapshot_sha256": self.base.get("source_snapshot_sha256"),
            "source_observed_at_utc": self.base["observed_at_utc"],
            "reg_close_time": self.base["reg_close_time"],
            "collected_at_utc": (NOW + timedelta(minutes=1)).isoformat(),
            "matches": []
        }
        for x in self.base["matches"]:
            self.feed["matches"].append({
                "number": x["number"], "home": x["home"], "away": x["away"],
                "league": None, "fixture_id": None, "home_feed": {},
                "away_feed": {}
            })
        row = self.feed["matches"][0]
        row["league"] = "Championship"
        row["fixture_id"] = 1001
        for side in ("home", "away"):
            row[side+"_feed"] = {
                "coverage": "verified_provider_feed", "players_covered": True,
                "injuries_covered": True, "players": sample_players(),
                "absences": []
            }


    def test_equal_cost_100_and_1800_scenario_systems(self):
        self.feed["matches"][0]["away_feed"]["absences"] = [
            {"player_id": 1, "status": "out"}
        ]
        report = build(self.base, self.feed, self.report_time, personal=self.personal)
        self.assertEqual(len(report["systems"]), 2)
        self.assertEqual([s["budget_limit"] for s in report["systems"]],[100,1800])
        for scenario in report["systems"]:
            from math import prod
            self.assertEqual(scenario["cost"],prod(len(c) for c in scenario["source_market_choices"]))
            self.assertEqual(scenario["cost"],prod(len(c) for c in scenario["player_scenario_choices"]))
            self.assertEqual(scenario["covered_by_player_data"],1)
            self.assertEqual(scenario["unknown_matches_using_market_only"],12)
            self.assertGreater(scenario["player_p13_under_scenario"],0)
        self.assertEqual(report["matches"][0]["market_p"],self.base["matches"][0]["p"])

    def test_no_scenario_system_when_all_matches_unknown(self):
        report = build(self.base, self.feed, self.report_time, personal=self.personal)
        self.assertEqual(report["coverage"]["scenario_matches"],1)
        self.assertEqual(len(report["systems"]),2)
        for item in self.feed["matches"]:
            item["league"] = None
            item["fixture_id"] = None
        missing = build(self.base, self.feed, self.report_time, personal=self.personal)
        self.assertEqual(missing["coverage"]["scenario_matches"],0)
        self.assertEqual(missing["systems"],[])

    def test_many_english_players_are_ranked_not_two_named_examples(self):
        ranked = ranked_players(sample_players())
        self.assertEqual(len(ranked), 8)
        self.assertEqual(ranked[0]["name"], "Player 1")
        self.assertGreater(ranked[0]["importance"], ranked[-1]["importance"])

    def test_away_key_player_absence_improves_home_chance_in_experiment(self):
        self.feed["matches"][0]["away_feed"]["absences"] = [
            {"player_id": 1, "status": "out", "reason": "Injury"}
        ]
        result = build(self.base, self.feed, self.report_time)
        row = result["matches"][0]
        self.assertGreater(row["scenario_p"][0], row["market_p"][0])
        self.assertLess(row["scenario_p"][2], row["market_p"][2])
        self.assertAlmostEqual(sum(row["scenario_p"]), 1, places=6)
        self.assertEqual(result["coverage"]["scenario_matches"], 1)
        self.assertEqual(result["coverage"]["unknown_matches"], 12)
        self.assertIn("hypotetisk", result["model_effect"].lower())

    def test_home_absence_reduces_home_chance(self):
        self.feed["matches"][0]["home_feed"]["absences"] = [
            {"player_id": 1, "status": "suspended"}
        ]
        row = build(self.base, self.feed, self.report_time)["matches"][0]
        self.assertLess(row["scenario_p"][0], row["market_p"][0])

    def test_multiple_absences_and_questionable_have_different_weight(self):
        x = self.feed["matches"][0]["home_feed"]
        x["absences"] = [{"player_id": 1, "status": "out"},
                         {"player_id": 2, "status": "doubtful"}]
        strong, players, reason = side_impact(x)
        self.assertIsNone(reason)
        self.assertEqual(len(players), 2)
        only = copy.deepcopy(x)
        only["absences"] = [{"player_id": 1, "status": "out"}]
        weak, _, _ = side_impact(only)
        self.assertGreater(strong, weak)

    def test_unknown_or_missing_stats_never_means_available(self):
        side = self.feed["matches"][0]["home_feed"]
        side["players_covered"] = False
        penalty, _, reason = side_impact(side)
        self.assertIsNone(penalty)
        self.assertTrue(reason)
        result = build(self.base, self.feed, self.report_time)
        self.assertIsNone(result["matches"][0]["scenario_p"])

    def test_missing_important_player_stats_blocks_guesses(self):
        side = self.feed["matches"][0]["home_feed"]
        side["absences"] = [{"player_id": 99999, "status": "out"}]
        penalty, _, reason = side_impact(side)
        self.assertIsNone(penalty)
        self.assertIn("statistik", reason)

    def test_no_late_or_stale_news(self):
        late = copy.deepcopy(self.feed)
        late["collected_at_utc"] = (NOW+timedelta(hours=3)).isoformat()
        self.assertFalse(source_ok(self.base, late, self.report_time))
        old = copy.deepcopy(self.feed)
        old["collected_at_utc"] = (NOW-timedelta(days=4)).isoformat()
        self.assertFalse(source_ok(self.base, old, self.report_time))

    def test_exact_match_identity_required(self):
        wrong = copy.deepcopy(self.feed)
        wrong["matches"][0]["home"] = "Another club"
        self.assertFalse(source_ok(self.base, wrong, self.report_time))

    def test_market_probabilities_unchanged(self):
        before = copy.deepcopy(self.base)
        self.feed["matches"][0]["away_feed"]["absences"] = [
            {"player_id": 1, "status": "out"}
        ]
        build(self.base, self.feed, self.report_time)
        self.assertEqual(self.base, before)

    def test_sensitivity_is_normalized_and_bounded(self):
        p = sensitivity([.54,.26,.20], .1, .0)
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertLess(p[0], .54)


class APIFootballMappingTests(unittest.TestCase):
    def test_english_league_identity_and_coverage(self):
        def transport(route, params):
            self.assertEqual(route, "leagues")
            return {"response": [
                {"league": {"id": 39, "name": "Premier League", "type": "League"},
                 "country": {"name": "England"},
                 "seasons": [{"year": 2026, "coverage": {"players": True, "injuries": True}}]},
                {"league": {"id": 999, "name": "Premier League", "type": "League"},
                 "country": {"name": "Another country"},
                 "seasons": [{"year": 2026, "coverage": {"players": True, "injuries": True}}]}
            ]}
        client = APIClient("test", transport=transport)
        leagues = english_leagues(client, 2026)
        self.assertEqual(leagues["Premier League"]["id"], 39)

    def test_ambiguous_fixtures_are_not_guessed(self):
        f = {"home": {"name": "Manchester United"}, "away": {"name": "Arsenal"}}
        m = {"home": "Man Utd", "away": "Arsenal"}
        self.assertIsNotNone(matching_fixture(m, [f]))
        self.assertIsNone(matching_fixture(m, [f, f]))

    def test_season_is_start_year(self):
        self.assertEqual(season_for(NOW), 2026)
        self.assertEqual(season_for(NOW.replace(month=2)), 2025)


if __name__ == "__main__":
    unittest.main()
