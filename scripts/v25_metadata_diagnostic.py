"""Read-only diagnosis of historical Svenska Spel fixture mismatches.
No odds are retrieved for use as pre-close observations. No fixture remapping
or result corrections are made automatically."""
import argparse,json,time
from pathlib import Path
from datetime import datetime,timezone
from scripts.collect import fetch
from scripts.v25_forecastrecord_api import team
from scripts.v25_history import instant,read

def compare(draw, archive, raw):
    d=raw["draw"]
    if str(d["drawNumber"])!=str(draw) or str(d["productId"])!="1" or d["productName"]!="Stryktipset":
        raise ValueError("Wrong draw/product")
    ev=sorted(d["drawEvents"],key=lambda e:e["eventNumber"])
    if [e["eventNumber"] for e in ev]!=list(range(1,14)) or len(archive["matches"])!=13:
        raise ValueError("Wrong fixture count")
    close=instant(d["regCloseTime"])
    rows=[]
    for i,(e,m) in enumerate(zip(ev,archive["matches"]),1):
        participants=e["match"]["participants"]
        sides={s:[p["name"] for p in participants if p["type"]==s] for s in ("home","away")}
        if any(len(v)!=1 for v in sides.values()):raise ValueError("Unclear official identity")
        actual=[sides[s][0] for s in ("home","away")]
        stored=[m[s] for s in ("home","away")]
        same=tuple(map(team,actual))==tuple(map(team,stored))
        rows.append({"number":i,"official":actual,"archive":stored,"normalized_match":same,"kickoff":e["match"].get("matchStart")})
    return {"draw":draw,"date":archive["date"],"reg_close_time":close.isoformat(),"matches":rows,"all_positions_match":all(r["normalized_match"] for r in rows),"matching_positions":sum(r["normalized_match"] for r in rows)}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",default="data")
    ap.add_argument("--output",default="official-metadata-review.json")
    a=ap.parse_args()
    data=Path(a.data); archive={x["draw"]:x for x in read(data/"history/summary.json")["archive"]}
    result={"schema":"v25-official-metadata-diagnostic-v1","observed_at":datetime.now(timezone.utc).isoformat(),"rounds":[],"errors":[]}
    for draw in range(4972,4979):
        try:
            raw,_=fetch("/draws/"+str(draw))
            r=compare(draw,archive[draw],raw)
            result["rounds"].append(r)
            print("OFFICIAL",draw,r["reg_close_time"],r["matching_positions"],"/13",flush=True)
            for m in r["matches"]:
                if not m["normalized_match"]:print("MISMATCH",draw,m["number"],json.dumps({"official":m["official"],"archive":m["archive"]},ensure_ascii=False),flush=True)
        except Exception as e:
            result["errors"].append({"draw":draw,"error":str(e)})
            print("ERROR",draw,str(e),flush=True)
        time.sleep(1)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
