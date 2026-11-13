#!/usr/bin/env python3
"""Spikvakt v1: prospective, versioned decision support, never outcome-informed.

Risk threshold and X bonus are FIXED *before* evaluating future draws.
The two experiments use the SAME exact number of lines as the baseline.
They are NOT demonstrated to outperform odds-only selection or earn profit.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

from scripts.analyze import valid_analysis, correct_rows, evaluate_probability
from scripts.solo import validate as valid_solo
from scripts.collect import write_json
from scripts.publish import instant, valid_result

SCHEMA = "stryktipslabbet-spikvakt-v1"
SETTLED = "stryktipslabbet-spikvakt-settlement-v1"
VERSION = "spikvakt-fixed-2026-11-13-v1"
SIGNS = "1X2"
SPIKE_LIMIT = .55
DRAW_LIMIT = .27
SAFE_PENALTY = .85
DRAW_BONUS = .90


def exact_cost_optimizer(p, target, mode):
    """Solve globally for the best objective under EXACTLY the baseline cost."""
    if len(p) != 13 or mode not in ("safe", "draw"):
        raise ValueError("Ogiltig kupong eller optimering")
    if target < 1 or target > 1800:
        raise ValueError("Ogiltig radkostnad")
    dp = {1: (0.0, ())}
    for probs in p:
        nxt = {}
        for rows, (score, previous) in dp.items():
            for mask in range(1, 8):
                width = mask.bit_count()
                new_rows = rows * width
                if new_rows > target or target % new_rows:
                    continue
                mass = sum(probs[j] for j in range(3) if mask & (1 << j))
                candidate_score = score + math.log(mass)
                if mode == "safe" and width == 1:
                    chosen = next(j for j in range(3) if mask & (1 << j))
                    candidate_score -= SAFE_PENALTY * max(0.0, SPIKE_LIMIT - probs[chosen])
                elif mode == "draw" and mask & 2:
                    candidate_score += DRAW_BONUS * max(0.0, probs[1] - DRAW_LIMIT)
                val = (candidate_score, previous + (mask,))
                if new_rows not in nxt or val[0] > nxt[new_rows][0]:
                    nxt[new_rows] = val
        dp = nxt
        if not dp:
            raise ValueError("Ingen möjlighet att bilda ett system")
    if target not in dp:
        raise ValueError("Exakt radantal går inte att använda")
    return dp[target][1]


def signs_to_masks(choices):
    return tuple(sum(1 << SIGNS.index(s) for s in c) for c in choices)


def risk_report(choices, matches):
    flagged, x_candidates = [], []
    for i, (c, match) in enumerate(zip(choices, matches)):
        probs = match["p"]
        if len(c) == 1:
            p = probs[SIGNS.index(c)]
            suggested = max((j for j in range(3) if SIGNS[j] not in c),
                            key=lambda j: probs[j])
            flagged.append({
                "number": i + 1,
                "home": match["home"], "away": match["away"],
                "chosen": c,
                "estimated_miss_probability": round(1 - p, 6),
                "high_risk": p < SPIKE_LIMIT,
                "suggested_second_sign": SIGNS[suggested],
                "extra_outcome_probability": round(probs[suggested], 6),
                "cost_if_added_without_rebalancing": math.prod(len(x) for x in choices) * 2,
            })
        if "X" not in c and probs[1] >= DRAW_LIMIT:
            new_cost = math.prod(len(x) for x in choices) * (len(c) + 1) // len(c)
            x_candidates.append({
                "number": i + 1,
                "home": match["home"], "away": match["away"],
                "x_probability": round(probs[1], 6),
                "extra_row_cost_to_include_x_alone": new_cost,
                "requires_rebalancing": True,
            })
    flagged.sort(key=lambda m: m["estimated_miss_probability"], reverse=True)
    x_candidates.sort(key=lambda m: m["x_probability"], reverse=True)
    return {"spikes": flagged, "possible_draws": x_candidates}


def build(original, solo, created=None):
    now = created or datetime.now(timezone.utc)
    observed, close = instant(original["observed_at_utc"]), instant(original["reg_close_time"])
    if not valid_analysis(original, now) or not valid_solo(solo, original):
        raise ValueError("Ogiltiga förhandsobservationer")
    if now >= close or now < observed:
        raise ValueError("Spikvakt får endast skapas före spelstopp och efter observation")
    matches = original["matches"]
    p = [m["p"] for m in matches]
    proposals = []
    for budget, baseline, prob_field in (
        (1800, original["systems"][0], "p13_estimate"),
        (100, solo["systems"][0], "probability_all_13"),
    ):
        cost = baseline["cost"]
        if not 1 <= cost <= budget:
            raise ValueError("Budget saknas")
        options = []
        for key, label in (
            ("safe", "Färre osäkra spikar (test)"),
            ("draw", "Titta extra på kryss (test)"),
        ):
            masks = exact_cost_optimizer(p, cost, key)
            choices = ["".join(SIGNS[j] for j in range(3) if mask & (1 << j))
                       for mask in masks]
            options.append({
                "key": key, "name": label, "cost": cost,
                "choices": choices,
                "estimated_p13": round(evaluate_probability(masks, p), 9),
                "miss_risk_spikes": sum(1 for c, probs in zip(choices, p)
                                          if len(c) == 1 and probs[SIGNS.index(c)] < SPIKE_LIMIT),
                "x_included": sum("X" in c for c in choices)
            })
        report = risk_report(baseline["choices"], matches)
        proposals.append({
            "budget": budget, "baseline_cost": cost,
            "baseline_choices": baseline["choices"],
            "baseline_p13": baseline[prob_field],
            "baseline_miss_risk_spikes": sum(1 for c, probs in zip(baseline["choices"], p)
                                                if len(c) == 1 and probs[SIGNS.index(c)] < SPIKE_LIMIT),
            "baseline_x_included": sum("X" in c for c in baseline["choices"]),
            "risk_report": report,
            "experiments": options
        })
    return {
        "schema": SCHEMA, "version": VERSION,
        "draw_number": original["draw_number"],
        "source_observed_at_utc": original["observed_at_utc"],
        "reg_close_time": original["reg_close_time"],
        "source_snapshot_sha256": original.get("source_snapshot_sha256"),
        "created_at_utc": now.isoformat(),
        "spike_threshold": SPIKE_LIMIT,
        "x_threshold": DRAW_LIMIT,
        "safe_penalty": SAFE_PENALTY,
        "draw_bonus": DRAW_BONUS,
        "budgets": proposals,
        "disclaimer": "Experiment på förhandsodds, inte tränad förbättring eller påvisat spelvärde."
    }


def validate(report, original, solo):
    try:
        when = instant(report["created_at_utc"])
        if report.get("schema") != SCHEMA or report.get("version") != VERSION:
            return False
        if report["draw_number"] != original["draw_number"]:
            return False
        if report["source_observed_at_utc"] != original["observed_at_utc"]:
            return False
        if report.get("source_snapshot_sha256") != original.get("source_snapshot_sha256"):
            return False
        if report["reg_close_time"] != original["reg_close_time"]:
            return False
        if report["spike_threshold"] != SPIKE_LIMIT or report["x_threshold"] != DRAW_LIMIT:
            return False
        if report["safe_penalty"] != SAFE_PENALTY or report["draw_bonus"] != DRAW_BONUS:
            return False
        rebuilt = build(original, solo, created=when)
        return report == rebuilt
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return False


def settle(report, result):
    if report.get("schema") != SCHEMA or instant(report["created_at_utc"]) >= instant(report["reg_close_time"]):
        raise ValueError("Beslutsstödet måste vara fryst före spelstopp")
    close, observed = instant(report["reg_close_time"]), instant(result["observed_at_utc"])
    if not valid_result(result, {report["draw_number"]: close}, observed):
        raise ValueError("Ej validerat facit")
    def settle_system(choices):
        counts = correct_rows(choices, result["outcome"])
        paid = sum(counts[i] * result["payouts"][str(i)] for i in (10, 11, 12, 13))
        return {
            "covered_matches": sum(actual in c for actual, c in zip(result["outcome"], choices)),
            "rows_by_correct": {str(i): counts[i] for i in (10, 11, 12, 13)},
            "paid": round(paid, 2),
        }
    budgets = []
    for group in report["budgets"]:
        baseline = settle_system(group["baseline_choices"])
        baseline["net"] = round(baseline["paid"] - group["baseline_cost"], 2)
        tested = []
        for experiment in group["experiments"]:
            val = settle_system(experiment["choices"])
            tested.append({
                "key": experiment["key"],
                "cost": experiment["cost"],
                **val,
                "net": round(val["paid"] - experiment["cost"], 2),
            })
        budgets.append({"budget": group["budget"], "baseline": baseline, "experiments": tested})
    return {
        "schema": SETTLED, "version": VERSION,
        "draw_number": report["draw_number"],
        "source_observed_at_utc": report["source_observed_at_utc"],
        "report_created_at_utc": report["created_at_utc"],
        "source_snapshot_sha256": report.get("source_snapshot_sha256"),
        "result_sha256": result.get("sha256"),
        "result_outcome": result["outcome"],
        "hypothetical": True,
        "budgets": budgets,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data")
    args = ap.parse_args()
    data = Path(args.outdir)
    created = settled_count = 0
    now = datetime.now(timezone.utc)
    for file in sorted((data / "analysis").glob("*.json")):
        try:
            original = json.loads(file.read_text(encoding="utf-8"))
            solo_file = data / "personal" / file.name
            if not solo_file.exists():
                continue
            solo = json.loads(solo_file.read_text(encoding="utf-8"))
            out = data / "spikvakt" / file.name
            # No retroactive construction. No substitution of a newer snapshot
            # for an older frozen experiment after game close.
            if now >= instant(original["reg_close_time"]):
                continue
            if out.exists():
                old = json.loads(out.read_text(encoding="utf-8"))
                if (old.get("source_observed_at_utc") == original["observed_at_utc"]
                        and validate(old, original, solo)):
                    continue
            obj = build(original, solo, created=now)
            if not validate(obj, original, solo):
                raise ValueError("Ny analys misslyckades validering")
            if out.exists():
                previous = json.loads(out.read_text(encoding="utf-8"))
                hist = data / "spikvakt_history" / str(original["draw_number"]) / (
                    previous["source_observed_at_utc"].replace(":", "_") + ".json")
                if not hist.exists():
                    write_json(hist, previous)
            write_json(out, obj)
            created += 1
        except (ValueError, KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
            print("Spikvakt hoppade över:", file, str(exc), file=sys.stderr)
    for file in sorted((data / "results").glob("*.json")):
        try:
            dest = data / "spikvakt_settlements" / file.name
            report_file = data / "spikvakt" / file.name
            base_file = data / "analysis" / file.name
            solo_file = data / "personal" / file.name
            if dest.exists() or not all(p.exists() for p in (report_file, base_file, solo_file)):
                continue
            report = json.loads(report_file.read_text(encoding="utf-8"))
            base = json.loads(base_file.read_text(encoding="utf-8"))
            solo = json.loads(solo_file.read_text(encoding="utf-8"))
            result = json.loads(file.read_text(encoding="utf-8"))
            if not validate(report, base, solo):
                continue
            write_json(dest, settle(report, result))
            settled_count += 1
        except (ValueError, KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
            print("Spikvakt-rättning hoppades över:", file, str(exc), file=sys.stderr)
    print("Frysta Spikvakt-rapporter:", created, "| rättade:", settled_count)


if __name__ == "__main__":
    main()
