import unittest
from datetime import datetime,timezone
from scripts.v33_submission import compare
class CompareTest(unittest.TestCase):
    def test_empty(self):
        base={"draw_number":1,"observed_at_utc":"2026-11-27T20:00:00Z","reg_close_time":"2026-11-28T14:59:00Z","matches":[{"number":n,"home":"A","away":"B","p":[.5,.25,.25],"streck":[50,25,25]} for n in range(1,14)]}
        now=datetime(2026,11,27,22,tzinfo=timezone.utc)
        r=compare(base,{"rows":[]},now)
        self.assertEqual(r["market"],r["expert"])
        self.assertEqual(r["expert_eligible_matches"],0)
        self.assertEqual(r["production_expert_weight"],0)
        self.assertLessEqual(r["market"]["cost"],1800)
if __name__=="__main__":unittest.main()
