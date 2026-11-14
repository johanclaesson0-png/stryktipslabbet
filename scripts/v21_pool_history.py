#!/usr/bin/env python3
"""V21: verified AFTER-CLOSE Stryktipset turnover, winners & payouts.

Read-only official Swedish Spel API. NEVER turn old settlements into historical
preclose snapshots. Only store compact integer aggregate public metrics.
"""
import argparse
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import json
import re
from pathlib import Path
import sys
import time

from scripts.collect import fetch,parse_result,write_json
from scripts.history5 import read_rounds

SCHEMA="stryktipslabbet-official-pools-v21"
SOURCE="https://api.spela.svenskaspel.se/draw/1/stryktipset"
CLASSES=(10,11,12,13)


def currency_int(x):
    if isinstance(x,bool) or type(x) not in (float,int,str):
        raise ValueError("Saknar omsättning i kronor")
    try:
        d=Decimal(str(x).replace("\u00a0","").replace(" ","").replace(",","."))
    except InvalidOperation:
        raise ValueError("Ogiltig kronorvalor") from None
    if not d.is_finite() or d!=d.to_integral_value() or d<0 or d>500_000_000:
        raise ValueError("Kronorvärde utanför tillåten precision/intervall")
    return int(d)


def parse_official(doc,draw,verified_at):
    r=doc.get("result") if isinstance(doc,dict) else None
    if (not isinstance(r,dict) or r.get("productName")!="Stryktipset"
        or str(r.get("productId"))!="1" or str(r.get("drawNumber"))!=str(draw)
        or r.get("cancelled") is True):
        raise ValueError("Inte verifierat Stryktipsresultat")
    # API field currentNetSale is final AFTER CLOSE; do not call it a
    # timestamped historical pre-close turnover.
    turnover=currency_int(r.get("currentNetSale"))
    if turnover<100_000:
        raise ValueError("Omsättning för låg för verifierad kupong")
    result=parse_result(doc,draw,verified_at)
    won={}
    for d in r.get("distribution") or []:
        match=re.fullmatch(r"(10|11|12|13) r[äa]tt",str(d.get("name","")).strip(),re.I)
        if match:
            k=match.group(1)
            if k in won:
                raise ValueError("Dubblett i vinstgrupp")
            n=d.get("winners")
            if type(n) is not int or n<0 or n>turnover:
                raise ValueError("Antal vinnande rader är ogiltigt")
            amount=currency_int(d.get("amount"))
            if amount!=result["payouts"][k]:
                raise ValueError("Utdelningen avviker från officiella facitparsern")
            won[k]={"winners":n,"payout_per_row_kr":amount}
    if set(won)!={str(x) for x in CLASSES}:
        raise ValueError("En eller flera vinstklasser saknas")
    return {
        "draw_number":int(draw),"outcome":result["outcome"],
        "turnover_kr":turnover,"classes":won,
        "source_url":SOURCE+"/draws/"+str(draw)+"/result",
        "verified_at_utc":verified_at.isoformat(),
        "time_type":"after_final_result_not_preclose",
    }


def source_expectations(data):
    history=read_rounds(data/"history"/"stryktipset-five-years.csv")
    payout_path=data/"history"/"payouts.json"
    payout=json.loads(payout_path.read_text(encoding="utf-8"))
    if payout.get("schema")!="stryktipslabbet-historical-payouts-v1":
        raise ValueError("Inkompatibelt historiskt officiellt utdelningsarkiv")
    expected={}
    for d in history:
        n=d["draw"]
        official=payout["draws"].get(str(n))
        if not official:
            continue
        outcome="".join(m["outcome"] for m in d["matches"])
        if outcome!=official["outcome"]:
            continue
        expected[n]={"outcome":outcome,"payouts":official["payouts"]}
    # Add recent actual results only if already verified by normal official
    # result collector (preclose snapshot mandatory for that collector).
    for p in (data/"results").glob("*.json"):
        try:
            doc=json.loads(p.read_text(encoding="utf-8"))
            n=doc["draw_number"]
            if doc.get("schema")=="stryktipslabbet-result-v7" and n not in expected:
                expected[n]={"outcome":doc["outcome"],"payouts":doc["payouts"]}
        except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
            continue
    return expected


def compare(verified,expected):
    if verified["outcome"]!=expected["outcome"]:
        raise ValueError("Officiellt facit motsäger verifierat historiskt facit")
    for k in ("10","11","12","13"):
        if verified["classes"][k]["payout_per_row_kr"]!=expected["payouts"][k]:
            raise ValueError("Utdelningskälla stämmer inte med tidigare officiellt facit")


def backfill(root,limit=16,transport=fetch,nap=.5,now=None):
    if not 0<=limit<=80:
        raise ValueError("Max 80 verifieringsförsök per körning")
    now=now or datetime.now(timezone.utc)
    data=root/"data"
    dest=data/"history"/"official_pools.json"
    statepath=data/"history"/"official_pools_state.json"
    old={}
    try:
        doc=json.loads(dest.read_text(encoding="utf-8"))
        if doc.get("schema")!=SCHEMA or not isinstance(doc.get("draws"),dict):
            raise ValueError("Fel schema på tidigare arkiv")
        old=doc["draws"]
    except OSError:
        pass
    state={}
    try:
        state=json.loads(statepath.read_text(encoding="utf-8"))
    except (OSError,ValueError,TypeError,json.JSONDecodeError):
        pass
    expected=source_expectations(data)
    order=sorted(expected,reverse=True)
    if not order:
        raise ValueError("Inga verifierade historiska facit")
    initial=max(0,int(state.get("cursor",0)))%len(order)
    attempted=saved=0
    offset=0
    for offset in range(len(order)):
        if attempted>=limit:break
        draw=order[(initial+offset)%len(order)]
        if str(draw) in old:continue
        attempted+=1
        try:
            raw,_=transport("/draws/"+str(draw)+"/result")
            observed=parse_official(raw,draw,now)
            compare(observed,expected[draw])
            old[str(draw)]=observed
            saved+=1
        except (OSError,ValueError,TypeError,KeyError,OverflowError) as e:
            print("V21 kunde inte verifiera",draw,type(e).__name__,str(e)[:110],file=sys.stderr)
        if nap and attempted<limit:time.sleep(nap)
    if limit==0:
        offset=-1
    state={"cursor":(initial+offset+1)%len(order),
           "checked_at_utc":now.isoformat(),"verified_count":len(old),
           "available_comparable_draws":len(order),"attempted":attempted}
    write_json(statepath,state)
    write_json(dest,{"schema":SCHEMA,"source":SOURCE,"draws":dict(sorted(old.items(),
                  key=lambda kv:int(kv[0]))),
           "scope":"Only after-close official turnover/winners/payouts; not preclose forecast inputs",
           "updated_at_utc":now.isoformat()})
    return state


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--outdir",default="data")
    p.add_argument("--limit",type=int,default=16)
    args=p.parse_args()
    # backfill uses root/data as a single fixed layout
    data=Path(args.outdir)
    state=backfill(data.parent if data.name=="data" else data,
                   limit=args.limit)
    print("V21 OFFICIAL:",state["verified_count"],"verifierade kuponger av",
          state["available_comparable_draws"],"| nya API-försök:",state["attempted"])


if __name__=="__main__":
    main()
