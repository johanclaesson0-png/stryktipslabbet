#!/usr/bin/env python3
"""Pre-close, market-odds Stryktipset system analysis and post-close settlement.

No model is trained on outcomes. P(1/X/2) comes solely from margin-normalized
odds actually observed *before* draw registration closed. Crowd is used only for
heuristic system selection. This is NOT a validated expected-return model.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

from scripts.collect import write_json
from scripts.publish import valid_snapshot, valid_result, instant

MODEL = "market-no-vig-v1"
SCHEMA = "stryktipslabbet-frozen-analysis-v1"
SETTLEMENT_SCHEMA = "stryktipslabbet-settlement-v1"
SIGNS = "1X2"
BUDGET = 1800
PROFILES = (
    ("balanserad", "Balanserad", 0.0),
    ("varde", "Streckvärde – experiment", 0.40),
    ("skrall", "Skräll – experiment", 0.85),
)


def probabilities(odds):
    raw = [1.0 / x for x in odds]
    total = sum(raw)
    return [v / total for v in raw]


def search_probabilities(model_p, crowd, exponent):
    """Use crowd only for heuristic system construction, NOT P(model)."""
    if not exponent:
        return model_p[:]
    weights = [
        p * (p / max(c, 0.035)) ** exponent
        for p, c in zip(model_p, crowd)
    ]
    total = sum(weights)
    return [w / total for w in weights]


def optimize(rows, budget=BUDGET):
    """Exact dynamic program over 13 matches and valid M-system row counts.

    Maximize sum of log P(allowed outcome on each match) under cost <= budget.
    Alternative profiles use transformed *selection scores*; true P(13) is
    always evaluated using the original margin-normalized market estimates.
    """
    if len(rows) != 13:
        raise ValueError("Exakt 13 matcher krävs")
    if not 1 <= budget <= 2000000:
        raise ValueError("Ogiltig budget")
    dp = {1: (0.0, ())}
    for row in rows:
        nxt = {}
        for cost, (score, choices) in dp.items():
            for mask in range(1, 8):
                count = mask.bit_count()
                new_cost = cost * count
                if new_cost > budget:
                    continue
                selection_prob = sum(row[j] for j in range(3) if mask & (1 << j))
                candidate = (score + math.log(selection_prob), choices + (mask,))
                if new_cost not in nxt or candidate[0] > nxt[new_cost][0]:
                    nxt[new_cost] = candidate
        if not nxt:
            raise ValueError("Inget möjligt matematiskt system")
        dp = nxt
    cost, (score, choices) = max(dp.items(), key=lambda item: item[1][0])
    return cost, choices


def selected_signs(mask):
    return "".join(SIGNS[i] for i in range(3) if mask & (1 << i))


def system_rows(choices):
    n = 1
    for mask in choices:
        n *= mask.bit_count()
    return n


def evaluate_probability(choices, probs):
    product = 1.0
    for mask, p in zip(choices, probs):
        product *= sum(p[j] for j in range(3) if mask & (1 << j))
    return product


def create_analysis(snapshot):
    observed = instant(snapshot["observed_at_utc"])
    close = instant(snapshot["reg_close_time"])
    if not valid_snapshot(snapshot, observed) or observed >= close:
        raise ValueError("Ingen giltig kupongobservation före spelstopp")
    ordered = sorted(snapshot["matches"], key=lambda m: m["number"])
    rows = []
    for m in ordered:
        market = probabilities(m["odds"])
        crowd = [float(x) / sum(m["streck"]) for x in m["streck"]]
        rows.append({
            "number": m["number"],
            "home": m["home"],
            "away": m["away"],
            "odds": m["odds"],
            "streck": m["streck"],
            "p": [round(v, 9) for v in market],
            "edge": [round(market[i] - crowd[i], 6) for i in range(3)]
        })
    profiles = []
    for key, label, exponent in PROFILES:
        scores = [search_probabilities(
            row["p"], [v / sum(row["streck"]) for v in row["streck"]], exponent
        ) for row in rows]
        cost, masks = optimize(scores)
        if cost != system_rows(masks) or cost > BUDGET:
            raise ValueError("Systemkostnaden är inkonsekvent")
        profiles.append({
            "key": key,
            "name": label,
            "selection_exponent": exponent,
            "cost": cost,
            "rows": cost,
            "choices": [selected_signs(mask) for mask in masks],
            "p13_estimate": round(evaluate_probability(masks, [r["p"] for r in rows]), 9),
            "spikes": sum(mask.bit_count() == 1 for mask in masks),
            "half": sum(mask.bit_count() == 2 for mask in masks),
            "full": sum(mask.bit_count() == 3 for mask in masks)
        })
    # SHA256 from the actual raw response, when present. All exported inputs
    # are frozen inside this object and never adjusted using match outcomes.
    return {
        "schema": SCHEMA,
        "model_version": MODEL,
        "draw_number": snapshot["draw_number"],
        "observed_at_utc": snapshot["observed_at_utc"],
        "reg_close_time": snapshot["reg_close_time"],
        "source": snapshot.get("source", "Svenska Spel"),
        "source_snapshot_sha256": snapshot.get("sha256"),
        "budget_limit": BUDGET,
        "p_definition": "1/odds normaliserat per match, inte validerad egen matchmodell",
        "system_profiles_note": "Streck- och skrällval är heuristiska experiment, inte bevisat värde eller förväntad avkastning.",
        "matches": rows,
        "systems": profiles,
    }


def valid_analysis(analysis, now):
    if not isinstance(analysis, dict) or analysis.get("schema") != SCHEMA or analysis.get("model_version") != MODEL:
        return False
    try:
        observed, close = instant(analysis["observed_at_utc"]), instant(analysis["reg_close_time"])
        if observed >= close or observed > now or type(analysis["draw_number"]) is not int:
            return False
        if analysis["budget_limit"] != BUDGET or len(analysis["matches"]) != 13:
            return False
        if [m["number"] for m in analysis["matches"]] != list(range(1, 14)):
            return False
        for m in analysis["matches"]:
            if not (isinstance(m["home"], str) and m["home"] and isinstance(m["away"], str) and m["away"]):
                return False
            if not (len(m["p"]) == 3 and all(type(p) in (float, int) and math.isfinite(p) and 0 < p < 1 for p in m["p"])):
                return False
            if abs(sum(m["p"]) - 1) > 0.0001:
                return False
        systems = analysis["systems"]
        if [s["key"] for s in systems] != [a[0] for a in PROFILES]:
            return False
        for s in systems:
            if type(s["cost"]) is not int or not (1 <= s["cost"] <= BUDGET):
                return False
            if len(s["choices"]) != 13 or any(
                not isinstance(c, str) or not c or "".join(x for x in SIGNS if x in c) != c
                for c in s["choices"]
            ):
                return False
            if s["cost"] != math.prod(len(c) for c in s["choices"]):
                return False
            if not (0 < s["p13_estimate"] <= 1):
                return False
        return True
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


def correct_rows(choices, outcome):
    """Exactly count the system's lines in 0..13 correct categories."""
    if len(choices) != 13 or len(outcome) != 13:
        raise ValueError("13 tecken krävs")
    dist = [1]
    for selected, real in zip(choices, outcome):
        size = len(selected)
        hit = real in selected
        nxt = [0] * (len(dist) + 1)
        for k, n in enumerate(dist):
            if hit:
                nxt[k + 1] += n
                nxt[k] += n * (size - 1)
            else:
                nxt[k] += n * size
        dist = nxt
    if sum(dist) != math.prod(len(c) for c in choices):
        raise ArithmeticError("Systemraderna summerar inte")
    return dist


