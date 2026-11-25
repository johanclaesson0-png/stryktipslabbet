"""V22: exact model coverage of unique rows, plus a freshness audit.
Experimental only; no submission, no payout prediction or new probability model.
"""
import argparse
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
import json
import math

from scripts.analyze import valid_analysis
from scripts.collect import write_json
from scripts.publish import instant, valid_result
from scripts.v19_decision import original_ok

SCHEMA = "stryktipslabbet-v22-rows-v1"
BUDGET = 1800
SIGNS = "1X2"

def top_rows(ps, k):
    """Exact top-k under independent positive match probabilities.
    A discarded prefix cannot outrank k retained prefixes extended by its
    same suffix. Ties are broken deterministically by row text.
    """
    if not 1 <= k <= BUDGET or not ps:
        raise ValueError("Invalid budget")
    candidates = [(1., "")]
    for p in ps:
        if len(p)!=3 or min(p)<=0 or abs(sum(p)-1)>1e-6:
            raise ValueError("Invalid probabilities")
        candidates = sorted(((v*q, r+s) for v,r in candidates
                            for q,s in zip(p,SIGNS)), key=lambda x:(-x[0],x[1]))[:k]
    return [r for _,r in candidates]

def validate_rows(rows, n=13):
    if not 1 <= len(rows) <= BUDGET or len(set(rows))!=len(rows):
        raise ValueError("Invalid row count or duplicates")
    if any(len(r)!=n or set(r)-set(SIGNS) for r in rows):
        raise ValueError("Invalid signs")
    return rows

def row_index(row):
    i=0
    for c in row:
        i=3*i+SIGNS.index(c)
    return i

def outcome_weights(ps):
    weights=[1.]
    for p in ps:
        weights=[v*q for v in weights for q in p]
    return weights

def exact_coverage(rows, ps, weights=None):
    """Exact probability of >=k correct on the best row (not count of rows).
    Multi-source Hamming distance transform on the ternary outcome cube.
    All outcome masses are counted once; rows need not be independent.
    """
    n=len(ps)
    validate_rows(rows,n)
    weights=outcome_weights(ps) if weights is None else weights
    dist=bytearray([n+1])*(3**n)
    for row in rows:
        dist[row_index(row)]=0
    stride=1
    for _ in range(n):
        for start in range(0,len(dist),3*stride):
            for i in range(start,start+stride):
                j=i+stride
                k=j+stride
                a,b,c=dist[i],dist[j],dist[k]
                m=min(a,b,c)+1
                if a>m: dist[i]=m
                if b>m: dist[j]=m
                if c>m: dist[k]=m
        stride*=3
    bins=[0.]*(n+1)
    for w,d in zip(weights,dist):
        bins[n-d]+=w
    return {str(k):round(sum(bins[k:]),10) for k in range(max(0,n-3),n+1)}

def m_rows(choices):
    return validate_rows(["".join(r) for r in product(*choices)])

def stats(rows, ps, weights):
    rows=validate_rows(rows,len(ps))
    # Expected number of winning lines in each exact class, not predicted cash.
    expected=[0.]*(len(ps)+1)
    for r in rows:
        dp=[1.]
        for c,p in zip(r,ps):
            q=p[SIGNS.index(c)]
            nxt=[0.]*(len(dp)+1)
            for j,v in enumerate(dp):
                nxt[j]+=v*(1-q)
                nxt[j+1]+=v*q
            dp=nxt
        for j,v in enumerate(dp): expected[j]+=v
    return {"cost":len(rows),"rows":rows,
            "prob_at_least":exact_coverage(rows,ps,weights),
            "expected_exact_rows":{str(k):round(expected[k],9) for k in range(10,14)},
            "row_sign_counts":[[sum(r[i]==c for r in rows) for c in SIGNS]
                               for i in range(13)]}

def read(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError): return None

def match_report(data,base,folder):
    doc=read(data/folder/f"{base['draw_number']}.json")
    try:
        if (doc["draw_number"]!=base["draw_number"] or
            doc["source_snapshot_sha256"]!=base["source_snapshot_sha256"] or
            doc.get("source_observed_at_utc",doc.get("observed_at_utc"))!=base["observed_at_utc"] or
            not instant(base["observed_at_utc"])<=instant(doc["created_at_utc"])<instant(base["reg_close_time"]) or
            len(doc["matches"])!=13):
            return None
        return doc
    except (KeyError,TypeError,ValueError): return None

def audit(data,base):
    facts=match_report(data,base,"match_insights")
    moves=match_report(data,base,"market_moves")
    players=match_report(data,base,"player_reports/analysis")
    out=[]
    for i,m in enumerate(base["matches"]):
        item={"number":m["number"],"home":m["home"],"away":m["away"],
              "market_p":m["p"],"streck":m["streck"],"form_age_days":[None,None],
              "form_status":"saknas","player_status":"ej verifierat",
              "market_delta_pp":None,"streck_delta_pp":None}
        if facts:
            r=facts["matches"][i]
            if (r["number"],r["home"],r["away"])==(m["number"],m["home"],m["away"]):
                ages=[r.get(side+"_facts",{}).get("days_since_last_match_at_observation")
                      for side in ("home","away")]
                item["form_age_days"]=ages
                item["form_status"]=("kontrollera – gammal eller saknad data" if
                    any(type(x)!=int or not 0<=x<=21 for x in ages) else
                    "inom 21 dagar – kontrollera fullständighet")
        if moves:
            r=moves["matches"][i]
            if (r["number"],r["home"],r["away"])==(m["number"],m["home"],m["away"]):
                item["market_delta_pp"]=r.get("market_delta_pp")
                item["streck_delta_pp"]=r.get("streck_delta_pp")
        if players:
            r=players["matches"][i]
            if r["number"]==m["number"] and r["home"]["team"]==m["home"] and r["away"]["team"]==m["away"]:
                item["player_status"]="verifierade uppgifter kan finnas – granska källor" if any(
                    side.get("reported_absences") for side in (r["home"],r["away"])) else "ej verifierat"
        out.append(item)
    return out

