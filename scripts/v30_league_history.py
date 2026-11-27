"""Collect a separate, retrospective league-wide expert dataset.
Only actual published catalog links, explicit 90-minute 1X2 claims, and
pre-kickoff records. Never feeds live probabilities or coupon backtests.
"""
import argparse, json, re, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from scripts.v25_forecastrecord import BASE, URL, extract
from scripts.v25_forecastrecord_api import team, ALIASES
from scripts.v25_history import instant, read

START = "2026-09-25"
LEAGUES = {
    "Premier League":BASE+"/football/competitions/premier-league/",
    "EFL Championship":BASE+"/football/competitions/efl-championship/",
    "EFL League One":BASE+"/football/competitions/efl-league-one/",
    "EFL League Two":BASE+"/football/competitions/efl-league-two/",
}
ALIASES.update({"brighton hove albion":"Brighton & Hove Albion",
    "tottenham":"Tottenham Hotspur","man utd":"Manchester United","man city":"Manchester City",
    "hull":"Hull City","norwich":"Norwich City","wrexham":"Wrexham",
    "burton":"Burton Albion","peterborough":"Peterborough United",
    "stockport":"Stockport County","wigan":"Wigan Athletic","swindon town":"Swindon",
    "swindon":"Swindon","crewe":"Crewe Alexandra","cambridge":"Cambridge United",
    "huddersfield":"Huddersfield Town","blackpool":"Blackpool","wimbledon":"AFC Wimbledon",
    "bournemouth":"AFC Bournemouth","grimsby":"Grimsby Town","rotherham":"Rotherham United",
    "shrewsbury":"Shrewsbury Town","fleetwood":"Fleetwood Town","newport":"Newport County",
    "accrington":"Accrington Stanley","tranmere":"Tranmere Rovers","colchester":"Colchester United",
    "salford":"Salford City","exeter":"Exeter City","cheltenham":"Cheltenham Town",
    "qpr":"Queens Park Rangers","preston":"Preston North End"})

def walk(obj):
    if isinstance(obj,dict):
        yield obj
        for x in obj.values(): yield from walk(x)
    elif isinstance(obj,list):
        for x in obj: yield from walk(x)

def pair(name):
    names=re.split(r" vs | — ",name)
    if len(names)!=2 or not all(names): raise ValueError("Unclear fixture")
    return names

def coupon_index(data):
    # Conservative exclusion by pair and date ±2 days; no crossover into
    # coupon validation. Known coupon fixtures only; external set still isolated.
    exclude=set()
    archive=read(data/"history/summary.json")["archive"]
    rounds=[(r["date"],r["matches"]) for r in archive if r["date"]>=START]
    for path in sorted((data/"analysis").glob("*.json")):
        b=read(path)
        if b and b.get("reg_close_time"):
            date=instant(b["reg_close_time"]).date().isoformat()
            if date>=START: rounds.append((date,b["matches"]))
    for date,matches in rounds:
        d=datetime.fromisoformat(date).date()
        for m in matches:
            for shift in range(-2,3):
                exclude.add(((d+timedelta(days=shift)).isoformat(),team(m["home"]),team(m["away"])))
    return exclude

def catalog_fixtures(doc,league,now,exclude):
    if doc.get("schema_version")!="2.0" or doc.get("page_type")!="league" or doc.get("league_info",{}).get("name")!=league:
        raise ValueError("League catalog mismatch")
    candidates=defaultdict(list)
    for x in walk(doc):
        path=x.get("url"); name=x.get("name"); kickoff=x.get("kickoff"); score=x.get("final_score")
        if not all(isinstance(v,str) for v in (path,name,kickoff,score)): continue
        url=BASE+path if path.startswith("/") else path
        if not URL.fullmatch(url) or not re.fullmatch(r"\d{1,2}-\d{1,2}",score): continue
        try:
            h,a=pair(name); at=instant(kickoff)
        except (ValueError,TypeError): continue
        date=at.date().isoformat()
        if date<START or at>=now or not url.endswith("-"+date+"/"): continue
        if (date,team(h),team(a)) in exclude: continue
        candidates[url].append({"url":url,"home":h,"away":a,"kickoff":at.isoformat(),"date":date,"score":score,"league":league})
    return [v[0] for u,v in sorted(candidates.items()) if len({(x["home"],x["away"],x["kickoff"],x["score"]) for x in v})==1]

class Client:
    def __init__(self,budget):
        self.budget=budget;self.calls=0;self.last=None
    def get(self,url):
        if url not in LEAGUES.values() and not URL.fullmatch(url): raise ValueError("Unapproved URL")
        if self.calls>=self.budget: raise ValueError("Budget reached")
        if self.last is not None: time.sleep(max(0,7-(time.monotonic()-self.last)))
        self.calls+=1;self.last=time.monotonic()
        with urlopen(Request(url+"index.json",headers={"User-Agent":"Stryktipslabbet research/1.0","Accept":"application/json"}),timeout=30) as res:
            if res.geturl()!=url+"index.json": raise ValueError("Unexpected redirect")
            raw=res.read(25_000_001)
            if len(raw)>25_000_000: raise ValueError("Export too large")
            d=json.loads(raw)
        if BASE+d.get("canonical","")!=url or d.get("schema_version")!="2.0": raise ValueError("Unexpected canonical/schema")
        return d

