#!/usr/bin/env python3
"""V18 market-vs-player prospective audit: require REAL frozen pre-close odds.

Old result-only archives cannot be backfilled with modern odds. This evaluator
only compares frozen market snapshots (provably timestamped before close) to
timestamped player reports created before close, after the official settlement
has been received. Never uses results to construct a prior forecast.
"""
from collections import Counter
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path

from scripts.analyze import valid_analysis, correct_rows
from scripts.player_impact import build as build_player, REPORT_SCHEMA
from scripts.publish import instant, valid_result, valid_snapshot

ROOT=Path(__file__).resolve().parents[1]
SIGNS="1X2"


def match_score(prob,outcome):
    y=SIGNS.index(outcome)
    if (len(prob)!=3 or any(type(p) not in (int,float) or p<=0 or p>=1
        or not math.isfinite(p) for p in prob) or abs(sum(prob)-1)>0.0001):
        raise ValueError("Ogiltig sannolikhetsprognos")
    return (sum((p-int(i==y))**2 for i,p in enumerate(prob)), -math.log(prob[y]))


def evaluate_verified_pair(analysis, snapshot, feed, report, result):
    """Return validated, leakage-free paired performance or explicit rejection."""
    try:
        frozen=instant(analysis["observed_at_utc"])
        close=instant(analysis["reg_close_time"])
        created=instant(report["created_at_utc"])
        fetched=instant(feed["collected_at_utc"])
        if not frozen<=fetched<=created<close:
            return None,"Spelaruppgift inte observerad efter odds och före spelstopp"
        if (feed.get("source_snapshot_sha256")!=analysis.get("source_snapshot_sha256")
            or feed.get("source_observed_at_utc")!=analysis.get("observed_at_utc")
            or feed.get("draw_number")!=analysis.get("draw_number")
            or report.get("source_snapshot_sha256")!=analysis.get("source_snapshot_sha256")
            or report.get("source_observed_at_utc")!=analysis.get("observed_at_utc")):
            return None,"Spelardata har inte exakt samma tidsfrysta oddsursprung"
        if not valid_snapshot(snapshot,created):
            return None,"Den frysta odds- och streckkällan är ogiltig"
        if (snapshot.get("observed_at_utc")!=analysis["observed_at_utc"]
            or snapshot.get("sha256")!=analysis.get("source_snapshot_sha256")
            or snapshot.get("draw_number")!=analysis.get("draw_number")):
            return None,"Prognosen saknar verifierad ursprungssnapshot"
        if not valid_analysis(analysis,created):
            return None,"Ogiltig tidsfryst originalanalys"
        for a,s in zip(analysis["matches"],sorted(snapshot["matches"],key=lambda m:m["number"])):
            if (a["number"]!=s["number"] or a["home"]!=s["home"]
                or a["away"]!=s["away"] or a["odds"]!=s["odds"]
                or a["streck"]!=s["streck"]):
                return None,"Odds/streck stämmer inte med råsnapshot"
        rebuilt=build_player(analysis,feed,created=created)
        if report.get("schema")!=REPORT_SCHEMA or rebuilt["matches"]!=report.get("matches"):
            return None,"Spelarrapport kunde inte verifieras eller rekonstrueras"
        if not valid_result(result,{analysis["draw_number"]:close},
                            datetime.now(timezone.utc)):
            return None,"Inget giltigt officiellt resultat efter spelstopp"
        rows=[]
        for m,player,y in zip(analysis["matches"],report["matches"],result["outcome"]):
            scen=player["scenario_p"]
            if scen is None:
                continue
            b,lb=match_score(m["p"],y)
            a,la=match_score(scen,y)
            rows.append({"market_brier":b,"player_brier":a,
                         "market_logloss":lb,"player_logloss":la,
                         "market_top1":int(SIGNS[max(range(3),key=lambda i:m["p"][i])]==y),
                         "player_top1":int(SIGNS[max(range(3),key=lambda i:scen[i])]==y)})
        if not rows:
            return None,"Inga verifierade spelarobservationer i den avslutade kupongen"
        systems=[]
        for s in report.get("systems",[]):
            original=s["source_market_choices"]
            revised=s["player_scenario_choices"]
            if (len(original)!=13 or len(revised)!=13 or
                math.prod(len(x) for x in original)!=s["cost"] or
                math.prod(len(x) for x in revised)!=s["cost"]):
                return None,"Systemen har olika radkostnad"
            dist0=correct_rows(original,result["outcome"])
            dist1=correct_rows(revised,result["outcome"])
            systems.append({"budget":s["budget_limit"],"cost":s["cost"],
                            "original_hits":{str(k):int(dist0[k]>0) for k in (10,11,12,13)},
                            "player_hits":{str(k):int(dist1[k]>0) for k in (10,11,12,13)}})
        return {"draw":analysis["draw_number"],"matches":len(rows),
                "market_brier":sum(r["market_brier"] for r in rows),
                "player_brier":sum(r["player_brier"] for r in rows),
                "market_logloss":sum(r["market_logloss"] for r in rows),
                "player_logloss":sum(r["player_logloss"] for r in rows),
                "market_top1":sum(r["market_top1"] for r in rows),
                "player_top1":sum(r["player_top1"] for r in rows),
                "systems":systems},None
    except (ValueError,KeyError,TypeError,OverflowError,IndexError,AttributeError):
        return None,"Indata saknas eller tidsstämplar kan inte valideras"


