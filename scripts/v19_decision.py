#!/usr/bin/env python3
"""V19: explainable Stryktipset decision studio, NEVER auto-submit or replace bets.

All suggestions are shadow comparisons from the SAME pre-close source snapshot.
Only independently evaluated and subsequently human-approved models can ever
be considered for promotion; this module does not implement such promotion.
Public output never includes API-Football-derived player records.
"""
import argparse
from datetime import datetime,timezone
import json
import math
from pathlib import Path

from scripts.analyze import create_analysis, evaluate_probability
from scripts.feature_model import validate as validate_form
from scripts.pool_value import validate as validate_pool
from scripts.solo import derive as derive_solo
from scripts.publish import instant, valid_snapshot
from scripts.v19_evaluation import json_doc

SCHEMA="stryktipslabbet-decision-studio-v19"
SIGNS="1X2"


def original_ok(snapshot,base,now):
    if not isinstance(snapshot,dict) or not isinstance(base,dict):
        return False
    try:
        if not valid_snapshot(snapshot,now):
            return False
        if (snapshot.get("sha256") != base.get("source_snapshot_sha256")
            or snapshot["observed_at_utc"] != base["observed_at_utc"]
            or snapshot["draw_number"] != base["draw_number"]
            or snapshot["reg_close_time"] != base["reg_close_time"]
            or instant(base["observed_at_utc"])>=instant(base["reg_close_time"])):
            return False
        regenerated=create_analysis(snapshot)
        return (base["matches"]==regenerated["matches"]
                and base["systems"]==regenerated["systems"])
    except (KeyError,TypeError,ValueError,OverflowError,ZeroDivisionError):
        return False


def assessment_from_evidence(evidence):
    if (not isinstance(evidence,dict) or
        evidence.get("schema")!="stryktipslabbet-evidence-gate-v19"):
        return {x:"otillräckligt underlag" for x in ("form","player","value")}
    result={}
    for x in evidence.get("factors",[]):
        if x.get("factor") in ("form","player","value"):
            result[x["factor"]]=x.get("status","otillräckligt underlag")
    return {k:result.get(k,"otillräckligt underlag") for k in ("form","player","value")}


def scenario_valid(model,base,solo,kind,now):
    if not isinstance(model,dict):
        return False
    try:
        created=instant(model["created_at_utc"])
        close=instant(base["reg_close_time"])
        if not instant(base["observed_at_utc"])<=created<=now<close:
            return False
        if model.get("source_snapshot_sha256")!=base.get("source_snapshot_sha256"):
            return False
        if model.get("draw_number")!=base["draw_number"]:
            return False
        if kind=="form":
            if (model.get("source_observed_at_utc")!=base["observed_at_utc"]
                or len(model.get("matches",[]))!=13):
                return False
            # Source form features are separately replay-validated by main().
            for m,r in zip(base["matches"],model["matches"]):
                if (m["number"]!=r.get("number") or m["home"]!=r.get("home")
                    or m["away"]!=r.get("away") or m["p"]!=r.get("market_p")):
                    return False
            return all(len(r["form_p"])==3 for r in model["matches"])
        if kind=="value":
            return (model.get("observed_at_utc")==base["observed_at_utc"]
                    and model.get("version")=="relative-pool-value-2026-11-14-v1")
        return False
    except (KeyError,TypeError,ValueError,OverflowError):
        return False


def safe_system_options(proposals,original,kind):
    """Only exactly same cost as original and canonical signs, no price upsell."""
    if not isinstance(proposals,list):
        return None
    records={}
    for row in proposals:
        try:
            budget=row["budget_limit"]
            baseline=original[budget]
            new=(row["new_choices"] if kind=="form" else row["value_choices"])
            orig=(row["original_choices"] if kind=="form" else row["baseline_choices"])
            cost=row["cost"]
            if (budget not in (100,1800) or orig!=baseline["choices"]
                or cost!=baseline["cost"] or len(new)!=13
                or not all(type(s) is str and s in ("1","X","2","1X","12","X2","1X2") for s in new)
                or math.prod(len(s) for s in new)!=cost):
                return None
            records[budget]=new
        except (KeyError,TypeError,ValueError):
            return None
    return records if set(records)=={100,1800} else None


