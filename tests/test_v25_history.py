import unittest
from datetime import datetime, timezone
from scripts.v25_history import blend, losses, valid_pick, strict_scope

class TestV25(unittest.TestCase):
    def test_blend(self):
        p=[.4,.3,.3]
        self.assertEqual(blend(p,None,.2),p)
        self.assertAlmostEqual(sum(blend(p,[1,0,0],.2)),1)
        self.assertAlmostEqual(blend(p,[1,0,0],.2)[0],.52)
        self.assertEqual(losses([1,0,0],0),(0,0))
    def test_cutoff(self):
        close=datetime(2026,11,14,15,tzinfo=timezone.utc)
        p={"source_at":"2026-11-13T12:00:00Z","observed_at":"2026-11-15T12:00:00Z","source":"https://example.com","sign":"1","type":"result","evidence":"article_timestamp"}
        self.assertTrue(valid_pick(p,close,"retrospective"))
        self.assertFalse(valid_pick(dict(p,source_at=None),close,"retrospective"))
        self.assertFalse(valid_pick(dict(p,source_at="2026-11-13T12:00:00"),close,"retrospective"))
        self.assertFalse(valid_pick(p,close,"prospective"))
        self.assertFalse(valid_pick(dict(p,source_at="2026-11-14T15:00:00Z"),close,"retrospective"))
        self.assertFalse(valid_pick(dict(p,sign="1X"),close,"retrospective"))
        self.assertFalse(valid_pick(dict(p,evidence="postclose_page"),close,"retrospective"))

    def test_strict_scope(self):
        close=datetime(2026,11,14,15,tzinfo=timezone.utc)
        p={"id":"expert","number":1,"home":"A","away":"B","source_at":"2026-11-13T12:00:00Z","observed_at":"2026-11-15T12:00:00Z","source":"https://forecastrecord.com/football/matches/a-vs-b/","sign":"1","type":"result","evidence":"archive_recorded"}
        doc={"schema":"v25-imported-v1","mode":"retrospective","reg_close_time":"2026-11-14T15:00:00Z","covered_positions":[1],"picks":[p]}
        ms=[{"home":"A","away":"B"}]
        panel={"expert":{}}
        self.assertEqual(strict_scope([doc],ms,panel,close),{1})
        self.assertEqual(strict_scope([],ms,panel,close),set())
        for bad in (dict(doc,picks=[]),dict(doc,picks=[p,p]),dict(doc,picks=[dict(p,away="C")])):
            with self.assertRaises(ValueError):
                strict_scope([bad],ms,panel,close)

if __name__ == "__main__":
    unittest.main()
