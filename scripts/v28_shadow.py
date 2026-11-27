"""V27/28: experimental probabilities, no production integration.
Only time-frozen V24 observations and matching preclose form snapshots.
"""
from collections import defaultdict
from datetime import datetime, timezone
import math
from scripts.v25_history import instant, WEIGHTS, blend

def probability(v):
    if not isinstance(v,list) or len(v)!=3 or any(type(x) not in (float,int) or not math.isfinite(x) or x<0 for x in v) or not .99999<=sum(v)<=1.00001:
        raise ValueError("Invalid probability")
    return [x/sum(v) for x in v]

def community_rows(doc, report, now):
    if not doc:
        return {}
    try:
        close=instant(report["reg_close_time"])
        when=instant(doc["observed_at"])
        if doc["schema"]!="v24-community-v1" or doc["draw_number"]!=report["draw_number"] or instant(doc["reg_close_time"])!=close or when>=close or when>now or doc["market"]!="Full Time Result":
            return {}
        matches={m["number"]:(m["home"],m["away"]) for m in report["matches"]}
        result={}
        for r in doc["matches"]:
            n=r["number"]; v=r["votes"]
            if n in result or matches.get(n)!=(r["home"],r["away"]) or not isinstance(v,list) or len(v)!=3 or any(type(x)!=int or x<0 for x in v) or not sum(v) or not r["source"].startswith("https://www.olbg.com/"):
                return {}
            result[n]=r
        return result
    except (KeyError,TypeError,ValueError):
        return {}

def preview(report, base, form=None, community=None, now=None):
    now=now or datetime.now(timezone.utc)
    close=instant(base["reg_close_time"])
    created=instant(report["created_at_utc"])
    if report["mode"]!="prospective" or report["draw_number"]!=base["draw_number"] or instant(report["reg_close_time"])!=close or created>=close or created>now or report["market_observed_at"]!=base["observed_at_utc"] or instant(base["observed_at_utc"])>=close:
        raise ValueError("Not a matching frozen report")
    f={}
    if form and form.get("draw_number")==base["draw_number"] and form.get("source_snapshot_sha256")==base.get("source_snapshot_sha256") and form.get("source_observed_at_utc")==base["observed_at_utc"] and instant(form["created_at_utc"])<close and instant(form["created_at_utc"])<=now:
        f={m["number"]:m for m in form["matches"]}
    c=community_rows(community,report,now)
    groups=defaultdict(lambda:defaultdict(list))
    for p in report["picks"]:
        if p["type"]=="result" and p["kind"]=="human" and p["sign"] in "1X2" and len(p["sign"])==1:
            groups[p["number"]][p["group"]].append("1X2".index(p["sign"]))
    rows=[]
    for m in base["matches"]:
        n=m["number"]; market=probability(m["p"]); fm=f.get(n)
        form_p=market
        if fm and fm.get("used_form") and (fm["home"],fm["away"])==(m["home"],m["away"]):
            form_p=probability(fm["form_p"])
        # A publisher contributes one share vector. Community is evaluated separately,
        # or combined with a human signal excluding OLBG to avoid double-counting.
        gs=groups.get(n,{})
        def shares(g):
            return [sum(v.count(i)/len(v) for v in g.values())/len(g) for i in range(3)] if len(g)>=2 else None
        human=shares(gs); independent=shares({k:v for k,v in gs.items() if k.lower()!="olbg.com"})
        cr=c.get(n); cp=[x/sum(cr["votes"]) for x in cr["votes"]] if cr else None
        experiments=[]
        for w in WEIGHTS:
            ep=blend(market,human,w)
            # Equal half weight for the two channels, not additive exposure.
            if independent is not None and cp is not None:
                signal=[(a+b)/2 for a,b in zip(independent,cp)]
            else:
                signal=independent if independent is not None else cp
            experiments.append({"weight":w,"expert_only":ep,"community_only":blend(market,cp,w),"form_expert_community":blend(form_p,signal,w)})
        rows.append({"number":n,"home":m["home"],"away":m["away"],"market":market,"form":form_p,"expert_groups":len(gs),"human_shares":human,"community_votes":sum(cr["votes"]) if cr else 0,"experiments":experiments,"production":market})
    return {"schema":"v28-shadow-v1","draw_number":report["draw_number"],"report_created_at":report["created_at_utc"],"production_expert_weight":0,"matches":rows,"warning":"Oprövade scenarier. Ingen automatisk ändring av grundmodell eller system. Nyckelspelare ej numeriskt viktade; saknar validerat underlag. Minst två mänskliga publicister per match. OLBG dubbelräknas inte i kombinationen."}
