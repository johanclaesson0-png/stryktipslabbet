import unittest
from scripts.v25_september_bulk import catalog_index,BASE,normalize_team
class BulkTest(unittest.TestCase):
    def test_explicit_catalog_links(self):
        path="/football/matches/queens-park-rangers-vs-lincoln-city-2026-11-07/"
        data={"catalog":{"groups":[{"items":[{"name":"Queens Park Rangers vs Lincoln City","url":path},{"name":"Queens Park Rangers vs Lincoln City","url":"https://evil.example"+path},{"name":"QPR vs Lincoln City","url":path.replace("2026-11-07","2026-11-08")}]}]}}
        index=catalog_index(data,{"2026-11-07"})
        self.assertEqual(list(index[(normalize_team("Queens Park Rangers"),normalize_team("Lincoln"))]),[BASE+path])
        self.assertEqual(len(index),1)
if __name__=="__main__": unittest.main()
