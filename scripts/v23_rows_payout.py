"""V23: hypothetical payout simulation for V22's arbitrary unique row lists.

All systems see the same simulated outcomes. The field is modelled using
marginal crowd proportions, not observed joint public rows. No submission.
"""
import argparse
from datetime import datetime,timezone
import math
from pathlib import Path
import statistics

from scripts.collect import write_json
from scripts.publish import instant
from scripts.v19_decision import original_ok
from scripts.v22_rows import read, valid_report, validate_rows
from scripts.v20_payout_simulator import (
    valid_probability_rows, sample_outcomes, crowds_class_likelihood,
    potential_payout, TURNOVERS, CROWD_MULTIPLIERS, SAMPLES, SEED,
)

SCHEMA="stryktipslabbet-v23-row-payout-v1"
SIGN="1X2"
MASK=sum(1<<(2*i) for i in range(13))

def packed(seq):
    return sum(int(s)<<(2*i) for i,s in enumerate(seq))

def row_codes(rows):
    return [packed(SIGN.index(c) for c in r) for r in validate_rows(rows)]

def winning_counts(codes, outcome):
    target=packed(outcome)
    bins=[0]*14
    for code in codes:
        delta=code^target
        misses=((delta|(delta>>1))&MASK).bit_count()
        bins[13-misses]+=1
    return bins

def validate_context(context,base):
    try:
        if (context["schema"]!="stryktipslabbet-reviewed-context-v23" or
            context["draw_number"]!=base["draw_number"] or
            context["reg_close_time"]!=base["reg_close_time"] or
            datetime.fromisoformat(context["review_date"]).date()>instant(base["reg_close_time"]).date() or
            len(context["matches"])!=13):return False
        for a,b in zip(context["matches"],base["matches"]):
            if (a["number"],a["home"],a["away"])!=(b["number"],b["home"],b["away"]):return False
            p=a["consensus"]
            if (len(p)!=3 or not all(math.isfinite(x) and 0<x<1 for x in p) or
                abs(sum(p)-1)>1e-6 or a["bookmakers"]<3 or
                not a["source"].startswith("https://tipsaudit.com/match/")):return False
        return True
    except (KeyError,TypeError,ValueError,OverflowError):return False

def mass(rows, ps):
    return sum(math.prod(p[SIGN.index(c)] for c,p in zip(r,ps)) for r in rows)

def analyze(base,report,context,now,n=SAMPLES):
    if not valid_report(report,base,now):raise ValueError("Missing valid V22 report")
    market,crowd=valid_probability_rows(base["matches"])
    ctx=validate_context(context,base) and datetime.fromisoformat(context["review_date"]).date()<=now.date()
    external=[m["consensus"] for m in context["matches"]] if ctx else None
    candidates=report["systems"]
    outcomes=sample_outcomes(market,n,SEED)
    likes=[crowds_class_likelihood(crowd,y) for y in outcomes]
    counts={}
    comparisons=[]
    for s in candidates:
        codes=row_codes(s["rows"])
        counts[s["id"]]=[winning_counts(codes,y) for y in outcomes]
        comparisons.append({"id":s["id"],"cost":len(codes),
            "p13_market":s["prob_at_least"]["13"],
            "p13_external_context":round(mass(s["rows"],external),10) if external else None})
    scenarios=[]
    for turnover in TURNOVERS:
        for multiplier in CROWD_MULTIPLIERS:
            stats=[]
            for s in candidates:
                cost=s["cost"]
                paid=[]
                for r,like in zip(counts[s["id"]],likes):
                    other={k:max(0.,turnover-cost)*like[k] for k in (10,11,12,13)}
                    paid.append(potential_payout(r,other,turnover,multiplier))
                avg=statistics.mean(paid)
                se=statistics.stdev(paid)/math.sqrt(n)
                stats.append({"id":s["id"],"cost":cost,
                    "mean_net_kr":round(avg-cost),"mean_paid_kr":round(avg),
                    "median_net_kr":round(statistics.median(paid)-cost),
                    "prob_positive_net":round(sum(x>cost for x in paid)/n,6),
                    "prob_zero_payout":round(sum(x==0 for x in paid)/n,6),
                    "sampling_only_ci95_net_kr":[round(avg-cost-1.96*se),round(avg-cost+1.96*se)]})
            scenarios.append({"assumed_turnover_kr":turnover,"crowd_multiplier":multiplier,"systems":stats})
    return {"schema":SCHEMA,"draw_number":base["draw_number"],
        "observed_at_utc":base["observed_at_utc"],"reg_close_time":base["reg_close_time"],
        "created_at_utc":now.isoformat(),"source_snapshot_sha256":base["source_snapshot_sha256"],
        "v22_created_at_utc":report["created_at_utc"],"simulation_draws":n,
        "hypothetical":True,"comparisons":comparisons,"scenarios":scenarios,
        "context_review_date":context["review_date"] if ctx else None,
        "warning":"Illustrativa pottar; jackpot, omfördelning och garantier ingår inte. Ingen validerad EV. Extern engångsgranskning ändrar inte sannolikhetsmodellen."}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--outdir",default="data")
    args=ap.parse_args()
    data=Path(args.outdir)
    now=datetime.now(timezone.utc)
    snap=read(data/"latest.json")
    if not snap:return
    n=snap["draw_number"]
    base=read(data/"analysis"/f"{n}.json")
    report=read(data/"v22"/f"{n}.json")
    context=read(data/"v23_context"/f"{n}.json")
    target=data/"v23"/f"{n}.json"
    if not original_ok(snap,base,now) or not report or now>=instant(base["reg_close_time"]):return
    old=read(target)
    if old and old.get("observed_at_utc")==base["observed_at_utc"] and old.get("context_review_date")== (context.get("review_date") if context else None):return
    result=analyze(base,report,context,now)
    if datetime.now(timezone.utc)<instant(base["reg_close_time"]):
        write_json(target,result)
        print("V23: simulated arbitrary rows",n,len(result["scenarios"]))

if __name__=="__main__":main()