def create_settlement(analysis, result):
    observed = instant(analysis["observed_at_utc"])
    if not valid_analysis(analysis, observed):
        raise ValueError("Prognos arkiverad efter spelstopp eller ogiltig")
    close = instant(analysis["reg_close_time"])
    if not valid_result(result, {analysis["draw_number"]: close}, instant(result["observed_at_utc"])):
        raise ValueError("Officiellt facit/utdelning är inte validerat")
    all_systems = []
    for s in analysis["systems"]:
        d = correct_rows(s["choices"], result["outcome"])
        payout = sum(d[k] * result["payouts"][str(k)] for k in (10, 11, 12, 13))
        all_systems.append({
            "key": s["key"],
            "name": s["name"],
            "cost": s["cost"],
            "correct_rows": {str(k): d[k] for k in (10, 11, 12, 13)},
            "paid": round(payout, 2),
            "net": round(payout - s["cost"], 2),
        })
    return {
        "schema": SETTLEMENT_SCHEMA,
        "draw_number": analysis["draw_number"],
        "forecast_observed_at_utc": analysis["observed_at_utc"],
        "result_observed_at_utc": result["observed_at_utc"],
        "source_snapshot_sha256": analysis.get("source_snapshot_sha256"),
        "official_result_sha256": result.get("sha256"),
        "outcome": result["outcome"],
        "payouts": result["payouts"],
        "systems": all_systems,
        "hypothetical": True,
        "note": "Rättat experiment: hypotetiska matematiska system, inga bekräftade spelade insatser."
    }


