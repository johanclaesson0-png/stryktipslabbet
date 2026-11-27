import unittest
from datetime import datetime, timezone
from copy import deepcopy
from scripts.v25_forecastrecord import extract

class ImportTests(unittest.TestCase):
    def test_filters(self):
        source="https://forecastrecord.com/football/matches/a-vs-b-2026-11-14/"
        spec={"draw":1,"number":1,"url":source,"date":"2026-11-14","display":"A — B"}
        base={"draw_number":1,"reg_close_time":"2026-11-14T14:59:00Z","matches":[{"number":1,"home":"A","away":"B"}]}
        official={"outcome":"1"}
        ev={"id":"e","display_name":"A — B","starts_at":"2026-11-14T19:45:00Z","status":"finished","scoreline":"2-0","competition_name":"Test league"}
        row={"observation_id":"r","url":"/authors/test/picks/1/","origin":"recorded_before_kickoff","withdrawn":False,"dates":{"detected_at":"2026-11-14T12:00:00Z"},"event":{"event_id":"e"},"author_claim":{"market_key":"1x2","period":"match","choice_key":"1"},"authorship":{"publisher":"test.example"}}
        doc={"schema_version":"2.0","page_type":"event","canonical":source.removeprefix("https://forecastrecord.com"),"event":ev,"evidence_items":[row],"match_summary":{"who_predicted_what":[{"record_id":"r","author":"Test","author_url":"/authors/test/"}]}}
        now=datetime(2026,11,27,tzinfo=timezone.utc)
        self.assertEqual(len(extract(doc,spec,base,official,now)[0]),1)
        for key,value in [("withdrawn",True),("origin","found_after_kickoff"),("link",{"kind":"same_material"}),("dates",{"detected_at":"2026-11-14T15:00:00Z"}),("author_claim",{"market_key":"correct_score_market","period":"match","choice_key":"1"})]:
            bad=deepcopy(doc);bad["evidence_items"][0][key]=value
            self.assertEqual(extract(bad,spec,base,official,now)[0],[])
        with self.assertRaises(ValueError):extract(doc,spec,base,{"outcome":"2"},now)
        pending=deepcopy(doc)
        pending["event"]["status"]="scheduled"
        pending["event"]["scoreline"]=None
        e=pending["evidence_items"][0]
        e["authorship"]=None
        e["source_info"]={"url":"https://www.test.example/article","material_removed":False}
        e["url"]=None
        identity=pending["match_summary"]["who_predicted_what"][0]
        identity.update({"url":None,"recorded_at":e["dates"]["detected_at"],"before_kickoff":True})
        preclose=datetime(2026,11,14,13,tzinfo=timezone.utc)
        picks,_=extract(pending,spec,base,None,preclose)
        self.assertEqual(len(picks),1)
        self.assertEqual(picks[0]["publisher"],"test.example")
        with self.assertRaises(ValueError):extract(pending,spec,base,None,now)
        identity["author_url"]="/sources/test/products/editorial/"
        e["url"]="/sources/test/products/editorial/picks/1/"
        self.assertEqual(extract(pending,spec,base,None,preclose)[0][0]["kind"],"site")

if __name__=="__main__":
    unittest.main()