def build(base,data,now):
    if not valid_analysis(base,now) or not instant(base["observed_at_utc"])<=now<instant(base["reg_close_time"]):
        raise ValueError("Only a pre-close analysis is eligible")
    ps=[m["p"] for m in base["matches"]]
    baseline=base["systems"][0]
    weights=outcome_weights(ps)
    top=top_rows(ps,BUDGET)
    candidates=[("m",m_rows(baseline["choices"])),
                ("same_cost",top[:baseline["cost"]]),("full_budget",top)]
    return {"schema":SCHEMA,"draw_number":base["draw_number"],
            "observed_at_utc":base["observed_at_utc"],"reg_close_time":base["reg_close_time"],
            "source_snapshot_sha256":base["source_snapshot_sha256"],"created_at_utc":now.isoformat(),
            "budget_limit":BUDGET,"hypothetical":True,
            "systems":[{"id":key,**stats(rows,ps,weights)} for key,rows in candidates],
            "matches":audit(data,base),
            "missing_factors":["odds från flera bolag","xG/xGA","aktuella startelvor"],
            "note":"Exakt modellmatematik under oberoende odds, inte en validerad egen prognos. Ingen automatisk inlämning."}

def valid_report(report,base,now):
    try:
        if (report["schema"]!=SCHEMA or report["hypothetical"] is not True or
            report["draw_number"]!=base["draw_number"] or
            report["source_snapshot_sha256"]!=base["source_snapshot_sha256"] or
            report["observed_at_utc"]!=base["observed_at_utc"] or
            report["reg_close_time"]!=base["reg_close_time"] or
            report["budget_limit"]!=BUDGET or
            not instant(report["observed_at_utc"])<=instant(report["created_at_utc"])<=now<instant(report["reg_close_time"])):
            return False
        ps=[m["p"] for m in base["matches"]]
        top=top_rows(ps,BUDGET)
        expected=[("m",m_rows(base["systems"][0]["choices"])),
                  ("same_cost",top[:base["systems"][0]["cost"]]),("full_budget",top)]
        if len(report["systems"])!=3 or len(report["matches"])!=13: return False
        for s,(key,rows) in zip(report["systems"],expected):
            if s["id"]!=key or s["rows"]!=rows or s["cost"]!=len(rows): return False
            mass=sum(math.prod(p[SIGNS.index(c)] for c,p in zip(r,ps)) for r in rows)
            if abs(s["prob_at_least"]["13"]-mass)>1e-8: return False
        return all((m["number"],m["home"],m["away"],m["market_p"],m["streck"])==
                   (b["number"],b["home"],b["away"],b["p"],b["streck"])
                   for m,b in zip(report["matches"],base["matches"]))
    except (TypeError,ValueError,KeyError,IndexError): return False

def settle(report,result):
    close=instant(report["reg_close_time"])
    if not instant(report["observed_at_utc"])<=instant(report["created_at_utc"])<close:
        raise ValueError("Not pre-close")
    if not valid_result(result,{report["draw_number"]:close},instant(result["observed_at_utc"])):
        raise ValueError("Invalid official result")
    systems=[]
    for s in report["systems"]:
        counts=[0]*14
        for r in validate_rows(s["rows"]):
            counts[sum(a==b for a,b in zip(r,result["outcome"]))]+=1
        paid=sum(counts[k]*result["payouts"][str(k)] for k in range(10,14))
        systems.append({"id":s["id"],"cost":len(s["rows"]),
                        "best":max(i for i,n in enumerate(counts) if n),
                        "correct_rows":{str(k):counts[k] for k in range(10,14)},
                        "gross":paid,"net":paid-len(s["rows"])})
    return {"schema":"stryktipslabbet-v22-settlement-v1","draw_number":report["draw_number"],
            "source_snapshot_sha256":report["source_snapshot_sha256"],
            "official_result_sha256":result.get("sha256"),"hypothetical":True,"systems":systems}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--outdir",default="data")
    data=Path(ap.parse_args().outdir)
    now=datetime.now(timezone.utc)
    snap=read(data/"latest.json")
    if snap:
        n=snap["draw_number"]
        base=read(data/"analysis"/f"{n}.json")
        target=data/"v22"/f"{n}.json"
        old=read(target)
        if original_ok(snap,base,now) and now<instant(base["reg_close_time"]):
            if not old or old.get("observed_at_utc")!=base["observed_at_utc"]:
                report=build(base,data,now)
                if datetime.now(timezone.utc)<instant(base["reg_close_time"]):
                    write_json(target,report)
                    print("V22 new frozen comparison",n)
    for p in (data/"v22").glob("*.json"):
        if not p.stem.isdigit(): continue
        report=read(p)
        result=read(data/"results"/p.name)
        if report and result:
            target=data/"v22_settlements"/p.name
            if not target.exists():
                try: write_json(target,settle(report,result))
                except (ValueError,KeyError,TypeError): continue

if __name__=="__main__": main()
