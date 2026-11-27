import unittest
from copy import deepcopy
from scripts.v32_opening_odds import opening
class OpeningTest(unittest.TestCase):
    def test_first_not_closing(self):
        row={"draw_number":1,"number":1,"home":"A","away":"B","source":"https://forecastrecord.com/football/matches/a-vs-b-2026-11-07/","reg_close_time":"2026-11-07T14:59:00Z","kickoff":"2026-11-07T17:30:00Z","actual":"1"}
        m={"score_home":2,"score_away":1}
        line={"market_group":"1x2","market_text":"1X2, match result","line_kind":"median_line","margin_included":False,"closing_line":True,"snapshot_at":row["kickoff"],"first_at":"2026-11-06T12:00:00Z","first_probabilities":{"1":40,"X":30,"2":30}}
        doc={"schema_version":"2.0","page_type":"event","canonical":row["source"].removeprefix("https://forecastrecord.com"),"event":{"status":"finished","starts_at":row["kickoff"],"scoreline":"2-1"},"match_summary":{"market_line":{"line_markets":[line]}}}
        self.assertEqual(opening(doc,row,m)["p"],[.4,.3,.3])
        for patch in ({"first_at":row["reg_close_time"]},{"first_probabilities":{"1":40,"2":60}},{"first_probabilities":None},{"margin_included":True}):
            bad=deepcopy(doc);bad["match_summary"]["market_line"]["line_markets"][0].update(patch)
            with self.assertRaises(ValueError):opening(bad,row,m)
if __name__=="__main__":unittest.main()
