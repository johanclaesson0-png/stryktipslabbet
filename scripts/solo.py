#!/usr/bin/env python3
"""Independent, frozen personal Stryktipset proposals (maximum 100 kr).

Always derived from an already frozen *pre-close* odds observation. Never uses
results when selecting signs. This model has not been validated for profit.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys
from scripts.analyze import (
    MODEL, PROFILES, SCHEMA as ANALYSIS_SCHEMA, probabilities,
    search_probabilities, optimize, selected_signs,
    evaluate_probability, correct_rows, valid_analysis
)
from scripts.collect import write_json
from scripts.publish import instant, valid_result

SCHEMA = "stryktipslabbet-personal-100-v1"
SETTLEMENT = "stryktipslabbet-personal-settlement-v1"
BUDGET = 100


def derive(a, generated=None):
    observed = instant(a["observed_at_utc"])
    if not valid_analysis(a, observed):
        raise ValueError("Ogiltig eller icke-fryst prognos")
    created = generated or datetime.now(timezone.utc)
    p = [m["p"][:] for m in a["matches"]]
    crowd = [[v / sum(m["streck"]) for v in m["streck"]] for m in a["matches"]]
    systems = []
    for name, label, exponent in PROFILES:
        score = [search_probabilities(row, c, exponent) for row, c in zip(p, crowd)]
        cost, masks = optimize(score, BUDGET)
        systems.append({
            "key": name,
            "name": label,
            "cost": cost,
            "rows": cost,
            "choices": [selected_signs(mask) for mask in masks],
            "probability_all_13": round(evaluate_probability(masks, p), 9),
            "singles": sum(mask.bit_count() == 1 for mask in masks),
            "doubles": sum(mask.bit_count() == 2 for mask in masks),
            "triples": sum(mask.bit_count() == 3 for mask in masks),
        })
    return {
        "schema": SCHEMA,
        "draw_number": a["draw_number"],
        "model_version": MODEL,
        "original_observed_at_utc": a["observed_at_utc"],
        "reg_close_time": a["reg_close_time"],
        "created_at_utc": created.isoformat(),
        "derived_before_close": created < instant(a["reg_close_time"]),
        "source_snapshot_sha256": a.get("source_snapshot_sha256"),
        "max_budget": BUDGET,
        "note": "Hypotetiska system; sannolikheter bygger på normaliserade odds, ingen bekräftad överavkastning.",
        "systems": systems,
    }


def validate(personal, original):
    try:
        if not isinstance(personal, dict) or personal.get("schema") != SCHEMA:
            return False
        if personal["draw_number"] != original["draw_number"]:
            return False
        if personal["original_observed_at_utc"] != original["observed_at_utc"]:
            return False
        if personal["reg_close_time"] != original["reg_close_time"]:
            return False
        if personal.get("source_snapshot_sha256") != original.get("source_snapshot_sha256"):
            return False
        if personal["max_budget"] != BUDGET or personal["model_version"] != MODEL:
            return False
        if len(personal["systems"]) != 3:
            return False
        for (key, _, _), s in zip(PROFILES, personal["systems"]):
            if s["key"] != key or len(s["choices"]) != 13:
                return False
            if any(not c or any(x not in "1X2" for x in c) or len(set(c)) != len(c) for c in s["choices"]):
                return False
            cost = 1
            for c in s["choices"]:
                cost *= len(c)
            if not (cost == s["cost"] == s["rows"] and cost <= BUDGET):
                return False
            prob = 1.0
            for m, c in zip(original["matches"], s["choices"]):
                prob *= sum(m["p"]["1X2".index(x)] for x in c)
            if abs(prob - s["probability_all_13"]) > 1e-6:
                return False
        return True
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def settle(personal, result):
    close = instant(personal["reg_close_time"])
    now = instant(result["observed_at_utc"])
    if not valid_result(result, {personal["draw_number"]: close}, now):
        raise ValueError("Officiellt facit har inte validerats")
    calculated = []
    for s in personal["systems"]:
        dist = correct_rows(s["choices"], result["outcome"])
        winnings = sum(dist[n] * result["payouts"][str(n)] for n in (10, 11, 12, 13))
        calculated.append({
            "key": s["key"], "name": s["name"], "cost": s["cost"],
            "count_by_correct": {str(n): dist[n] for n in (10, 11, 12, 13)},
            "paid": round(winnings, 2),
            "net": round(winnings - s["cost"], 2)
        })
    return {
        "schema": SETTLEMENT,
        "draw_number": personal["draw_number"],
        "source_observed_at_utc": personal["original_observed_at_utc"],
        "source_snapshot_sha256": personal.get("source_snapshot_sha256"),
        "result_sha256": result.get("sha256"),
        "outcome": result["outcome"], "payouts": result["payouts"],
        "hypothetical": True, "systems": calculated
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--outdir", default="data")
    args = p.parse_args()
    data = Path(args.outdir)
    created = settled = 0
    for path in sorted((data / "analysis").glob("*.json")):
        try:
            original = json.loads(path.read_text(encoding="utf-8"))
            if not valid_analysis(original, datetime.now(timezone.utc)):
                continue
            target = data / "personal" / path.name
            if target.exists():
                previous = json.loads(target.read_text(encoding="utf-8"))
                if previous["original_observed_at_utc"] == original["observed_at_utc"] and validate(previous, original):
                    continue
            current = derive(original)
            if not validate(current, original):
                raise ValueError("Ny personanalys validerades inte")
            # Only upgrade latest observation; preserve historical artifact versions
            old = target if target.exists() else None
            if old:
                previous = json.loads(old.read_text(encoding="utf-8"))
                hist = data / "personal_history" / str(original["draw_number"]) / (previous["original_observed_at_utc"].replace(":", "_")+".json")
                if not hist.exists():
                    write_json(hist, previous)
            write_json(target, current)
            created += 1
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print("Eget system hoppades över", path, str(exc), file=sys.stderr)
    for path in sorted((data / "results").glob("*.json")):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            target = data / "personal_settlements" / path.name
            orig_file = data / "analysis" / path.name
            solo_file = data / "personal" / path.name
            if target.exists() or not orig_file.exists() or not solo_file.exists():
                continue
            original = json.loads(orig_file.read_text(encoding="utf-8"))
            personal = json.loads(solo_file.read_text(encoding="utf-8"))
            if not validate(personal, original):
                continue
            result_data = settle(personal, result)
            write_json(target, result_data)
            settled += 1
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print("Rättning av eget system hoppades över", path, str(exc), file=sys.stderr)
    print("Personliga 100-kronorssystem:", created, "| nya rättningar:", settled)


if __name__ == "__main__":
    main()
