import unittest
from datetime import datetime, timezone
from scripts.v24_experts import accepted, counts
class ExpertTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,26,tzinfo=timezone.utc)
        self.base={"draw_number":4981,"reg_close_time":"2026-11-28T14:59:00Z","matches":[{"number":1,"home":"A","away":"B"}]}
        self.panel={"a":{"name":"A","kind":"human","group":"pub"}}
        self.row={"id":"a","number":1,"home":"A","away":"B","type":"result","sign":"2","source":"https://example.org/a","source_at":"2026-11-25T10:00:00Z","observed_at":"2026-11-25T12:00:00Z","evidence":"article_timestamp"}
        self.doc={"schema":"v24-expert-observations-v1","draw_number":4981,"reg_close_time":self.base["reg_close_time"],"mode":"prospective","picks":[self.row]}
    def test_valid(self):self.assertEqual(len(accepted(self.doc,self.base,self.panel,self.now)),1)
    def test_dedup(self):
        self.doc["picks"]*=2
        self.assertEqual(len(accepted(self.doc,self.base,self.panel,self.now)),1)
    def test_conflict(self):
        self.doc["picks"].append({**self.row,"sign":"1"})
        self.assertEqual(accepted(self.doc,self.base,self.panel,self.now),[])
    def test_late(self):
        with self.assertRaises(ValueError):accepted(self.doc,self.base,self.panel,datetime(2026,11,29,tzinfo=timezone.utc))
    def test_missing(self):
        self.row["source_at"]=None
        self.assertEqual(accepted(self.doc,self.base,self.panel,self.now),[])
    def test_grouped(self):
        rows=[{"id":"a","group":"g","sign":"1X"},{"id":"b","group":"g","sign":"2"}]
        self.assertEqual(counts(rows,True)["shares"],[.25,.25,.5])
        self.assertEqual(counts([],True)["shares"],None)
