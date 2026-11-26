"""V24: attributable observations, never an automatic betting model.
Retrospective reconstructions must not be scored as prospectively frozen.
One vote per identity/match/market; shared publishers shown separately.
"""
import argparse
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
import json
import math
from urllib.parse import urlparse
from scripts.publish import instant, valid_result
from scripts.analyze import valid_analysis
from scripts.collect import write_json
from scripts.v22_rows import read

SCHEMA="v24-expert-barometer-v1"
KINDS=("result","first","system")
SIGNS="1X2"

def validate_panel(doc):
    if doc["schema"]!="v24-panel-v1" or doc["target"]!=50 or len(doc["panel"])!=50:
        raise ValueError("Expected 50 candidate sources")
    p={x["id"]:x for x in doc["panel"]}
    if len(p)!=50 or any(x["kind"] not in ("human","editorial","site") or not x["group"] for x in p.values()):
        raise ValueError("Invalid source registry")
    return p

def accepted(doc,base,panel,now):
    close=instant(base["reg_close_time"])
    mode=doc["mode"]
    if (doc["schema"]!="v24-expert-observations-v1" or
        doc["draw_number"]!=base["draw_number"] or doc["reg_close_time"]!=base["reg_close_time"] or
        mode not in ("retrospective","prospective")):
        raise ValueError("Draw mismatch")
    if mode=="prospective" and now>=close:
        raise ValueError("Cannot create a new preclose report after cutoff")
    matches={m["number"]:m for m in base["matches"]}
    choices=defaultdict(list)
    for r in doc["picks"]:
        try:
            m=matches[r["number"]]
            p=panel[r["id"]]
            if (r["home"],r["away"])!=(m["home"],m["away"]):continue
            if r["type"] not in KINDS:continue
            s=r["sign"]
            if s not in ("1","X","2","1X","12","X2","1X2"):continue
            if r["type"]!="system" and len(s)!=1:continue
            u=urlparse(r["source"])
            if u.scheme!="https" or not u.hostname or u.username:continue
            seen=instant(r["observed_at"])
            if seen>now:continue
            src=instant(r["source_at"]) if r["source_at"] else None
            if src and (src>=close or src>seen):continue
            if mode=="prospective" and (seen>=close or not src or r["evidence"] not in
                ("article_timestamp","article_date_upper_bound","archive_recorded","direct_preclose")):continue
            if mode=="retrospective" and r["evidence"] not in
                ("article_timestamp","article_date_upper_bound","archive_recorded","postclose_page"):continue
            choices[(r["id"],r["number"],r["type"])].append((seen,r))
        except (KeyError,ValueError,TypeError,OverflowError):continue
    result=[]
    for key,values in sorted(choices.items()):
        latest=max(v[0] for v in values)
        tied=[r for t,r in values if t==latest]
        if len({r["sign"] for r in tied})!=1:continue
        r=tied[0].copy()
        r["name"]=panel[r["id"]]["name"]
        r["kind"]=panel[r["id"]]["kind"]
        r["group"]=panel[r["id"]]["group"]
        result.append(r)
    return result

def counts(rows,by_group=False):
    groups=defaultdict(list)
    for r in rows:groups[r["group"] if by_group else r["id"]].append(r)
    vals=[0.,0.,0.]
    for group in groups.values():
        for r in group:
            for c in r["sign"]:vals[SIGNS.index(c)]+=1/len(r["sign"])/len(group)
    n=len(groups)
    shares=[round(x/n,6) for x in vals] if n else None
    return {"n":n,"votes":[round(x,6) for x in vals],"shares":shares,
        "disagreement":round(1-max(shares),6) if shares else None}

def summarize(base,doc,panel,now):
    picks=accepted(doc,base,panel,now)
    matches=[]
    for m in base["matches"]:
        r=[x for x in picks if x["number"]==m["number"]]
        metrics={}
        for t in KINDS:
            for kind in ("human","editorial","site"):
                selected=[x for x in r if x["type"]==t and x["kind"]==kind]
                metrics[t+"_"+kind]={"individual":counts(selected),"publisher":counts(selected,True)}
        matches.append({"number":m["number"],"home":m["home"],"away":m["away"],
                        "market":m["p"],"streck":m["streck"],"metrics":metrics})
    return {"schema":SCHEMA,"draw_number":base["draw_number"],"reg_close_time":base["reg_close_time"],
            "created_at_utc":now.isoformat(),"market_observed_at":base["observed_at_utc"],
            "mode":doc["mode"],"candidate_count":50,"sources_with_data":len({r["id"] for r in picks}),
            "observations":len(picks),"matches":matches,"picks":picks,
            "warning":"Källor kan vara beroende. Förstaval, rena resultatval och systemgarderingar hålls isär. Ingen automatisk modellpåverkan."}

def settle(report,result):
    close=instant(report["reg_close_time"])
    if report["mode"]!="prospective" or instant(report["created_at_utc"])>=close:
        raise ValueError("Only genuinely preclose reports can enter evaluation")
    if not valid_result(result,{report["draw_number"]:close},instant(result["observed_at_utc"])):
        raise ValueError("Invalid result")
    by=defaultdict(lambda:{"n":0,"hit":0,"fractional_hit":0.,"market_top_hit":0})
    for r in report["picks"]:
        m=report["matches"][r["number"]-1]
        actual=result["outcome"][r["number"]-1]
        row=by[(r["id"],r["type"])]
        row["n"]+=1
        row["hit"]+=int(actual in r["sign"])
        row["fractional_hit"]+=int(actual in r["sign"])/len(r["sign"])
        row["market_top_hit"]+=int(SIGNS[max(range(3),key=lambda j:m["market"][j])]==actual)
    return {"schema":"v24-expert-settlement-v1","draw_number":report["draw_number"],
            "created_at_utc":report["created_at_utc"],"result_sha256":result.get("sha256"),
            "scores":[{"id":i,"type":t,**v} for (i,t),v in sorted(by.items())]}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--outdir",default="data");args=ap.parse_args()
    data=Path(args.outdir);now=datetime.now(timezone.utc)
    panel=validate_panel(read(data/"v24"/"panel.json"))
    for path in sorted((data/"v24_inputs").glob("*.json")):
        doc=read(path)
        base=read(data/"analysis"/path.name)
        if not doc or not base or not valid_analysis(base,now):continue
        target=data/"v24"/"reports"/path.name
        prior=read(target)
        if doc["mode"]=="retrospective":
            if not prior:write_json(target,summarize(base,doc,panel,now))
            continue
        close=instant(base["reg_close_time"])
        if now<close:
            report=summarize(base,doc,panel,now)
            if not prior or prior.get("picks")!=report["picks"] or prior.get("market_observed_at")!=report["market_observed_at"]:
                if datetime.now(timezone.utc)<close:
                    stamp=now.strftime("%Y%m%dT%H%M%S%fZ")
                    write_json(data/"v24"/"history"/path.stem/(stamp+".json"),report)
                    write_json(target,report)
        elif prior:
            official=read(data/"results"/path.name)
            dest=data/"v24"/"settlements"/path.name
            if official and not dest.exists():
                try:write_json(dest,settle(prior,official))
                except (ValueError,KeyError,TypeError):pass
    print("V24: expert panel reports processed")
if __name__=="__main__":main()
