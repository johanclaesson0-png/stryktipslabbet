import unittest
from datetime import datetime,timezone,timedelta
from copy import deepcopy
from scripts.v29_research import evaluate, shares, reliability, update
from scripts.v29_odds import extract

class TestResearch(unittest.TestCase):
    def row(self,draw):
        close=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=7*draw)
        return {"draw":draw,"number":1,"cutoff":close,"settled":close+timedelta(hours=6),"p":[.5,.3,.2],"form":[.5,.3,.2],"actual":0,"experts":[{"id":"a","group":"one","league":"L","sign":"1"},{"id":"b","group":"two","league":"L","sign":"2"}]}
    def test_chronology(self):
        a,b=self.row(1),self.row(2)
        report=evaluate([b,a])
        self.assertEqual([r["train_matches"] for r in report["per_match"]],[0,1])
        self.assertEqual(report["holdout_matches"],0)
        self.assertEqual(report["production_expert_weight"],0)
        a["settled"]=b["cutoff"]+timedelta(hours=1)
        self.assertEqual(evaluate([a,b])["per_match"][1]["train_matches"],0)
    def test_skill(self):
        a=self.row(1); stats={}; self.assertEqual(reliability(stats,"a","L","1",.5),1)
        for _ in range(100): update(stats,a)
        self.assertGreater(reliability(stats,"a","L","1",.5),reliability(stats,"b","L","2",.2))
        self.assertAlmostEqual(sum(shares(a,stats)),1)
    def test_odds(self):
        spec={"draw_number":1,"number":1,"home":"A","away":"B","provider_home":"A","provider_away":"B","event_id":"e","reg_close_time":"2026-01-01T14:59:00Z","kickoff":"2026-01-01T15:00:00Z"}
        book={"key":"one","last_update":"2026-01-01T14:55:00Z","markets":[{"key":"h2h","outcomes":[{"name":"A","price":2},{"name":"Draw","price":3},{"name":"B","price":4}]}]}
        snapshot={"timestamp":"2026-01-01T14:56:00Z","data":[{"id":"e","home_team":"A","away_team":"B","commence_time":spec["kickoff"],"bookmakers":[book,dict(book,key="two")]}]}
        self.assertAlmostEqual(sum(extract(snapshot,spec)["p"]),1)
        for bad in [dict(snapshot,timestamp=spec["reg_close_time"]),dict(spec,event_id="wrong")]:
            with self.assertRaises(ValueError):
                extract(bad,spec) if "timestamp" in bad else extract(snapshot,bad)
if __name__=="__main__": unittest.main()
