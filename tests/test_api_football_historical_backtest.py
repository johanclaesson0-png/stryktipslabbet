"""No-network regressions for aggregated retrospective API-Football sensitivity."""
from datetime import date
import math
import unittest

from scripts.api_football_historical_backtest import (
    adjust, injury_counts, matched_fixture, confidence_interval,
    elbow_snapshots, results_for, APIClient,
)


class BacktestSafetyTests(unittest.TestCase):
    def test_historical_api_signal_has_expected_direction_and_normalization(self):
        p=[.60,.25,.15]
        home_loss=adjust(p,2,0)
        away_loss=adjust(p,0,2)
        self.assertLess(home_loss[0],p[0])
        self.assertGreater(away_loss[0],p[0])
        self.assertAlmostEqual(sum(home_loss),1,places=12)
        self.assertAlmostEqual(sum(away_loss),1,places=12)
        self.assertEqual(adjust(p,1,1),p)
        self.assertAlmostEqual(sum(adjust(p,999,0)),1,places=12)

    def test_injury_records_are_deduped_with_unknown_types_ignored(self):
        row={"fixture":{"id":123},"team":{"id":9},"player":{"id":6,"type":"Missing Fixture"}}
        other={"fixture":{"id":123},"team":{"id":10},
               "player":{"id":8,"type":"Questionable"}}
        irrelevant={"fixture":{"id":123},"team":{"id":9},
                    "player":{"id":5,"type":"Available"}}
        counts=injury_counts([row,row,other,irrelevant], [123,124])
        self.assertEqual(counts[123][9]["out"],1)
        self.assertEqual(counts[123][10]["doubtful"],1)
        self.assertEqual(counts[123][9]["doubtful"],0)
        self.assertEqual(dict(counts[124]),{})

    def test_exact_teams_scores_date_and_unambiguous_fixture_required(self):
        m={"home":"arsenal","away":"chelsea",
           "score_home":2,"score_away":1,"outcome":"1"}
        entry={"id":2,"date":date(2024,11,17),"played":True,
               "sign":"1","gh":2,"ga":1}
        self.assertEqual(matched_fixture("2024-11-16",m,{
            ("arsenal","chelsea"):[entry]}),entry)
        self.assertIsNone(matched_fixture("2024-11-16",m,{
            ("arsenal","chelsea"):[dict(entry,gh=1)]}))
        self.assertIsNone(matched_fixture("2024-11-16",m,{
            ("arsenal","chelsea"):[dict(entry,date=date(2024,11,30))]}))
        self.assertIsNone(matched_fixture("2024-11-16",m,{
            ("arsenal","chelsea"):[entry,entry]}))

    def test_bootstrap_uses_entire_draw_blocks(self):
        rows=[{"draw":i,"value":(-1)**i*.01} for i in range(8)]
        ci=confidence_interval(rows,lambda r:r["value"],rounds=400)
        self.assertEqual(len(ci),2)
        self.assertLess(ci[0],0)
        self.assertGreater(ci[1],0)

    def test_same_cost_100_and_1800_when_player_data_incomplete(self):
        p=[.54,.25,.21]
        d={"draw":5000,"date":"2024-11-16",
           "matches":[{"outcome":"1" if i%3==0 else "X",
                       "played_consistent":True} for i in range(13)]}
        matched={(5000,0):{"id":9,"home_id":20,"away_id":30,
                           "season":2024,"league":"Premier League"}}
        injury={9:{20:{"out":0,"doubtful":0},30:{"out":2,"doubtful":0}}}
        metrics,rounds=results_for([d],{5000:[p[:] for _ in range(13)]},matched,injury)
        self.assertEqual(len(metrics),1)
        self.assertTrue(metrics[0]["changed"])
        for budget in (100,1800):
            self.assertLessEqual(rounds[5000][budget]["cost"],budget)
            self.assertGreater(rounds[5000][budget]["cost"],0)
            self.assertEqual(sum(rounds[5000][budget]["api"].values())>=0,True)

    def test_non_secret_transport_does_not_need_network(self):
        r=APIClient("test",delay=0,max_calls=2,
                    transport=lambda route,params:{"response":[{"x":route}]})
        self.assertEqual(r.get("fixture",{})[0]["x"],"fixture")
        self.assertEqual(r.calls,1)


if __name__=="__main__":
    unittest.main()
