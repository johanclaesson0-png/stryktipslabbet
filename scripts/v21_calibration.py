#!/usr/bin/env python3
"""V21: distinguish verifiable AFTER-CLOSE payout history from real pre-close tests.

Historical actual winnings/turnover can assess the payout allocation equation.
Only SAME-DRAW archived, preclose market snapshots can test independent-crowd
winner-count estimates; only preclose V20 strategy files can test actual
hypothetical strategy returns. Never backfill a wager with postclose odds.
"""
import argparse
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import statistics

from scripts.analyze import correct_rows
from scripts.publish import instant,valid_snapshot
from scripts.v19_evaluation import pick_locked_snapshot,json_doc
from scripts.v20_payout_simulator import crowds_class_likelihood,POOL_SHARES,RETURN_FRACTION,SCHEMA as V20_SCHEMA
from scripts.v21_pool_history import SCHEMA as POOL_SCHEMA

SCHEMA="stryktipslabbet-official-calibration-v21"
CLASSES=(10,11,12,13)


def quantile(values,f):
    if not values:return None
    a=sorted(float(x) for x in values)
    i=min(len(a)-1,max(0,int(round((len(a)-1)*f))))
    return round(a[i],3)


def historical_summary(draws):
    """Pure observed after-the-fact numbers; NO crowd/odds calibration here."""
    entries=[d for d in draws.values()
             if isinstance(d,dict) and
             type(d.get("turnover_kr")) is int and
             d["turnover_kr"]>100000 and
             isinstance(d.get("classes"),dict)]
    turnovers=[x["turnover_kr"] for x in entries]
    summary={"draws_with_official_turnover_winners":len(entries),
             "turnover_median_kr":quantile(turnovers,.5),
             "turnover_p10_kr":quantile(turnovers,.10),
             "turnover_p90_kr":quantile(turnovers,.90),
             "by_class":{}}
    for k in CLASSES:
        key=str(k)
        sample=[d for d in entries if key in d["classes"]]
        vals=[d["classes"][key]["winners"] for d in sample]
        pays=[d["classes"][key]["payout_per_row_kr"] for d in sample]
        ratios=[]
        for d in sample:
            w=d["classes"][key]["winners"]
            pay=d["classes"][key]["payout_per_row_kr"]
            theoretical=d["turnover_kr"]*RETURN_FRACTION*POOL_SHARES[k]
            # Avoid a spurious precision claim for jackpot, zero payout,
            # no-winner, guarantee and reallocation events.
            if w>0 and pay>=15:
                ratios.append((w*pay)/theoretical)
        summary["by_class"][key]={
            "rounds_with_winners_data":len(sample),
            "winner_rows_median":quantile(vals,.5),
            "winner_rows_p10":quantile(vals,.10),
            "winner_rows_p90":quantile(vals,.90),
            "actual_payout_median_kr":quantile(pays,.5),
            "zero_winner_rounds":sum(v==0 for v in vals),
            "zero_payout_rounds":sum(v==0 for v in pays),
            "observed_vs_simple_pool_ratio_median":quantile(ratios,.5),
            "allocation_ratio_scope":"Retrospective accounting only; includes jackpots and guarantees",
        }
    return summary


def frozen_crowd_market(snapshot,source):
    if not valid_snapshot(snapshot,instant(source["verified_at_utc"])):
        return None
    if snapshot.get("draw_number")!=source["draw_number"]:
        return None
    if instant(snapshot["observed_at_utc"])>=instant(snapshot["reg_close_time"]):
        return None
    matches=sorted(snapshot["matches"],key=lambda m:m["number"])
    if len(matches)!=13:return None
    try:
        crowd=[]
        for m in matches:
            s=m["streck"]
            if len(s)!=3 or not 98.9<=sum(s)<=101.1:return None
            crowd.append([v/sum(s) for v in s])
        outcome=tuple("1X2".index(x) for x in source["outcome"])
        return crowd,outcome
    except (ValueError,KeyError,TypeError,ZeroDivisionError):
        return None


def verify_v20_forecast(data,draw,source):
    """Only V20 predictions already saved BEFORE the official draw ended."""
    candidates=[data/"v20_history"/f"{draw}.json",data/"v20"/"simulator.json"]
    frozen=pick_locked_snapshot(data,draw,instant(source["verified_at_utc"]))
    if frozen is None:return None
    accepted=[]
    for path in candidates:
        model=json_doc(path)
        if not isinstance(model,dict) or not model.get("scenarios"):
            continue
        try:
            if (model.get("schema")!=V20_SCHEMA or model.get("draw_number")!=draw
                or model.get("source_snapshot_sha256")!=frozen.get("sha256")
                or model.get("observed_at_utc")!=frozen.get("observed_at_utc")
                or instant(model["generated_at_utc"])>=instant(frozen["reg_close_time"])
                or instant(model["generated_at_utc"])<instant(frozen["observed_at_utc"])):
                continue
            accepted.append(model)
        except (KeyError,TypeError,ValueError,OverflowError):
            continue
    return min(accepted,key=lambda v:v["generated_at_utc"]) if accepted else None


