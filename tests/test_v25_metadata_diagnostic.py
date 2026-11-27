import unittest
from scripts.v25_metadata_diagnostic import compare
class DiagnosticTest(unittest.TestCase):
    def test_no_guess(self):
        m={"home":"Ipswich","away":"Aston Villa"}
        e={"match":{"participants":[{"type":"home","name":"Ipswich Town"},{"type":"away","name":"Aston Villa"}]}}
        a={"date":"2026-10-10","matches":[dict(m) for _ in range(13)]}
        d={"draw":{"drawNumber":4974,"productName":"Stryktipset","productId":"1","regCloseTime":"2026-10-10T13:59:00Z","drawEvents":[dict(e,eventNumber=i) for i in range(1,14)]}}
        self.assertTrue(compare(4974,a,d)["all_positions_match"])
        a["matches"][0]={"home":"Aston Villa","away":"Ipswich"}
        self.assertEqual(compare(4974,a,d)["matching_positions"],12)
if __name__=="__main__":unittest.main()