def audit(root=ROOT):
    """Missing feeds/results stay explicitly unavailable, not fake zero scores."""
    data=root/"data"
    report={"schema":"stryktipslabbet-verified-market-player-audit-v18",
            "generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "frozen_market_draws":0,"with_official_settlement":0,
            "with_verifiable_preclose_player_feed":0,
            "evaluated_draws":0,"evaluated_matches":0,
            "brier_market":None,"brier_player":None,
            "logloss_market":None,"logloss_player":None,
            "systems":[],"status":"Ingen godkänd parvis jämförelse ännu"}
    completed=[]
    seen=set()
    for p in sorted((data/"analysis").glob("*.json")):
        try:
            a=json.loads(p.read_text(encoding="utf-8"))
            draw=a["draw_number"]
            if draw in seen:
                continue
            seen.add(draw)
            observed=instant(a["observed_at_utc"])
            close=instant(a["reg_close_time"])
            if not valid_analysis(a,observed) or observed>=close:
                continue
            report["frozen_market_draws"]+=1
            result_p=data/"results"/f"{draw}.json"
            if not result_p.exists():continue
            res=json.loads(result_p.read_text(encoding="utf-8"))
            if not valid_result(res,{draw:close},datetime.now(timezone.utc)):continue
            report["with_official_settlement"]+=1
            feed_p=data/"player_feed"/f"{draw}.json"
            player_p=data/"player_impact"/f"{draw}.json"
            if not feed_p.exists() or not player_p.exists():continue
            source=None
            for snap_path in (data/"snapshots"/str(draw)).glob("*.json"):
                candidate=json.loads(snap_path.read_text(encoding="utf-8"))
                if candidate.get("observed_at_utc")==a["observed_at_utc"]:
                    source=candidate;break
            if source is None:continue
            feed=json.loads(feed_p.read_text(encoding="utf-8"))
            player=json.loads(player_p.read_text(encoding="utf-8"))
            performance,why=evaluate_verified_pair(a,source,feed,player,res)
            if performance:
                report["with_verifiable_preclose_player_feed"]+=1
                completed.append(performance)
        except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
            continue
    if completed:
        n=sum(x["matches"] for x in completed)
        report["evaluated_draws"]=len(completed)
        report["evaluated_matches"]=n
        for name in ("market_brier","player_brier","market_logloss","player_logloss"):
            report[("brier_" if "brier" in name else "logloss_")+
                   ("market" if "market" in name else "player")]=round(
                       sum(x[name] for x in completed)/n,6)
        report["systems"]=[x for row in completed for x in row["systems"]]
        report["status"]="Giltig förhandsfryst observation och utfall; ingen kausal effekt bevisad"
    return report


if __name__=="__main__":
    result=audit()
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    destination=os.getenv("MARKET_AUDIT_OUTPUT")
    if destination:
        p=Path(destination)
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
