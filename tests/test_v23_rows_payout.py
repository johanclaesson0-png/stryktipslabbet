import unittest
from scripts.v23_rows_payout import row_codes, winning_counts
from scripts.v22_rows import m_rows
from scripts.analyze import correct_rows
class V23Tests(unittest.TestCase):
    def test_m_counts_match_original(self):
        choices=["1X","12","1X2"]+["1"]*10
        rows=m_rows(choices)
        for result in ("111"+"1"*10,"X22"+"1"*10,"221"+"X"*10):
            self.assertEqual(winning_counts(row_codes(rows),["1X2".index(c) for c in result]),correct_rows(choices,result))
    def test_nonrectangular(self):
        rows=["1"*13,"X"*13,"2"*13,"1X2"*4+"1"]
        for outcome in rows:
            got=winning_counts(row_codes(rows),["1X2".index(c) for c in outcome])
            expected=[0]*14
            for r in rows:expected[sum(x==y for x,y in zip(r,outcome))]+=1
            self.assertEqual(got,expected)
    def test_no_duplicates(self):
        with self.assertRaises(ValueError):row_codes(["1"*13]*2)
