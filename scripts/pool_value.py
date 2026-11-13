#!/usr/bin/env python3
"""V15: outcome probabilities vs estimated crowd concentration, no fake payout EV.

Only saved odds and streck from the SAME pre-close Stryktipset draw.
'Popularity' is the independent-streck probability mass of rows in a system.
It is neither the actual number of winners nor expected payout.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from scripts.analyze import valid_analysis, evaluate_probability, selected_signs, correct_rows
from scripts.solo import validate as validate_solo
from scripts.feature_model import optimize_exact
from scripts.publish import instant, valid_result
from scripts.collect import write_json

SCHEMA = "stryktipslabbet-pool-value-v15"
SETTLED = "stryktipslabbet-pool-value-settlement-v15"
VERSION = "relative-pool-value-2026-11-14-v1"
SIGNS = "1X2"
CROWD_EXPONENT = 0.45
MIN_CROWD = 0.035


def crowd_distribution(match):
    raw = match["streck"]
    if len(raw) != 3 or not 98.9 <= sum(raw) <= 101.1:
        raise ValueError("Ogiltiga folktecken")
    return [x/sum(raw) for x in raw]


def profile_probs(p, crowd):
    raw = [p[j] * (p[j]/max(crowd[j], MIN_CROWD))**CROWD_EXPONENT
           for j in range(3)]
    total = sum(raw)
    return [v/total for v in raw]


def masses(choices, matches):
    market = crowd = 1.
    if len(choices) != 13:
        raise ValueError("Kupongen kräver 13 matcher")
    for selected, m in zip(choices, matches):
        if not selected or any(c not in SIGNS for c in selected):
            raise ValueError("Felaktigt tecken")
        p, s = m["p"], crowd_distribution(m)
        market *= sum(p[SIGNS.index(v)] for v in selected)
        crowd *= sum(s[SIGNS.index(v)] for v in selected)
    return round(market, 12), round(crowd, 12)


def build(base, solo, created=None):
    now = created or datetime.now(timezone.utc)
    if not valid_analysis(base, now) or not validate_solo(solo, base):
        raise ValueError("Förhandskupongen är inte verifierad")
    if not instant(base["observed_at_utc"]) <= now < instant(base["reg_close_time"]):
        raise ValueError("Inga nya förslag efter spelstopp")
    matches = base["matches"]
    transformed = [profile_probs(m["p"], crowd_distribution(m)) for m in matches]
    scenarios = []
    for limit, baseline in ((100, solo["systems"][0]), (1800, base["systems"][0])):
        cost = baseline["cost"]
        masks = optimize_exact(transformed, cost)
        value_choices = [selected_signs(x) for x in masks]
        baseline_p, baseline_c = masses(baseline["choices"], matches)
        target_p, target_c = masses(value_choices, matches)
        scenarios.append({
            "budget_limit": limit,
            "cost": cost,
            "baseline_choices": baseline["choices"],
            "value_choices": value_choices,
            "changes": sum(a!=b for a,b in zip(baseline["choices"],value_choices)),
            "baseline": {
                "probability_cover_all_13": baseline_p,
                "modelled_crowd_cover_mass": baseline_c,
                "relative_concentration_ratio": round(baseline_p/max(baseline_c,1e-14),5)
            },
            "value": {
                "probability_cover_all_13": target_p,
                "modelled_crowd_cover_mass": target_c,
                "relative_concentration_ratio": round(target_p/max(target_c,1e-14),5)
            }
        })
    diagnostics = []
    for m in matches:
        crowd = crowd_distribution(m)
        diagnostics.append({
            "number": m["number"], "home": m["home"], "away": m["away"],
            "p_market": m["p"], "p_crowd": [round(x,8) for x in crowd],
            "market_minus_crowd_pp": [round(100*(m["p"][i]-crowd[i]),2) for i in range(3)],
            "relative_underbetting": [round(m["p"][i]/max(crowd[i], MIN_CROWD),3) for i in range(3)]
        })
    return {
        "schema": SCHEMA, "version": VERSION,
        "draw_number": base["draw_number"],
        "observed_at_utc": base["observed_at_utc"],
        "source_snapshot_sha256": base.get("source_snapshot_sha256"),
        "reg_close_time": base["reg_close_time"],
        "created_at_utc": now.isoformat(),
        "crowd_exponent": CROWD_EXPONENT,
        "budget_proposals": scenarios, "matches": diagnostics,
        "warnings": [
            "Jämförelsen P/st–crowd är en popularitetsindikator, INTE validerad förväntad avkastning.",
            "Streckmodellen antar oberoende mellan matcher; verkliga kupongrader är korrelerade.",
            "Omsättning, jackpot, antal vinnande rader och slutlig utdelning är okända före rättning.",
            "Ingen förändring av insatsgränser eller automatiskt spel."
        ]
    }


def validate(obj, base, solo):
    try:
        if obj.get("schema") != SCHEMA or obj.get("version") != VERSION:
            return False
        return obj == build(base, solo, created=instant(obj["created_at_utc"]))
    except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError):
        return False


def settle(report, official):
    close = instant(report["reg_close_time"])
    if report.get("schema") != SCHEMA or instant(report["created_at_utc"]) >= close:
        raise ValueError("Ofrysen prognos")
    if not valid_result(official, {report["draw_number"]:close}, instant(official["observed_at_utc"])):
        raise ValueError("Ogiltigt resultat")
    summary=[]
    for b in report["budget_proposals"]:
        systems=[]
        for typ, choices in (("baseline",b["baseline_choices"]),("value",b["value_choices"])):
            dist = correct_rows(choices, official["outcome"])
            paid = sum(dist[j]*official["payouts"][str(j)] for j in (10,11,12,13))
            systems.append({"key":typ,"cost":b["cost"],
                            "rows_by_correct":{str(j):dist[j] for j in (10,11,12,13)},
                            "paid":round(paid,2),"net":round(paid-b["cost"],2)})
        summary.append({"budget_limit":b["budget_limit"],"systems":systems})
    return {"schema":SETTLED,"version":VERSION,
            "draw_number":report["draw_number"],
            "source_snapshot_sha256":report.get("source_snapshot_sha256"),
            "report_created_at_utc":report["created_at_utc"],
            "official_result_sha256":official.get("sha256"),
            "outcome":official["outcome"],"payouts":official["payouts"],
            "hypothetical":True, "budget_results":summary}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--outdir",default="data")
    args=ap.parse_args()
    data=Path(args.outdir)
    now=datetime.now(timezone.utc)
    built=finished=0
    for path in sorted((data/"analysis").glob("*.json")):
        try:
            base=json.loads(path.read_text(encoding="utf-8"))
            if now>=instant(base["reg_close_time"]):
                continue
            solo=json.loads((data/"personal"/path.name).read_text(encoding="utf-8"))
            target=data/"pool_value"/path.name
            if target.exists():
                old=json.loads(target.read_text(encoding="utf-8"))
                if old.get("observed_at_utc")==base["observed_at_utc"] and validate(old,base,solo):
                    continue
                hist=data/"pool_value_history"/str(base["draw_number"])/(
                    old["observed_at_utc"].replace(":","_")+".json")
                if not hist.exists():
                    write_json(hist,old)
            new=build(base,solo,created=now)
            if not validate(new,base,solo):
                raise ValueError("Värdeanalysen kan inte valideras")
            write_json(target,new)
            built+=1
        except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError) as exc:
            print("V15 hoppades över:",path,str(exc),file=sys.stderr)
    for path in sorted((data/"results").glob("*.json")):
        try:
            target=data/"pool_value_settlements"/path.name
            if target.exists():continue
            base=json.loads((data/"analysis"/path.name).read_text(encoding="utf-8"))
            solo=json.loads((data/"personal"/path.name).read_text(encoding="utf-8"))
            report=json.loads((data/"pool_value"/path.name).read_text(encoding="utf-8"))
            if not validate(report,base,solo):continue
            official=json.loads(path.read_text(encoding="utf-8"))
            write_json(target,settle(report,official))
            finished+=1
        except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError) as exc:
            print("V15 rättning hoppades över:",path,str(exc),file=sys.stderr)
    print("V15 ny värdeanalys:",built,"rättad:",finished)


if __name__=="__main__":
    main()