def analyze_all(data, now=None):
    """Idempotent, model-versioned, as-of correct forward analysis."""
    now = now or datetime.now(timezone.utc)
    created = 0
    for path in sorted((data / "snapshots").glob("*/*.json")):
        try:
            snap = json.loads(path.read_text(encoding="utf-8"))
            if not valid_snapshot(snap, now):
                continue
            n = snap["draw_number"]
            observed = instant(snap["observed_at_utc"])
            hist = data / "analysis_history" / str(n) / (path.stem + ".json")
            if not hist.exists():
                analysis = create_analysis(snap)
                if not valid_analysis(analysis, now):
                    raise ValueError("Validering av prognos misslyckades")
                write_json(hist, analysis)
                created += 1
            else:
                analysis = json.loads(hist.read_text(encoding="utf-8"))
                if not valid_analysis(analysis, now) or analysis["observed_at_utc"] != snap["observed_at_utc"]:
                    raise ValueError("Fryst historikpost har ändrats")
            latest = data / "analysis" / (str(n) + ".json")
            if latest.exists():
                previous = json.loads(latest.read_text(encoding="utf-8"))
                if instant(previous["observed_at_utc"]) >= observed:
                    continue
            write_json(latest, analysis)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            print("Prognos hoppades över:", path, str(exc), file=sys.stderr)
    return created


def settle_all(data, now=None):
    now = now or datetime.now(timezone.utc)
    settled = 0
    for result_file in sorted((data / "results").glob("*.json")):
        try:
            result = json.loads(result_file.read_text(encoding="utf-8"))
            n = result["draw_number"]
            source = data / "analysis" / (str(n) + ".json")
            dest = data / "settlements" / (str(n) + ".json")
            if dest.exists() or not source.exists():
                continue
            analysis = json.loads(source.read_text(encoding="utf-8"))
            close = instant(analysis["reg_close_time"])
            if not valid_result(result, {n: close}, now):
                continue
            payout = create_settlement(analysis, result)
            write_json(dest, payout)
            settled += 1
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            print("Rättning hoppades över:", result_file, str(exc), file=sys.stderr)
    return settled


def main():
    ap = argparse.ArgumentParser(description="Skapa tre frysta system per pre-close-snapshot")
    ap.add_argument("--outdir", default="data")
    args = ap.parse_args()
    data = Path(args.outdir)
    new = analyze_all(data)
    settled = settle_all(data)
    print("Nya frysta prognoser:", new, "nya officiella rättningar:", settled)


if __name__ == "__main__":
    main()
