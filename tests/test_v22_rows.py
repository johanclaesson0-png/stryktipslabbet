import itertools
import unittest
from scripts.v22_rows import top_rows, exact_coverage, validate_rows, row_index
from math import prod

class V22Tests(unittest.TestCase):
    def setUp(self):
        self.ps=[[.6,.25,.15],[.4,.35,.25],[.2,.3,.5],[.5,.25,.25]]
        self.all_rows=["".join(r) for r in itertools.product("1X2",repeat=4)]
    def mass(self,r):
        return prod(p["1X2".index(c)] for p,c in zip(self.ps,r))
    def test_top_k_matches_exhaustive(self):
        expect=sorted(self.all_rows,key=lambda r:(-self.mass(r),r))[:17]
        actual=top_rows(self.ps,17)
        self.assertAlmostEqual(sum(map(self.mass,expect)),sum(map(self.mass,actual)),12)
        self.assertEqual(len(set(actual)),17)
    def test_coverage_matches_exhaustive(self):
        rows=top_rows(self.ps,9)
        got=exact_coverage(rows,self.ps)
        for k in range(1,5):
            expect=sum(self.mass(r) for r in self.all_rows if
                max(sum(a==b for a,b in zip(r,s)) for s in rows)>=k)
            self.assertAlmostEqual(got[str(k)],expect,9)
    def test_duplicates_and_bad_signs_rejected(self):
        for rows in (["1"*13]*2,["0"*13],["1"*12],[]):
            with self.assertRaises(ValueError):validate_rows(rows)
    def test_index_order(self):
        self.assertEqual([row_index(r) for r in self.all_rows],list(range(81)))
    def test_budget(self):
        with self.assertRaises(ValueError):top_rows(self.ps,1801)