def event_rows(doc,spec,now):
    ev=doc["event"]; at=instant(ev["starts_at"]); settled=instant(ev["result_received_at"])
    if ev["status"]!="finished" or ev.get("postponement") or ev["competition_name"]!=spec["league"] or ev["scoreline"]!=spec["score"] or at!=instant(spec["kickoff"]) or not at<settled<=now:
        raise ValueError("Fixture/score/settlement mismatch")
    h,a=map(int,spec["score"].split("-")); actual="1" if h>a else "2" if h<a else "X"
    # The sole cutoff is kickoff here, NOT a Stryktipset deadline.
    base={"draw_number":0,"reg_close_time":at.isoformat(),"matches":[{"number":1,"home":spec["home"],"away":spec["away"]}]}
    query={"draw":0,"number":1,"url":spec["url"],"display":spec["home"]+" — "+spec["away"],"date":spec["date"]}
    rows,rejected=extract(doc,query,base,{"outcome":actual},now)
    for row in rows:
        row.pop("number",None)
        row.update({"event_id":ev["id"],"kickoff":at.isoformat(),"result_received_at":settled.isoformat(),"actual":actual,"scope":"external_league_review","cutoff_status":"kickoff_only","result_source":"Forecast Record (catalog and event; not independent)"})
    return rows,rejected

def profiles(rows):
    # Unique external identity × fixture. No name-only merging; duplicates
    # and conflicts excluded before counts. Profiles are descriptive, not skill
    # vs market: no simultaneous 1X2 probability vector has been verified.
    unique=defaultdict(list)
    for r in rows: unique[(r["external_id"],r["event_id"])].append(r)
    counts=defaultdict(lambda:{"n":0,"hits":0,"signs":{"1":[0,0],"X":[0,0],"2":[0,0]},"leagues":{}})
    for v in unique.values():
        if len({(r["sign"],r["actual"]) for r in v})!=1:continue
        r=min(v,key=lambda x:x["source_at"]); c=counts[r["external_id"]]
        hit=int(r["sign"]==r["actual"]);c["n"]+=1;c["hits"]+=hit
        c["name"]=r["name"];c["kind"]=r["kind"]
        c["signs"][r["sign"]][0]+=1;c["signs"][r["sign"]][1]+=hit
        l=c["leagues"].setdefault(r["league"],[0,0]);l[0]+=1;l[1]+=hit
    return [{"external_id":k,**v} for k,v in sorted(counts.items())]

def main():
    p=argparse.ArgumentParser();p.add_argument("--data",default="data")
    p.add_argument("--budget",type=int,default=64);p.add_argument("--output",default="league-review.json")
    a=p.parse_args()
    if not 8<=a.budget<=120:p.error("budget 8–120")
    now=datetime.now(timezone.utc);client=Client(a.budget);exclude=coupon_index(Path(a.data))
    report={"schema":"v30-league-review-v1","started_at":now.isoformat(),"start_date":START,"rows":[],"matches":[],"catalogs":[],"errors":[]}
    queues={};stop=False
    for league,url in LEAGUES.items():
        try:
            items=catalog_fixtures(client.get(url),league,now,exclude)
            # Chronological systematic sample across available dates (not chosen
            # by outcome or a particular expert's success).
            items.sort(key=lambda x:(x["kickoff"],x["url"]))
            queues[league]=items
            report["catalogs"].append({"league":league,"eligible_listed":len(items),"url":url})
            print("LEAGUE",league,len(items),flush=True)
        except HTTPError as e:
            report["errors"].append({"league":league,"error":"HTTP "+str(e.code)})
            if e.code in (401,403,429):stop=True;break
        except (KeyError,ValueError,TypeError,OSError) as e:
            report["errors"].append({"league":league,"error":str(e)})
    # Balanced selection across leagues. Process different date ranges evenly.
    allot=max(1,(a.budget-client.calls)//max(1,len(queues)))
    sampled={}
    for league,v in queues.items():
        if len(v)<=allot: sampled[league]=v
        else: sampled[league]=[v[min(len(v)-1,int((i+.5)*len(v)/allot))] for i in range(allot)]
    for i in range(max((len(v) for v in sampled.values()),default=0)):
        if stop:break
        for league,q in sampled.items():
            if i>=len(q) or client.calls>=client.budget:continue
            spec=q[i]
            try:
                rows,rejected=event_rows(client.get(spec["url"]),spec,datetime.now(timezone.utc))
                report["rows"].extend(rows);report["matches"].append({**spec,"accepted":len(rows),"rejected":rejected})
                print("LEAGUE IMPORT",league,spec["date"],len(rows),flush=True)
            except HTTPError as e:
                report["errors"].append({"url":spec["url"],"error":"HTTP "+str(e.code)})
                if e.code in (401,403,429):stop=True;break
            except (ValueError,KeyError,TypeError,OSError) as e:
                report["errors"].append({"url":spec["url"],"error":str(e)})
            Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    report["profiles"]=profiles(report["rows"]);report["requests"]=client.calls
    report["finished_at"]=datetime.now(timezone.utc).isoformat()
    Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("LEAGUE TOTAL",len(report["rows"]),"matches",len(report["matches"]),"identities",len(report["profiles"]),"requests",client.calls,"errors",len(report["errors"]),flush=True)
    if not report["rows"]:raise SystemExit(1)
if __name__=="__main__":main()
