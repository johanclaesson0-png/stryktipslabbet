import unittest
from datetime import datetime,timezone
from copy import deepcopy
from scripts.v34_team_news import build,SCHEMA
class NewsTest(unittest.TestCase):
    def test_cutoff_and_lineup(self):
        now=datetime(2026,11,28,14,45,tzinfo=timezone.utc)
        close="2026-11-28T14:59:00Z";kick="2026-11-28T15:00:00Z"
        matches=[{"number":i,"home":"A","away":"B","match_start":kick} for i in range(1,14)]
        base={"draw_number":4981,"reg_close_time":close,"observed_at_utc":"2026-11-28T14:30:00Z","source_snapshot_sha256":"x","matches":matches}
        snap={**base,"sha256":"x"}
        entry={"number":1,"home":"A","away":"B","kickoff":kick,"side":"home","team":"A","checked_at":"2026-11-28T14:40:00Z","reported_at":"2026-11-28T14:39:00Z","source_url":"https://example.org/team","publisher":"Club","review_method":"manual_source_review","type":"lineup","status":"confirmed","players":[str(i) for i in range(11)]}
        doc={"schema":SCHEMA,"draw_number":4981,"reg_close_time":close,"entries":[entry]}
        r=build(base,snap,doc,None,now)
        self.assertEqual(r["coverage"]["confirmed_lineup_teams"],1)
        self.assertEqual(r["matches"][0]["sides"]["away"]["coverage"],"unknown")
        for change in ({"checked_at":close},{"players":["same"]*11},{"home":"C"},{"source_url":"http://example.org"}):
            bad=deepcopy(doc);bad["entries"][0].update(change)
            self.assertEqual(build(base,snap,bad,None,now)["coverage"]["confirmed_lineup_teams"],0)
        bad=deepcopy(doc);bad["entries"].append(dict(entry,type="absence",player="0",status="out",reason="injury"))
        self.assertEqual(build(base,snap,bad,None,now)["matches"][0]["sides"]["home"]["absence_conflicts"],["0"])
if __name__=="__main__":unittest.main()
