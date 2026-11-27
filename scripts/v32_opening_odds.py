"""Forecast Record opening-line research, separate from near-cutoff market.
Read only, preserve time and source. Never use a closing line as a preclose line."""
import argparse,json,time,math
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError
from scripts.v25_forecastrecord_api import Client,team
from scripts.v25_forecastrecord import BASE,URL
from scripts.v25_history import read,instant,blend,losses,SIGNS
from scripts.v31_canonical_history import alias

def walk(x):
    if isinstance(x,dict):
        yield x
        for v in x.values():yield from walk(v)
    elif isinstance(x,list):
        for v in x:yield from walk(v)

def opening(doc,row,match):
    if doc.get("schema_version")!="2.0" or doc.get("page_type")!="event" or BASE+doc.get("canonical","")!=row["source"]:
        raise ValueError("Event canonical mismatch")
    ev=doc["event"]
    if ev.get("status")!="finished" or ev.get("postponement") or instant(ev["starts_at"])!=instant(row["kickoff"]):
        raise ValueError("Event status or kickoff mismatch")
    if ev["scoreline"]!=f'{match["score_home"]}-{match["score_away"]}':
        raise ValueError("Official archive score mismatch")
    close=min(instant(row["reg_close_time"]),instant(row["kickoff"]))
    candidates=[]
    for x in walk(doc):
        line=x.get("market_line")
        if not isinstance(line,dict):continue
        for m in line.get("line_markets",[]):
            if m.get("market_group")!="1x2" or m.get("market_text")!="1X2, match result" or m.get("line_kind")!="median_line" or m.get("margin_included") is not False:continue
            # Use only the explicitly recorded first vector; closing snapshot is forbidden.
            if not m.get("first_at") or not isinstance(m.get("first_probabilities"),dict):continue
            t=instant(m["first_at"]); q=m["first_probabilities"]
            if set(q)!=set(SIGNS) or not all(type(v) in (int,float) and math.isfinite(v) and 0<v<100 for v in q.values()) or not 99<=sum(q.values())<=101:continue
            if not t<close or t>instant(m["snapshot_at"]):continue
            candidates.append((t,tuple(q[k]/sum(q.values()) for k in SIGNS)))
    unique=set(candidates)
    if len(unique)!=1:raise ValueError("No unique complete early 1X2 line before cutoff")
    t,p=next(iter(unique))
    return {"draw_number":row["draw_number"],"number":row["number"],"home":row["home"],"away":row["away"],"source":row["source"],"snapshot_at":t.isoformat(),"reg_close_time":row["reg_close_time"],"kickoff":row["kickoff"],"p":list(p),"hours_before_cutoff":round((close-t).total_seconds()/3600,2),"actual":row["actual"],"reference":"first_recorded_market_line","observed_at":datetime.now(timezone.utc).isoformat(),"note":"Rounded percentages from provider; not an exact Svenska Spel snapshot at coupon deadline."}

def paired(odds,claims):
    report=[]
    for r in odds:
        groups=defaultdict(list)
        for p in claims[(r["draw_number"],r["number"])]:
            if p["kind"]!="human":continue
            publisher=p["publisher"].strip().casefold()
            if publisher:
                # Conservatively collapse localized SportyTrader and Telegram publisher variants.
                if "sportytrader" in publisher:publisher="sportytrader"
                if publisher.startswith("t.me"):publisher="telegram"
                groups[publisher].append(SIGNS.index(p["sign"]))
        if len(groups)<2:continue
        shares=[sum(v.count(i)/len(v) for v in groups.values())/len(groups) for i in range(3)]
        scores={str(w):losses(blend(r["p"],shares,w),SIGNS.index(r["actual"])) for w in (0,.05,.10,.15,.20)}
        report.append({"draw":r["draw_number"],"number":r["number"],"groups":len(groups),"scores":scores})
    return {"matches":len(report),"draws":len({r["draw"] for r in report}),"fixed_weight_experiments":[{"weight":w,"brier":sum(r["scores"][str(w)][0] for r in report)/len(report),"log_loss":sum(r["scores"][str(w)][1] for r in report)/len(report)} for w in (0,.05,.10,.15,.20)] if report else [],"warning":"Exploratory first-line comparison, not a chronological independent holdout or near-cutoff odds comparison."}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",default="data")
    ap.add_argument("--output",default="v32-opening-review.json")
    ap.add_argument("--limit",type=int,default=63)
    a=ap.parse_args()
    if not 1<=a.limit<=63:ap.error("Limit 1–63")
    data=Path(a.data)
    rows=read(data/"v31/historical_coupon.json")["rows"]
    archive={r["draw"]:r for r in read(data/"history/summary.json")["archive"]}
    claims=defaultdict(list)
    for r in rows:
        if r["draw_number"]<=4978 and r["cutoff_status"]=="verified_coupon_reconciled":
            claims[(r["draw_number"],r["number"])].append(r)
    client=Client(a.limit)
    report={"schema":"v32-opening-review-v1","eligible_positions":len(claims),"rows":[],"errors":[]}
    for key,rs in sorted(claims.items(),reverse=True)[:a.limit]:
        try:
            if len({(r["source"],r["kickoff"],r["reg_close_time"],r["actual"]) for r in rs})!=1:raise ValueError("Inconsistent canonical rows")
            r=rs[0];m=archive[key[0]]["matches"][key[1]-1]
            if not m["played_consistent"] or r["actual"]!=m["outcome"]:raise ValueError("Inconsistent result")
            o=opening(client.get(r["source"]),r,m)
            report["rows"].append(o)
            print("OPENING",*key,o["p"],o["snapshot_at"],flush=True)
        except HTTPError as e:
            report["errors"].append({"draw":key[0],"number":key[1],"error":"HTTP "+str(e.code)})
            if e.code in (401,403,429):break
        except (OSError,KeyError,TypeError,ValueError) as e:
            report["errors"].append({"draw":key[0],"number":key[1],"error":str(e)})
            print("MISSING",*key,str(e),flush=True)
        Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    report["requests"]=client.calls
    report["comparison"]=paired(report["rows"],claims)
    Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("OPENING TOTAL",len(report["rows"]),"of",len(claims),"requests",client.calls,"errors",len(report["errors"]),flush=True)
    print("OPENING COMPARISON",json.dumps(report["comparison"]),flush=True)
    if not report["rows"]:raise SystemExit(1)
if __name__=="__main__":main()