def build(base,snapshot,personal,now,evidence=None,form=None,value=None):
    if not original_ok(snapshot,base,now):
        raise ValueError("Beslutsmotorn kräver verifierad tidsfryst oddskälla")
    if now>=instant(base["reg_close_time"]):
        raise ValueError("Ingen ny beslutsanalys efter spelstopp")
    rebuilt=derive_solo(base,generated=now)
    if not isinstance(personal,dict) or personal.get("systems")!=rebuilt["systems"]:
        raise ValueError("Personliga system matchar inte oddsursprunget")
    original={
        100:personal["systems"][0],1800:base["systems"][0]
    }
    scenarios={}
    valid_form_report=scenario_valid(form,base,personal,"form",now)
    valid_value_report=scenario_valid(value,base,personal,"value",now)
    if valid_form_report:
        opts=safe_system_options(form.get("budgets",[]),original,"form")
        if opts:scenarios["form"]=opts
    if valid_value_report:
        opts=safe_system_options(value.get("budget_proposals",[]),original,"value")
        if opts:scenarios["value"]=opts
    evidence_status=assessment_from_evidence(evidence)
    matches=[]
    for i,m in enumerate(base["matches"]):
        odds=m["p"]
        raw=m["streck"]
        crowd=[x/sum(raw) for x in raw]
        top=max(range(3),key=lambda k:odds[k])
        edge=[100*(odds[j]-crowd[j]) for j in range(3)]
        form_shift=(
            [100*(form["matches"][i]["form_p"][j]-odds[j]) for j in range(3)]
            if "form" in scenarios and form["matches"][i].get("used_form") is True
            else [0.,0.,0.]
        )
        # Signed market crowd edge is only relative popularity, not payout EV.
        # Prioritize review when crowd and market disagree or a shadow system
        # changes an existing sign. Never call this an expected profit.
        current={str(k):original[k]["choices"][i] for k in (100,1800)}
        alternatives={
            typ:{str(k):opt[k][i] for k in (100,1800)}
            for typ,opt in scenarios.items()
        }
        changes=sum(opt[str(k)]!=current[str(k)]
                    for opt in alternatives.values() for k in (100,1800))
        discrepancy=max(abs(v) for v in edge)
        form_delta=max(abs(v) for v in form_shift)
        priority=round(discrepancy+.4*form_delta+changes*2.5,2)
        note=(
            "Marknad och folket skiljer sig tydligt; granska spiken/garderingen."
            if discrepancy>=8 else
            "Experimenten väljer andra tecken – jämför, men byt inte automatiskt."
            if changes else "Inga stora skillnader mellan tillgängliga analyser."
        )
        matches.append({
            "number":m["number"],"home":m["home"],"away":m["away"],
            "market_p":[round(p,6) for p in odds],
            "crowd_p":[round(p,6) for p in crowd],
            "market_minus_crowd_pp":[round(x,2) for x in edge],
            "form_delta_pp":[round(x,2) for x in form_shift],
            "most_likely_sign":SIGNS[top],
            "market_favourite_prob_pct":round(100*odds[top],1),
            "baseline_choices":current,
            "experimental_choices":alternatives,
            "review_priority":priority,
            "explanation":note,
        })
    matches.sort(key=lambda r:r["number"])
    proposals=[]
    for budget in (100,1800):
        baseline=original[budget]
        choices=baseline["choices"]
        block={"budget":budget,"cost":baseline["cost"],
               "baseline_choices":choices,
               "experiments":[]}
        for typ,selected in scenarios.items():
            proposal=selected[budget]
            original_mass=round(
                evaluate_probability([sum(1<<SIGNS.index(c) for c in sign) for sign in choices],
                                     [m["p"] for m in base["matches"]]),9)
            proposal_mass=round(
                evaluate_probability([sum(1<<SIGNS.index(c) for c in sign) for sign in proposal],
                                     [m["p"] for m in base["matches"]]),9)
            block["experiments"].append({
                "factor":typ,"title":("Formscenario" if typ=="form" else "Streckvärdescenario"),
                "status":evidence_status[typ],
                "choices":proposal,
                "changes":sum(a!=b for a,b in zip(choices,proposal)),
                "same_cost":True,
                "market_probability_baseline":original_mass,
                "market_probability_experiment":proposal_mass,
                "activated":False})
        proposals.append(block)
    return {
        "schema":SCHEMA,
        "draw_number":base["draw_number"],
        "observed_at_utc":base["observed_at_utc"],
        "reg_close_time":base["reg_close_time"],
        "source_snapshot_sha256":base.get("source_snapshot_sha256"),
        "created_at_utc":now.isoformat(),
        "status":"förhandsfryst – experimentella alternativ, ingen automatisk ändring",
        "models_available":sorted(scenarios),
        "factor_evidence":evidence_status,
        "matches":matches,"systems":proposals,
        "review_order":[r["number"] for r in sorted(
            matches,key=lambda r:(-r["review_priority"],r["number"]))],
        "warnings":[
            "Streck−marknad i procentenheter är inte verifierat vinstvärde.",
            "Alla alternativ har exakt samma radkostnad som originalsystemet.",
            "En förbättrad sannolikhet är inte bevis på högre utdelning.",
            "API-spelardata publiceras inte och påverkar inte några system.",
            "Inget system lämnas in eller ersätts automatiskt."
        ]}


