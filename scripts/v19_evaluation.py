#!/usr/bin/env python3
"""V19: prospective, matched-input model evaluation against frozen market odds.

Never reconstruct historical odds from results. Every evaluable draw has one
pre-declared, outcome-independent market snapshot: latest at least 30 minutes
before close. Missing source-model data means missing evaluation, NOT neutral
performance. Results enter only after all probabilities/systems were frozen.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import random

from scripts.analyze import create_analysis, correct_rows
from scripts.feature_model import validate as validate_form
from scripts.pool_value import validate as validate_value
from scripts.player_impact import build as build_player
from scripts.publish import instant, valid_result, valid_snapshot
from scripts.solo import derive as derive_solo

SCHEMA="stryktipslabbet-evidence-gate-v19"
SIGNS="1X2"
MIN_ADVANCE=timedelta(minutes=30)
EVALUATION_DRAW_MIN=30
EVALUATION_MATCH_MIN=300
MIN_BRIER_GAIN=.004
ROOT=Path(__file__).resolve().parents[1]
FACTOR_NAMES={
    "form":"Form utöver odds",
    "player":"Spelarfrånvaro utöver odds",
    "value":"Streckvärde i systemval (ej 1/X/2-prognos)",
}


def json_doc(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def valid_p(p):
    return (isinstance(p,list) and len(p)==3
            and all(type(v) in (float,int) and math.isfinite(v) and 0<v<1 for v in p)
            and abs(sum(p)-1)<1e-5)


def score(p,y):
    if not valid_p(p) or y not in SIGNS:
        raise ValueError("Ogiltig sannolikhetsvektor/utfall")
    k=SIGNS.index(y)
    return {"brier":sum((x-int(i==k))**2 for i,x in enumerate(p)),
            "logloss":-math.log(p[k]),
            "top1":int(max(range(3),key=lambda i:p[i])==k)}


def pick_locked_snapshot(data,draw,now):
    """An ex-ante fixed cutoff rule, independent of availability/outcome."""
    candidates=[]
    for p in (data/"snapshots"/str(draw)).glob("*.json"):
        snap=json_doc(p)
        if not snap or snap.get("draw_number")!=draw:
            continue
        try:
            observed=instant(snap["observed_at_utc"])
            close=instant(snap["reg_close_time"])
            if observed<=close-MIN_ADVANCE and valid_snapshot(snap,now):
                candidates.append((observed,str(p),snap))
        except (KeyError,ValueError,TypeError,OverflowError):
            pass
    candidates.sort(key=lambda item:(item[0],item[1]))
    return candidates[-1][2] if candidates else None


def archived_reports(data,folder,draw):
    candidates=[]
    paths=[data/folder/f"{draw}.json"]
    paths.extend(sorted((data/(folder+"_history")/str(draw)).glob("*.json")))
    for p in paths:
        report=json_doc(p)
        if isinstance(report,dict):
            candidates.append(report)
    return candidates


def find_form(data,base,now):
    """Accept only form reports that can be replayed against their input file."""
    source=json_doc(data/"form"/"features"/f"{base['draw_number']}.json")
    if source is None:
        return None
    eligible=[]
    for report in archived_reports(data,"form_model",base["draw_number"]):
        try:
            created=instant(report["created_at_utc"])
            if not instant(base["observed_at_utc"])<=created<instant(base["reg_close_time"]):
                continue
            personal=derive_solo(base,generated=created)
            if (report.get("source_snapshot_sha256")==base.get("source_snapshot_sha256")
                and report.get("source_observed_at_utc")==base["observed_at_utc"]
                and validate_form(report,base,personal,source)):
                eligible.append((created,report))
        except (KeyError,TypeError,ValueError,OverflowError,ZeroDivisionError):
            pass
    return min(eligible,key=lambda e:e[0])[1] if eligible else None


def find_player(data,base):
    """Only source-bound, preclose reports reconstructed from their full feed.

    Do not import retrospective provider records from historical tests.
    """
    feed=json_doc(data/"player_feed"/f"{base['draw_number']}.json")
    report=json_doc(data/"player_impact"/f"{base['draw_number']}.json")
    if not isinstance(feed,dict) or not isinstance(report,dict):
        return None
    try:
        created=instant(report["created_at_utc"])
        obtained=instant(feed["collected_at_utc"])
        if not (instant(base["observed_at_utc"])<=obtained<=created
                <instant(base["reg_close_time"])):
            return None
        if (report.get("source_snapshot_sha256")!=base.get("source_snapshot_sha256")
            or feed.get("source_snapshot_sha256")!=base.get("source_snapshot_sha256")
            or report.get("source_observed_at_utc")!=base["observed_at_utc"]
            or feed.get("source_observed_at_utc")!=base["observed_at_utc"]):
            return None
        recreated=build_player(base,feed,created=created)
        if recreated["matches"]!=report.get("matches"):
            return None
        return report
    except (KeyError,TypeError,ValueError,OverflowError,ZeroDivisionError):
        return None


def find_value(data,base):
    candidates=[]
    for report in archived_reports(data,"pool_value",base["draw_number"]):
        try:
            created=instant(report["created_at_utc"])
            if not instant(base["observed_at_utc"])<=created<instant(base["reg_close_time"]):
                continue
            if (report.get("source_snapshot_sha256")!=base.get("source_snapshot_sha256")
                or report.get("observed_at_utc")!=base["observed_at_utc"]):
                continue
            solo=derive_solo(base,generated=created)
            if validate_value(report,base,solo):
                candidates.append((created,report))
        except (KeyError,TypeError,ValueError,OverflowError,ZeroDivisionError):
            pass
    return min(candidates,key=lambda e:e[0])[1] if candidates else None


def paired_rows(base,scenario,outcome,selected):
    out=[]
    for i in selected:
        b=score(base["matches"][i]["p"],outcome[i])
        s=score(scenario[i],outcome[i])
        out.append({"index":i,"base":b,"adjusted":s})
    return out


def rows_from_model(base,report,field,required_flag=None):
    if len(report.get("matches",[]))!=13:
        return None,None
    selected=[]
    probs=[]
    for i,(orig,entry) in enumerate(zip(base["matches"],report["matches"])):
        if (entry.get("number")!=orig["number"] or entry.get("home")!=orig["home"]
            or entry.get("away")!=orig["away"] or entry.get("market_p")!=orig["p"]):
            return None,None
        p=entry.get(field)
        used=(required_flag is None or entry.get(required_flag) is True)
        if p is None:
            probs.append(orig["p"])
        elif valid_p(p):
            probs.append(p)
            if used:
                selected.append(i)
        else:
            return None,None
    return probs,selected


def payout_systems(choices_a,choices_b,cost,outcome,payouts):
    if (type(cost) is not int or cost<1 or cost>1800 or
        len(choices_a)!=13 or len(choices_b)!=13):
        return None
    for choices in (choices_a,choices_b):
        if (not all(type(v) is str and
                v in ("1","X","2","1X","12","X2","1X2") for v in choices)
            or math.prod(len(v) for v in choices)!=cost):
            return None
    left=correct_rows(choices_a,outcome)
    right=correct_rows(choices_b,outcome)
    def paid(rows):
        return sum(rows[k]*payouts[str(k)] for k in (10,11,12,13))
    return {"cost":cost,
            "base_paid":round(paid(left),2),"adjusted_paid":round(paid(right),2),
            "base_10plus":int(any(left[k] for k in (10,11,12,13))),
            "adjusted_10plus":int(any(right[k] for k in (10,11,12,13))),
            "base_13":int(left[13]>0),"adjusted_13":int(right[13]>0),
            "changed":sum(a!=b for a,b in zip(choices_a,choices_b))}


def choose_report(data,draw,now):
    snapshot=pick_locked_snapshot(data,draw,now)
    if snapshot is None:
        return None
    official=json_doc(data/"results"/f"{draw}.json")
    if not isinstance(official,dict):
        return None
    try:
        close=instant(snapshot["reg_close_time"])
        if not valid_result(official,{draw:close},now):
            return None
        base=create_analysis(snapshot)  # replay; no mutable old odds provenance
        return snapshot,base,official
    except (ValueError,KeyError,TypeError,OverflowError,ZeroDivisionError):
        return None


def block_ci(match_rows,seed=19019,iterations=1500):
    """Paired draw-block bootstrap; one draw sampled as a unit."""
    by_draw=defaultdict(list)
    for r in match_rows:
        by_draw[r["draw"]].append(r["base"]["brier"]-r["adjusted"]["brier"])
    draws=sorted(by_draw)
    if len(draws)<5:
        return None
    rng=random.Random(seed)
    values=[]
    for _ in range(iterations):
        sampled=[by_draw[rng.choice(draws)] for _ in draws]
        flat=[x for block in sampled for x in block]
        values.append(sum(flat)/len(flat))
    values.sort()
    return [round(values[int(.025*iterations)],7),
            round(values[min(iterations-1,int(.975*iterations))],7)]


def classify(rows,systems):
    """Promotable = enough PROSPECTIVE independent evidence, including holdout.

    No automated model activation even when promotable; additional manual
    evaluation and provider rights are still required.
    """
    n=len(rows)
    draws=len({r["draw"] for r in rows})
    if not n:
        return "otillräckligt underlag",False,None
    gain=sum(r["base"]["brier"]-r["adjusted"]["brier"] for r in rows)/n
    ci=block_ci(rows)
    if draws<EVALUATION_DRAW_MIN or n<EVALUATION_MATCH_MIN:
        label=("lovande men osäkert" if gain>0 else "ingen påvisad förbättring")
        return label,False,ci
    drawn=sorted({r["draw"] for r in rows})
    holdout=set(drawn[len(drawn)*2//3:])
    held=[r for r in rows if r["draw"] in holdout]
    holdout_gain=sum(r["base"]["brier"]-r["adjusted"]["brier"] for r in held)/len(held)
    log_gain=sum(r["base"]["logloss"]-r["adjusted"]["logloss"] for r in rows)/n
    credible=(gain>=MIN_BRIER_GAIN and log_gain>0 and ci is not None
              and ci[0]>0 and holdout_gain>0 and
              len(holdout)>=10)
    return ("tillräckligt stöd för manuell prövning" if credible else
            "osäker eller ingen förbättring"),credible,ci


def aggregate_factor(name,rows,systems):
    status,eligible,ci=classify(rows,systems)
    n=len(rows)
    draws=len({r["draw"] for r in rows})
    mean=lambda model,metric:round(
        sum(r[model][metric] for r in rows)/n,6) if n else None
    out={"factor":name,"label":FACTOR_NAMES[name],
         "status":status,"eligible_for_review":eligible,
         "matched_draws":draws,"matched_matches":n,
         "baseline_brier":mean("base","brier"),
         "factor_brier":mean("adjusted","brier"),
         "baseline_logloss":mean("base","logloss"),
         "factor_logloss":mean("adjusted","logloss"),
         "baseline_top1":mean("base","top1"),
         "factor_top1":mean("adjusted","top1"),
         "brier_gain_ci95":ci,
         "system_rounds":len({s["draw"] for s in systems}),
         "system_deltas":{}}
    for budget in (100,1800):
        entries=[s["system"] for s in systems if s["budget"]==budget]
        out["system_deltas"][str(budget)]={
            "rounds":len(entries),
            "changed_systems":sum(e["changed"]>0 for e in entries),
            "baseline_10plus":sum(e["base_10plus"] for e in entries),
            "factor_10plus":sum(e["adjusted_10plus"] for e in entries),
            "baseline_13":sum(e["base_13"] for e in entries),
            "factor_13":sum(e["adjusted_13"] for e in entries),
            "total_net_difference":round(sum(e["adjusted_paid"]-e["base_paid"]
                                             for e in entries),2)
        }
    return out


def evaluate(data,now=None):
    now=now or datetime.now(timezone.utc)
    collected=defaultdict(list)
    system_rows=defaultdict(list)
    counts={"frozen_draws_with_result":0,
            "draws_with_form_inputs":0,
            "draws_with_player_inputs":0,
            "draws_with_value_inputs":0}
    draws=sorted({int(p.stem) for p in (data/"results").glob("*.json")
                  if p.stem.isdigit()})
    for draw in draws:
        pair=choose_report(data,draw,now)
        if pair is None:
            continue
        snapshot,base,result=pair
        counts["frozen_draws_with_result"]+=1
        outcome=result["outcome"]; payout=result["payouts"]
        sources={"form":find_form(data,base,now),
                 "player":find_player(data,base),
                 "value":find_value(data,base)}
        for typ in ("form","player","value"):
            report=sources[typ]
            if report is None:
                continue
            counts["draws_with_"+typ+"_inputs"]+=1
            if typ=="form":
                probs,selected=rows_from_model(base,report,"form_p","used_form")
                proposals=report.get("budgets",[])
                if probs is None:continue
                for row in paired_rows(base,probs,outcome,selected):
                    collected[typ].append({"draw":draw,**row})
                for x in proposals:
                    sys=payout_systems(x["original_choices"],x["new_choices"],
                                       x["cost"],outcome,payout)
                    if sys and x["budget_limit"] in (100,1800):
                        system_rows[typ].append({"draw":draw,"budget":x["budget_limit"],"system":sys})
            elif typ=="player":
                probs,selected=rows_from_model(base,report,"scenario_p")
                if probs is None:continue
                for row in paired_rows(base,probs,outcome,selected):
                    collected[typ].append({"draw":draw,**row})
                for x in report.get("systems",[]):
                    sys=payout_systems(x["source_market_choices"],
                                       x["player_scenario_choices"],
                                       x["cost"],outcome,payout)
                    if sys and x["budget_limit"] in (100,1800):
                        system_rows[typ].append({"draw":draw,"budget":x["budget_limit"],"system":sys})
            else:
                for x in report.get("budget_proposals",[]):
                    sys=payout_systems(x["baseline_choices"],x["value_choices"],
                                       x["cost"],outcome,payout)
                    if sys and x["budget_limit"] in (100,1800):
                        system_rows[typ].append({"draw":draw,"budget":x["budget_limit"],"system":sys})
    form=aggregate_factor("form",collected["form"],system_rows["form"])
    player=aggregate_factor("player",collected["player"],system_rows["player"])
    value=aggregate_factor("value",[],system_rows["value"])
    value["status"]=("endast experimentella systemjämförelser" if
                     value["system_rounds"] else "otillräckligt underlag")
    return {"schema":SCHEMA,"generated_at_utc":now.isoformat(),
            "source_rule":"Latest verified market snapshot at least 30 minutes before draw close",
            "period_rule":"All model outputs must have been generated before close, from exactly the selected market snapshot",
            "factors":[form,player,value],
            "coverage":counts,
            "policy":{"min_draws_for_review":EVALUATION_DRAW_MIN,
                      "min_matches_for_review":EVALUATION_MATCH_MIN,
                      "min_brier_gain_for_review":MIN_BRIER_GAIN,
                      "holdout":"last third of independently observed draw numbers, >=10 draws",
                      "auto_apply_to_systems":False},
            "warnings":[
                "Resultatbaserade historiska Elo-tester ingår inte som marknadsbaserad förhandsvalidering.",
                "Streckvärde är en systemvalsheuristik, inte en alternativ 1/X/2-sannolikhetsmodell.",
                "Retrospektiva skaderapporter från API-Football utan verifierad förhandstid ingår inte.",
                "Resultat/utdelning redovisar hypotetiska system med lika radkostnad, aldrig garanterad lönsamhet."
            ]}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--outdir",default="data")
    args=ap.parse_args()
    out=Path(args.outdir)
    result=evaluate(out)
    target=out/"v19"/"evidence.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("V19: verifierade förhandsomgångar med facit:",
          result["coverage"]["frozen_draws_with_result"])
    for row in result["factors"]:
        print("V19:",row["factor"],"matcher:",row["matched_matches"],
              "kuponger:",row["matched_draws"],"status:",row["status"])


if __name__=="__main__":
    main()
