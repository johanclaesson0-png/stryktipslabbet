"""V18: tests without external APIs, licensing assumptions or current outcomes."""
from datetime import date,datetime,timezone,timedelta
import unittest

from scripts.api_football_historical_backtest import choose_history_batch
from scripts.weighted_player_backtest import (prior_fixture_ids,importance_from_past_games,
    absence_impact,weighted_sensitivity)
from scripts.market_player_audit import evaluate_verified_pair,match_score,audit


class HistoricalV18Tests(unittest.TestCase):
    def test_nonoverlapping_stratified_batches(self):
        catalog={}
        for season in (2022,2023,2024):
            for league in ("Premier League","Championship"):
                for i in range(12):
                    fid=season*100000+(1 if league=="Premier League" else 2)*100+i
                    catalog[fid]={"id":fid,"season":season,"league":league,
                        "date":date(season,10,1)+timedelta(days=i)}
        x=choose_history_batch(catalog,0,per_group=6)
        y=choose_history_batch(catalog,1,per_group=6)
        self.assertEqual(len(x),36)
        self.assertEqual(len(y),36)
        self.assertFalse(x&y)
        self.assertRaises(ValueError,choose_history_batch,catalog,-1,6)

    def test_player_minutes_strictly_prior(self):
        team=50
        index={("home","away"): [
            {"id":1,"home_id":team,"away_id":30,"date":date(2024,10,5),"played":True},
            {"id":2,"home_id":40,"away_id":team,"date":date(2024,10,12),"played":True},
            {"id":3,"home_id":team,"away_id":60,"date":date(2024,10,19),"played":True},
            {"id":4,"home_id":team,"away_id":70,"date":date(2024,10,26),"played":True},
            {"id":5,"home_id":team,"away_id":80,"date":date(2024,11,2),"played":True},
        ]}
        self.assertEqual(prior_fixture_ids(index,team,date(2024,10,26)),[3,2,1])
        self.assertEqual(prior_fixture_ids(index,team,date(2024,10,20)),[3,2,1])
        self.assertNotIn(4,prior_fixture_ids(index,team,date(2024,10,26)))

    def test_importance_uses_older_starts_and_minutes(self):
        first={i:(80.,1) for i in range(1,12)}
        second={i:(90.,1) for i in range(1,12)}
        first[1]=(90.,1);second[1]=(90.,1)
        first[2]=(20.,0);second[2]=(30.,0)
        rating=importance_from_past_games([first,second])
        self.assertGreater(rating[1],rating[2])
        self.assertLessEqual(rating[1],1.000001)
        self.assertIsNone(importance_from_past_games([first]))
        self.assertIsNone(absence_impact([{"team":{"id":1},
            "player":{"id":999,"type":"Missing Fixture"}}],1,rating))
        self.assertEqual(absence_impact([],1,rating),0.)

    def test_missing_player_cannot_be_mistaken_for_available(self):
        report=[{"team":{"id":1},"player":{"id":4,"type":"Missing Fixture"}}]
        self.assertIsNone(absence_impact(report,1,{}))
        self.assertIsNone(absence_impact(report,1,None))
        self.assertEqual(absence_impact(report,2,{}),0.0)

    def test_weighted_probabilities_direction(self):
        p=[0.50,0.27,0.23]
        a=weighted_sensitivity(p,1.,0.)
        b=weighted_sensitivity(p,0.,1.)
        self.assertLess(a[0],p[0])
        self.assertGreater(b[0],p[0])
        self.assertAlmostEqual(sum(a),1.)
        self.assertAlmostEqual(sum(b),1.)

    def test_real_market_pair_rejects_missing_or_postclose_evidence(self):
        base={"observed_at_utc":"2024-10-12T10:00:00+00:00",
              "reg_close_time":"2024-10-12T15:00:00+00:00"}
        feed={"collected_at_utc":"2024-10-12T15:01:00+00:00"}
        report={"created_at_utc":"2024-10-12T15:02:00+00:00"}
        p,reason=evaluate_verified_pair(base,{},feed,report,{})
        self.assertIsNone(p)
        self.assertIn("spelstopp",reason)
        self.assertEqual(match_score([.5,.3,.2],"1")[0],.38)

    def test_no_old_odds_or_settlements_cannot_produce_fake_improvement(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as tmp:
            result=audit(Path(tmp))
            self.assertEqual(result["evaluated_matches"],0)
            self.assertIsNone(result["brier_market"])
            self.assertIsNone(result["brier_player"])
            self.assertEqual(result["with_official_settlement"],0)


if __name__=="__main__":
    unittest.main()
