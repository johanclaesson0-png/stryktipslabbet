"""Convert licensed timestamped historical odds snapshots into a research-only index.
No network requests, keys, purchases or production writes. Use provider JSON exports
obtained under a suitable licence. Exact fixture mapping must be reviewed first."""
import argparse, json, math, statistics
from pathlib import Path
from scripts.v25_history import instant, read

def extract(snapshot, spec):
    cutoff=instant(spec["reg_close_time"])
    kickoff=instant(spec["kickoff"])
    seen=instant(snapshot["timestamp"])
    if not seen < min(cutoff,kickoff):
        raise ValueError("Snapshot is not before both cutoff and kickoff")
    if (cutoff-seen).total_seconds()>86400:
        raise ValueError("Snapshot older than 24h before coupon cutoff")
    events=[e for e in snapshot["data"] if e["id"]==spec["event_id"]]
    if len(events)!=1:
        raise ValueError("Missing or ambiguous event")
    e=events[0]
    if (e["home_team"],e["away_team"])!=(spec["provider_home"],spec["provider_away"]) or instant(e["commence_time"])!=kickoff:
        raise ValueError("Provider fixture mismatch")
    books={}
    names=(e["home_team"],"Draw",e["away_team"])
    for b in e["bookmakers"]:
        if b["key"] in books: raise ValueError("Duplicate bookmaker")
        if instant(b["last_update"])>seen: continue
        ms=[m for m in b["markets"] if m["key"]=="h2h"]
        if len(ms)!=1: continue
        m=ms[0]
        if m.get("last_update") and instant(m["last_update"])>seen: continue
        outcomes=m["outcomes"]
        prices={o["name"]:o["price"] for o in outcomes}
        if len(outcomes)!=3 or set(prices)!=set(names): continue
        if any(type(v) not in (int,float) or not math.isfinite(v) or not 1<v<10000 for v in prices.values()): continue
        inv=[1/prices[n] for n in names]
        books[b["key"]]=[x/sum(inv) for x in inv]
    if len(books)<2: raise ValueError("At least two complete 1X2 bookmakers required")
    med=[statistics.median(v[i] for v in books.values()) for i in range(3)]
    return {"draw_number":spec["draw_number"],"number":spec["number"],"home":spec["home"],"away":spec["away"],"p":[x/sum(med) for x in med],"reg_close_time":spec["reg_close_time"],"observed_at":snapshot["timestamp"],"kickoff":spec["kickoff"],"event_id":spec["event_id"],"bookmakers":sorted(books),"source":"https://the-odds-api.com/historical-odds-data/","market":"90-minute 1X2","mode":"licensed_external_research"}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--snapshot",required=True)
    ap.add_argument("--spec",required=True)
    ap.add_argument("--output",required=True)
    a=ap.parse_args()
    snapshot=read(Path(a.snapshot)); spec=read(Path(a.spec))
    rows=[extract(snapshot,s) for s in spec["matches"]]
    Path(a.output).write_text(json.dumps({"schema":"v29-licensed-odds-v1","rows":rows},indent=2)+"\n")
if __name__=="__main__": main()