def prospective_comparison(data,draws):
    metrics={k:[] for k in CLASSES}
    model_settlements=[]
    matched_draws=0
    for draw_id,entry in sorted(draws.items(),key=lambda r:int(r[0])):
        n=int(draw_id)
        when=instant(entry["verified_at_utc"])
        snap=pick_locked_snapshot(data,n,when)
        if snap is None:continue
        result=frozen_crowd_market(snap,entry)
        if result is None:continue
        crowd,observed=result
        likelihood=crowds_class_likelihood(crowd,observed)
        matched_draws+=1
        for k in CLASSES:
            predicted=entry["turnover_kr"]*likelihood[k]
            actual=entry["classes"][str(k)]["winners"]
            metrics[k].append({"draw":n,"predicted":predicted,"actual":actual,
                               "ratio":actual/predicted if predicted>.00001 else None})
        model=verify_v20_forecast(data,n,entry)
        if model is None:continue
        # Match the SAME set of prior-saved system choices to the real
        # outcome and actual final payout; NEVER use it as a preclose forecast.
        first=model["scenarios"][0]
        for b in first["budgets"]:
            for variant in b["strategies"]:
                choices=variant["choices"]
                if (len(choices)!=13 or
                    math.prod(len(c) for c in choices)!=b["exact_cost"]):
                    continue
                hits=correct_rows(choices,entry["outcome"])
                earned=sum(hits[k]*entry["classes"][str(k)]["payout_per_row_kr"]
                           for k in CLASSES)
                model_settlements.append({
                    "draw_number":n,"budget":b["budget"],"variant":variant["id"],
                    "cost":b["exact_cost"],"actual_net_kr":round(earned-b["exact_cost"],2),
                    "actual_paid_kr":round(earned,2),
                    "rows_10":hits[10],"rows_11":hits[11],
                    "rows_12":hits[12],"rows_13":hits[13],
                })
    out={"prospective_draws_with_preclose_streck_and_official_winners":matched_draws,
         "class_error":{},
         "correctly_frozen_v20_strategy_draws":len({r["draw_number"] for r in model_settlements}),
         "actually_settled_hypothetical_v20_strategies":model_settlements}
    for k,items in metrics.items():
        ratios=[x["ratio"] for x in items if x["ratio"] is not None]
        out["class_error"][str(k)]={
            "draws":len(items),
            "predicted_winners_median":quantile([x["predicted"] for x in items],.5),
            "actual_winners_median":quantile([x["actual"] for x in items],.5),
            "actual_to_independent_crowd_ratio_median":quantile(ratios,.5),
            "log10_error_mae":round(statistics.mean(
                abs(math.log10((x["actual"]+1)/(x["predicted"]+1)))
                for x in items),5) if items else None,
            "reliable_for_multiplier_calibration":len(items)>=20,
        }
    return out


def build(data,now=None):
    now=now or datetime.now(timezone.utc)
    raw=json_doc(data/"history"/"official_pools.json")
    if not isinstance(raw,dict) or raw.get("schema")!=POOL_SCHEMA:
        pools={}
    else:
        pools=raw["draws"]
    history=historical_summary(pools)
    actual=prospective_comparison(data,pools)
    recent=sorted(pools.values(),key=lambda d:d["draw_number"],reverse=True)[:6]
    return {"schema":SCHEMA,"generated_at_utc":now.isoformat(),
       "historical_actuals":history,
       "prospective_model_check":actual,
       "recent_verified_draws":[{
           "draw_number":d["draw_number"],"turnover_kr":d["turnover_kr"],
           "winning_rows":{k:d["classes"][k]["winners"] for k in ("10","11","12","13")},
           "payouts":{k:d["classes"][k]["payout_per_row_kr"] for k in ("10","11","12","13")},
           "source_url":d["source_url"],
           "time_type":"officiellt resultat efter avslut",
       } for d in recent],
       "status":("Historiska officiella faktiska belopp och vinnarantal"
                 if pools else "Inga verifierade omsättningar ännu"),
       "warnings":[
           "Äldre officiell omsättning och vinnarantal är efterhandsfacit, inte förhandsodds.",
           "Inga historiska sannolikhetsfördelningar hittas på när förhandsstreck saknas.",
           "Kalibrering mot streck kräver minst 20 tidsfrysta kuponger med senare officiellt facit.",
           "Oberoendeantagandet för hur andra kombinerar strecken är obevisat.",
           "V20 är hypotetisk och dess faktiska lönsamhet är ännu inte verifierad.",
       ]}


def main():
    p=argparse.ArgumentParser();p.add_argument("--outdir",default="data")
    args=p.parse_args();data=Path(args.outdir)
    r=build(data)
    target=data/"v21"/"calibration.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("V21 kalibrering: officiella omgångar",
          r["historical_actuals"]["draws_with_official_turnover_winners"],
          "| jämförbara tidsfrysta streckomgångar",
          r["prospective_model_check"]["prospective_draws_with_preclose_streck_and_official_winners"])


if __name__=="__main__":
    main()