def latest_snapshot(data,base,now):
    for p in sorted((data/"snapshots"/str(base["draw_number"])).glob("*.json"),reverse=True):
        snap=json_doc(p)
        if (isinstance(snap,dict) and
            snap.get("observed_at_utc")==base.get("observed_at_utc")
            and snap.get("sha256")==base.get("source_snapshot_sha256")
            and original_ok(snap,base,now)):
            return snap
    return None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--outdir",default="data")
    args=parser.parse_args()
    data=Path(args.outdir)
    now=datetime.now(timezone.utc)
    evidence=json_doc(data/"v19"/"evidence.json")
    latest={}
    for p in sorted((data/"analysis").glob("*.json"),reverse=True):
        base=json_doc(p)
        if not isinstance(base,dict):
            continue
        try:
            if now>=instant(base["reg_close_time"]):
                continue
            raw=latest_snapshot(data,base,now)
            if raw is None:continue
            personal=json_doc(data/"personal"/p.name)
            if personal is None:continue
            form=json_doc(data/"form_model"/p.name)
            source=json_doc(data/"form"/"features"/p.name)
            if form is not None:
                try:
                    from scripts.feature_model import validate as form_validate
                    if source is None or not form_validate(
                        form,base,personal,source):
                        form=None
                except (KeyError,TypeError,ValueError,OverflowError):
                    form=None
            value=json_doc(data/"pool_value"/p.name)
            if value is not None:
                try:
                    if not validate_pool(value,base,personal):
                        value=None
                except (KeyError,TypeError,ValueError,OverflowError):
                    value=None
            decision=build(base,raw,personal,now,evidence,form,value)
            latest=decision
            break
        except (KeyError,TypeError,ValueError,OverflowError,ZeroDivisionError):
            continue
    # No invented live probability if the draw is closed/unavailable.
    if not latest:
        latest={"schema":SCHEMA,"status":"Ingen verifierad öppen kupong",
                "created_at_utc":now.isoformat(),"matches":[],"systems":[],
                "review_order":[],"models_available":[]}
    target=data/"v19"/"decision.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(latest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("V19:",latest["status"],"matcher:",len(latest["matches"]),
          "jämförelsemodeller:",len(latest["models_available"]))


if __name__=="__main__":
    main()
