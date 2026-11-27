import unittest
from datetime import datetime,timezone
from scripts.v30_league_history import catalog_fixtures,profiles,team
class LeagueTest(unittest.TestCase):
    def test_catalog(self):
        path="/football/matches/manchester-city-vs-fulham-2026-11-21/"
        item={"name":"Manchester City vs Fulham","url":path,"kickoff":"2026-11-21T12:30:00Z","final_score":"1-1"}
        doc={"schema_version":"2.0","page_type":"league","league_info":{"name":"Premier League","matches":{"recent":[item,item]}}}
        now=datetime(2026,11,27,tzinfo=timezone.utc)
        self.assertEqual(len(catalog_fixtures(doc,"Premier League",now,set())),1)
        self.assertEqual(catalog_fixtures(doc,"Premier League",now,{("2026-11-21",team("Manchester City"),team("Fulham"))}),[])
        doc["league_info"]["matches"]["recent"].append(dict(item,final_score="1-2"))
        self.assertEqual(catalog_fixtures(doc,"Premier League",now,set()),[])
    def test_profiles(self):
        row={"external_id":"/authors/a/","event_id":"e","name":"A","kind":"human","league":"Premier League","sign":"1","actual":"1","source_at":"2026-11-20T00:00:00Z"}
        self.assertEqual(profiles([row,row])[0]["n"],1)
        self.assertEqual(profiles([row,dict(row,sign="2")]),[])
if __name__=="__main__":unittest.main()
