#!/usr/bin/env python3
"""Gradually verify historical Stryktipset 10/11/12/13 payouts with official API.

This is an AFTER-the-fact audit, not a source of historical pre-close odds.
Maximum 8 API requests per scheduled run, rotating even after failed fetches.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import time

from scripts.collect import fetch, parse_result, write_json
from scripts.history5 import read_rounds

SCHEMA = "stryktipslabbet-historical-payouts-v1"


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--outdir", default="data")
    parser.add_argument("--limit", type=int, default=8)
    args=parser.parse_args()
    out=Path(args.outdir)/"history"
    rounds=read_rounds(out/"stryktipset-five-years.csv")
    expected={r["draw"]:"".join(m["outcome"] for m in r["matches"]) for r in rounds}
    order=[r["draw"] for r in reversed(rounds)]
    cache=out/"payouts.json"
    statefile=out/"payout_state.json"
    try:
        p=json.loads(cache.read_text(encoding="utf-8"))
    except (ValueError,OSError):
        p={"schema":SCHEMA,"draws":{}}
    if p.get("schema")!=SCHEMA or not isinstance(p.get("draws"),dict):
        raise ValueError("Fel historiskt utdelningsarkiv")
    try:
        state=json.loads(statefile.read_text(encoding="utf-8"))
        cursor=int(state.get("cursor",0))
    except (ValueError,OSError,TypeError):
        cursor=0
    attempted=saved=0
    now=datetime.now(timezone.utc)
    for i in range(len(order)):
        if attempted>=max(0,min(args.limit,20)):
            break
        draw=order[(cursor+i)%len(order)]
        if str(draw) in p["draws"]:
            continue
        attempted+=1
        try:
            doc, _raw = fetch("/draws/"+str(draw)+"/result")
            # Official settlements may be observed years AFTER the event.
            result=parse_result(doc,draw,now)
            if result["outcome"]!=expected[draw]:
                raise ValueError("Official facit skiljer från speglat historiskt facit")
            p["draws"][str(draw)]={
                "outcome":result["outcome"],
                "payouts":result["payouts"],
                "source_url":result["source_url"],
                "verified_at_utc":now.isoformat()
            }
            saved+=1
            print("Verifierad utdelning:",draw)
        except Exception as exc:
            print("Ingen verifierad utdelning för",draw,str(exc)[:130],file=sys.stderr)
        time.sleep(.2)
    if order:
        # Increment by the number of *examined* draws, not only saved ones.
        state={"cursor":(cursor+len(order) if attempted==0 else (cursor+i+1))%len(order),
               "checked_at_utc":now.isoformat(),"verified_count":len(p["draws"])}
        write_json(statefile,state)
    if saved:
        write_json(cache,p)
    print("Officiellt verifierade omgångar:",len(p["draws"]),
          "av",len(order),"| försök:",attempted,"| nya:",saved)


if __name__=="__main__":
    main()
