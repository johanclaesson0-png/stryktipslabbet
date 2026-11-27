"""Bounded retrospective review of coupon fixtures since 2026-09-25.

Fetch public JSON catalogs and event exports, not third-party quotations.
Separate records whose coupon cutoff is verified from pre-kickoff-only records.
Never write live probabilities or auto-publish new sources.
"""
import argparse
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from scripts.collect import fetch as official_fetch
from scripts.v25_forecastrecord import BASE, URL, extract
from scripts.v25_forecastrecord_api import team as normalize_team, ALIASES
from scripts.v25_history import instant, read

# Explicit aliases only, no fuzzy names or result-based fixture guessing.
ALIASES.update({
    "norwich":"Norwich City","burton":"Burton Albion","cambridge united":"Cambridge United",
    "peterborough":"Peterborough United","grimsby town":"Grimsby Town","accrington":"Accrington Stanley",
    "crewe":"Crewe Alexandra","rotherham":"Rotherham United","shrewsbury":"Shrewsbury Town",
    "colchester":"Colchester United","tranmere":"Tranmere Rovers","newport":"Newport County",
    "salford":"Salford City","exeter":"Exeter City","fleetwood":"Fleetwood Town",
    "cheltenham":"Cheltenham Town","rochdale":"Rochdale","czech republic":"Czechia",
})
DAY=re.compile(r"https://forecastrecord\.com/football/matches/archive/\d{4}/\d{2}/\d{2}/")
ROOT=BASE+"/football/matches/"
DAY_SLUG=re.compile(r"-(\d{4}-\d{2}-\d{2})/$")

class StopBudget(Exception): pass

class Client:
    def __init__(self, maximum):
        self.maximum=maximum; self.calls=0; self.last=None; self.cache={}
    def get(self,url):
        if url in self.cache: return self.cache[url]
        if url!=ROOT and not (DAY.fullmatch(url) or URL.fullmatch(url)):
            raise ValueError("Unexpected export path")
        if self.calls>=self.maximum: raise StopBudget("Request budget exhausted")
        if self.last is not None: time.sleep(max(0,7-(time.monotonic()-self.last)))
        self.calls+=1; self.last=time.monotonic()
        with urlopen(Request(url+"index.json",headers={"User-Agent":"Stryktipslabbet research/1.0","Accept":"application/json"}),timeout=25) as r:
            if r.geturl()!=url+"index.json": raise ValueError("Unexpected redirect")
            raw=r.read(15_000_001)
            if len(raw)>15_000_000: raise ValueError("Export too large")
            obj=json.loads(raw)
        if not isinstance(obj,dict) or obj.get("schema_version")!="2.0":
            raise ValueError("Unsupported export schema")
        canonical=obj.get("canonical")
        if canonical not in (url,url.removeprefix(BASE)):
            raise ValueError("Canonical URL mismatch")
        self.cache[url]=obj
        return obj

def walk(x):
    if isinstance(x,dict):
        yield x
        for v in x.values(): yield from walk(v)
    elif isinstance(x,list):
        for v in x: yield from walk(v)

def catalog_index(doc, dates):
    """Index only explicit match URL + exact team labels in catalog objects."""
    index=defaultdict(dict)
    for x in walk(doc):
        url=x.get("url") or x.get("path") or x.get("canonical")
        name=x.get("name") or x.get("display_name") or x.get("title")
        if not isinstance(url,str) or not isinstance(name,str): continue
        if url.startswith("/"): url=BASE+url
        if not URL.fullmatch(url): continue
        date=DAY_SLUG.search(url)
        if not date or date[1] not in dates: continue
        parts=re.split(r" vs | — | v ",name)
        if len(parts)!=2 or not all(parts): continue
        index[(normalize_team(parts[0]),normalize_team(parts[1]))][url]={"display":parts[0]+" — "+parts[1],"date":date[1],"url":url}
    return index

def historical_cutoff(draw,archive):
    """Read historical draw metadata, never historical odds returned after close."""
    raw,_=official_fetch("/draws/"+str(draw))
    d=raw["draw"]
    if str(d["drawNumber"])!=str(draw) or str(d["productId"])!="1" or d["productName"]!="Stryktipset":
        raise ValueError("Wrong official product/draw")
    close=instant(d["regCloseTime"])
    if close>=datetime.now(timezone.utc): raise ValueError("Historical cutoff not passed")
    events=sorted(d["drawEvents"],key=lambda x:x["eventNumber"])
    if [e["eventNumber"] for e in events]!=list(range(1,14)):
        raise ValueError("Wrong official fixture count")
    for e,m in zip(events,archive["matches"]):
        participants=e["match"]["participants"]
        names={side:[p["name"] for p in participants if p["type"]==side] for side in ("home","away")}
        if any(len(v)!=1 for v in names.values()) or tuple(normalize_team(names[s][0]) for s in ("home","away"))!=tuple(normalize_team(m[s]) for s in ("home","away")):
            raise ValueError("Official archive fixture mismatch")
    return close.isoformat()

