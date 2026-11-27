import unittest
from scripts.v28_shadow import probability, community_rows
from scripts.v25_history import instant

class TestV28(unittest.TestCase):
    def test_invalid_probability(self):
        for x in ([1,1,1],[-.1,.5,.6],[float("nan"),0,1]):
            with self.assertRaises(ValueError): probability(x)
        self.assertEqual(probability([.4,.3,.3]),[.4,.3,.3])
    def test_late_community_rejected(self):
        r={"draw_number":1,"reg_close_time":"2026-11-28T14:59:00Z","matches":[]}
        d={"schema":"v24-community-v1","draw_number":1,"reg_close_time":r["reg_close_time"],"observed_at":r["reg_close_time"],"market":"Full Time Result","matches":[]}
        self.assertEqual(community_rows(d,r,instant("2026-11-29T00:00:00Z")),{})
