import unittest
from scripts.v25_forecastrecord_api import discover, Client

class TestAPI(unittest.TestCase):
    def test_discover(self):
        base={"draw_number":4981,"reg_close_time":"2026-11-28T14:59:00Z","matches":[{"number":1,"home":"Ipswich","away":"Aston Villa"},{"number":2,"home":"Sheffield W","away":"Reading"}]}
        item={"url":"/football/matches/ipswich-town-vs-aston-villa-2026-11-28/","name":"Ipswich Town vs Aston Villa"}
        cat={"schema_version":"2.0","canonical":"/football/matches/","page_type":"catalog","catalog":{"groups":[{"items":[item,item,{"url":"/football/matches/ipswich-town-vs-aston-villa-2026-11-21/","name":item["name"]}]}]}}
        found,missing=discover(cat,base)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["number"],1)
        self.assertEqual(missing[0]["number"],2)
        cat["catalog"]["groups"][0]["items"].append(dict(item,url="/football/matches/other-2026-11-28/"))
        self.assertEqual(discover(cat,base)[0],[])
    def test_budget_and_url(self):
        c=Client(0)
        with self.assertRaises(ValueError): c.get("https://forecastrecord.com/football/matches/")
        with self.assertRaises(ValueError): c.get("https://example.org/")

if __name__=="__main__":
    unittest.main()