def build_round(data,draw,archive,pools,now):
    base=read(data/"analysis"/f"{draw}.json")
    result=read(data/"results"/f"{draw}.json") or pools.get(str(draw))
    latest=read(data/"latest.json")
    if base:
        close=instant(base["reg_close_time"])
        if result:
            if len(result["outcome"])!=13: raise ValueError("Bad official outcome")
            return base,result,close.date().isoformat(),"verified_coupon",None
        if draw==latest["draw_number"] and now<close:
            return base,None,close.date().isoformat(),"prospective_review",None
        raise ValueError("No eligible result or upcoming snapshot")
    r=archive[draw]
    if not result or result.get("outcome")!=r["outcome"] or len(r["matches"])!=13:
        raise ValueError("Missing/conflicting archived result")
    matches=[dict(m,number=i+1) for i,m in enumerate(r["matches"])]
    try:
        close=historical_cutoff(draw,r)
        status="verified_coupon"
        note=None
    except (OSError,KeyError,TypeError,ValueError) as exc:
        close=None;status="kickoff_only";note=str(exc)
    return {"draw_number":draw,"reg_close_time":close,"matches":matches},result,r["date"],status,note

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data",default="data")
    p.add_argument("--draws",nargs="+",type=int,default=list(range(4981,4971,-1)))
    p.add_argument("--budget",type=int,default=130)
    p.add_argument("--output",default="september-review.json")
    args=p.parse_args()
    if not 1<=args.budget<=130 or not set(args.draws)<=set(range(4972,4982)) or len(args.draws)!=len(set(args.draws)):
        p.error("Only unique draws 4972–4981 and budget 1–130")
    data=Path(args.data)
    archive={r["draw"]:r for r in read(data/"history/summary.json")["archive"]}
    pools=read(data/"history/official_pools.json")["draws"]
    now=datetime.now(timezone.utc); client=Client(args.budget)
    report={"schema":"v25-september-review-v1","started_at":now.isoformat(),"rounds":[],"rows":[],"errors":[]}
    stop=False
    for draw in args.draws:
        if stop: break
        try:
            base,result,date,status,note=build_round(data,draw,archive,pools,now)
            # 4980 full coverage already obtained in artifact 15234058123.
            # Preserve existing strict imports; no requests for already covered matches.
            prior=read(data/"v25/imported"/f"{draw}.json") or {}
            covered=set(prior.get("covered_positions",[]))
            if draw==4980: covered.update(range(1,14))
            positions=[m for m in base["matches"] if m["number"] not in covered]
            r={"draw":draw,"date":date,"cutoff_status":status,"reg_close_time":base["reg_close_time"],"cutoff_note":note,"already_covered":sorted(covered),"matches":[],"missing":[]}
            report["rounds"].append(r)
            if not positions: continue
            if draw==4981:
                url=ROOT
            else:
                url=ROOT+"archive/"+date.replace("-","/")+"/"
            catalog=client.get(url)
            index=catalog_index(catalog,{date})
            print("CATALOG",draw,"pairs",len(index),"cutoff",status,flush=True)
            for m in positions:
                n=m["number"]
                if m.get("played_consistent") is False:
                    r["missing"].append({"number":n,"reason":"unplayed/inconsistent"});continue
                opts=index.get((normalize_team(m["home"]),normalize_team(m["away"])),{})
                if len(opts)!=1:
                    r["missing"].append({"number":n,"reason":"ambiguous" if opts else "absent"});continue
                spec={**next(iter(opts.values())),"draw":draw,"number":n}
                try:
                    doc=client.get(spec["url"])
                    working=base
                    if status=="kickoff_only":
                        # This is a distinct pre-kickoff-only experiment, not a fabricated coupon cutoff.
                        working={**base,"reg_close_time":doc["event"]["starts_at"]}
                    if "score_home" in m:
                        score=doc["event"]["scoreline"].split("-")
                        if tuple(map(int,score))!=(m["score_home"],m["score_away"]):
                            raise ValueError("Exact archived score mismatch")
                    rows,rejected=extract(doc,spec,working,result,datetime.now(timezone.utc))
                    for row in rows:
                        row.update({"draw_number":draw,"cutoff_status":status,"reg_close_time":base["reg_close_time"],"kickoff":doc["event"]["starts_at"]})
                    report["rows"].extend(rows)
                    r["matches"].append({"number":n,"accepted":len(rows),"rejected":rejected,"url":spec["url"]})
                    print("IMPORT",draw,n,len(rows),status,flush=True)
                except StopBudget:
                    raise
                except HTTPError as exc:
                    report["errors"].append({"draw":draw,"number":n,"error":"HTTP "+str(exc.code)})
                    if exc.code in (401,403,429): stop=True; break
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    report["errors"].append({"draw":draw,"number":n,"error":str(exc)})
        except StopBudget as exc:
            report["errors"].append({"draw":draw,"error":str(exc)}); break
        except HTTPError as exc:
            report["errors"].append({"draw":draw,"error":"HTTP "+str(exc.code)})
            if exc.code in (401,403,429): break
        except (OSError,ValueError,KeyError,TypeError) as exc:
            report["errors"].append({"draw":draw,"error":str(exc)})
        # Checkpoint all accepted metadata even if a later date is unavailable.
        Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    report["requests"]=client.calls
    report["finished_at"]=datetime.now(timezone.utc).isoformat()
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    counts=defaultdict(int)
    for row in report["rows"]: counts[row["cutoff_status"]]+=1
    print("BULK TOTAL",len(report["rows"]),"by cutoff",dict(counts),"requests",client.calls,"errors",len(report["errors"]),flush=True)

if __name__=="__main__": main()
