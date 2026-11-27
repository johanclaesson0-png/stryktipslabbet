"""Discover actual coupon matches via the public Forecast Record catalog.
Read-only review output. No production odds, tips or stake changes.
"""
import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from scripts.v25_forecastrecord import BASE, URL, norm, extract
from scripts.v25_history import read, instant

ALIASES = {
    "ipswich":"Ipswich Town", "leeds":"Leeds United", "coventry":"Coventry City",
    "birmingham":"Birmingham City", "bolton":"Bolton Wanderers",
    "derby":"Derby County", "west bromwich":"West Bromwich Albion",
    "sheffield u":"Sheffield United", "sheffield w":"Sheffield Wednesday",
    "west ham":"West Ham United", "stoke":"Stoke City", "luton":"Luton Town",
    "oxford":"Oxford United", "wycombe":"Wycombe Wanderers", "bradford":"Bradford City",
    "newcastle":"Newcastle United", "tottenham":"Tottenham Hotspur",
    "bournemouth":"AFC Bournemouth", "nottingham":"Nottingham Forest",
    "lincoln":"Lincoln City", "middlesbrough":"Middlesbrough",
    "swansea":"Swansea City", "wolverhampton":"Wolverhampton Wanderers",
    "charlton":"Charlton Athletic", "sverige":"Sweden",
    "bosnien & hercegovina":"Bosnia-Herzegovina", "danmark":"Denmark",
    "norge":"Norway", "rumänien":"Romania", "polen":"Poland",
    "nordirland":"Northern Ireland", "ukraina":"Ukraine",
    "österrike":"Austria", "irland":"Rep of Ireland",
    "georgien":"Georgia", "ungern":"Hungary",
    "plymouth":"Plymouth Argyle", "stockport":"Stockport County",
    "wimbledon":"AFC Wimbledon", "wigan":"Wigan Athletic", "swindon":"Swindon Town",
    "grimsby":"Grimsby Town", "hull":"Hull City",
}
def team(s):
    return norm(ALIASES.get(s.casefold().strip(),s))

class Client:
    def __init__(self, maximum=14):
        self.maximum=maximum
        self.calls=0
        self.last=None
    def get(self, url):
        if url!=BASE+"/football/matches/" and not URL.fullmatch(url):
            raise ValueError("Unapproved API path")
        if self.calls>=self.maximum:
            raise ValueError("Per-run request budget exhausted")
        if self.last is not None:
            time.sleep(max(0,7-(time.monotonic()-self.last)))
        self.calls+=1
        self.last=time.monotonic()
        with urlopen(Request(url+"index.json",headers={"User-Agent":"Stryktipslabbet research/1.0","Accept":"application/json"}),timeout=25) as res:
            if res.geturl()!=url+"index.json":
                raise ValueError("Unexpected API redirect")
            raw=res.read(15_000_001)
            if len(raw)>15_000_000:
                raise ValueError("Export too large")
            return json.loads(raw)

def discover(catalog, base):
    if catalog.get("schema_version")!="2.0" or catalog.get("canonical")!="/football/matches/" or catalog.get("page_type")!="catalog":
        raise ValueError("Unexpected catalog schema")
    date=instant(base["reg_close_time"]).date().isoformat()
    index={}
    for g in catalog["catalog"]["groups"]:
        for item in g["items"]:
            path=item.get("url","")
            name=item.get("name","")
            url=BASE+path
            if not URL.fullmatch(url) or not path.endswith("-"+date+"/") or name.count(" vs ")!=1:
                continue
            a,b=name.split(" vs ")
            key=team(a),team(b)
            index.setdefault(key,{})[url]=a+" — "+b
    found=[]; missing=[]
    for m in base["matches"]:
        options=index.get((team(m["home"]),team(m["away"])),{})
        if len(options)!=1:
            missing.append({"number":m["number"],"home":m["home"],"away":m["away"],"reason":"ambiguous" if options else "not in catalog"})
            continue
        url,display=next(iter(options.items()))
        found.append({"draw":base["draw_number"],"number":m["number"],"display":display,"date":date,"url":url})
    return found,missing

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data",default="data")
    p.add_argument("--draw",type=int)
    p.add_argument("--limit",type=int,default=13)
    p.add_argument("--output",default="forecastrecord-api-review.json")
    args=p.parse_args()
    if not 1<=args.limit<=13:
        p.error("Limit must be 1–13")
    data=Path(args.data)
    latest=read(data/"latest.json")
    draw=args.draw or latest["draw_number"]
    base=read(data/"analysis"/f"{draw}.json")
    official=read(data/"results"/f"{draw}.json")
    now=datetime.now(timezone.utc)
    if not base or (official is None and now>=instant(base["reg_close_time"])):
        raise ValueError("No eligible current coupon or historical result")
    if official is None and (draw!=latest["draw_number"] or base["reg_close_time"]!=latest["reg_close_time"]):
        raise ValueError("Current snapshot mismatch")
    client=Client(args.limit+1)
    report={"schema":"forecastrecord-api-review-v1","draw_number":draw,"mode":"retrospective" if official else "prospective_review","cutoff":base["reg_close_time"],"matches":[],"rows":[],"errors":[]}
    catalog=client.get(BASE+"/football/matches/")
    specs,missing=discover(catalog,base)
    report["missing"]=missing
    print("DISCOVERY",draw,len(specs),"missing",len(missing),flush=True)
    for spec in specs[:args.limit]:
        try:
            rows,rejected=extract(client.get(spec["url"]),spec,base,official,datetime.now(timezone.utc))
            for row in rows:
                row["draw_number"]=draw
            report["rows"].extend(rows)
            report["matches"].append({"number":spec["number"],"url":spec["url"],"accepted":len(rows),"rejected":rejected})
            print("IMPORT",spec["number"],len(rows),rejected,flush=True)
        except HTTPError as e:
            report["errors"].append({"number":spec["number"],"error":"HTTP "+str(e.code)})
            print("HTTP",spec["number"],e.code,flush=True)
            if e.code in (401,403,429): break
        except (ValueError,KeyError,TypeError,OSError) as e:
            report["errors"].append({"number":spec["number"],"error":str(e)})
            print("ERROR",spec["number"],str(e),flush=True)
    report["requests"]=client.calls
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("TOTAL",len(report["rows"]),"matches",len(report["matches"]),"errors",len(report["errors"]),"requests",client.calls)
    if report["errors"] or not report["matches"]: raise SystemExit(1)

if __name__=="__main__":
    main()
