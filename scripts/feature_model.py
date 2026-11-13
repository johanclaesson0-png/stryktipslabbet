#!/usr/bin/env python3
"""Version 14: frozen *experimental* football-form forecast vs market baseline.

Pre-registered conservative adjustment; NOT fit to 2021-26 results.
Only pre-close source snapshots and form reports whose games predate source
observation are eligible. Original market systems remain unchanged.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

from scripts.analyze import correct_rows, evaluate_probability, valid_analysis
from scripts.solo import validate as valid_personal
from scripts.collect import write_json
from scripts.publish import instant, valid_result

SCHEMA = "stryktipslabbet-form-model-v1"
SETTLEMENT = "stryktipslabbet-form-model-settlement-v1"
MODEL = "form-overlay-preregistered-2026-11-13-v14"
WEIGHT = .25  # log-weight form correction, fixed before seeing new results
SIGNS = "1X2"


def clip(value, lo, hi):
    return max(lo, min(hi, value))


def form_adjustment(odds_p, home, away):
    """Returns original p when either side's last-five sample is inadequate.

    Does not claim learned coefficients or positive financial expectation.
    """
    prior = [float(x) for x in odds_p]
    for x in prior:
        if not math.isfinite(x) or x <= 0 or x >= 1:
            raise ValueError("Ogiltig sannolikhet")
    if abs(sum(prior)-1) > 1e-4:
        raise ValueError("Sannolikhetsmassa saknas")
    h5, a5 = home["last5"], away["last5"]
    n = min(h5["n"], a5["n"])
    if n < 3:
        return prior, 0.0, False, "Otillräckligt jämförbar formdata"
    def ppg(x):
        return x["points_per_game"] if x["n"] >= 3 and x["points_per_game"] is not None else None
    def goal_difference(x):
        if x["n"] < 3 or x["goals_for_per_game"] is None or x["goals_against_per_game"] is None:
            return None
        return x["goals_for_per_game"] - x["goals_against_per_game"]
    base5 = (ppg(h5) - ppg(a5)) / 3.0
    h10, a10 = ppg(home["last10"]), ppg(away["last10"])
    base10 = ((h10-a10)/3.0) if h10 is not None and a10 is not None else base5
    hvenue, avenue = ppg(home["venue5"]), ppg(away["venue5"])
    base_venue = ((hvenue-avenue)/3.0) if hvenue is not None and avenue is not None else base5
    hg, ag = goal_difference(h5), goal_difference(a5)
    base_goals = clip((hg-ag)/3, -1, 1) if hg is not None and ag is not None else 0.0
    signal = clip(.4*base5 + .2*base10 + .2*base_venue + .2*base_goals, -1, 1)
    reliability = clip(n / 5, .6, 1.0)
    delta = WEIGHT * signal * reliability
    weighted = [
        prior[0] * math.exp(delta),
        prior[1] * math.exp(-.12*abs(delta)),
        prior[2] * math.exp(-delta),
    ]
    total = sum(weighted)
    revised = [round(x/total, 9) for x in weighted]
    # Preserve exact total (within float arithmetic), avoid display rounding drift
    revised[1] = round(1.0-revised[0]-revised[2], 9)
    if not all(0 < p < 1 for p in revised):
        raise ValueError("Korrigerad sannolikhet ogiltig")
    reason = ("Hemmaform starkare än bortaform" if signal > .025 else
              "Bortaform starkare än hemmaform" if signal < -.025 else
              "Liknande form hos lagen")
    return revised, round(signal, 6), True, reason


def optimize_exact(ps, required_rows):
    """Maximize full-cover probability, keeping the baseline's EXACT cost."""
    if len(ps) != 13 or not 1 <= required_rows <= 1800:
        raise ValueError("13 matcher och rimlig radkostnad krävs")
    dp = {1: (0.0, ())}
    for p in ps:
        nxt = {}
        for existing, (score, choices) in dp.items():
            for mask in range(1, 8):
                rows = existing * mask.bit_count()
                if rows > required_rows or required_rows % rows:
                    continue
                mass = sum(p[j] for j in range(3) if mask & (1<<j))
                proposal = (score + math.log(mass), choices+(mask,))
                if rows not in nxt or proposal[0] > nxt[rows][0]:
                    nxt[rows] = proposal
        dp = nxt
        if not dp:
            raise ValueError("Exakt budget kan inte konstrueras")
    if required_rows not in dp:
        raise ValueError("Ouppnåelig radkostnad")
    return dp[required_rows][1]


def form_digest(form):
    payload = json.dumps(form, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def source_ok(base, personal, form, when):
    if not valid_analysis(base, when) or not valid_personal(personal, base):
        return False
    try:
        observed, close, ftime = (instant(base["observed_at_utc"]),
                                   instant(base["reg_close_time"]),
                                   instant(form["created_at_utc"]))
        if not observed <= ftime <= when < close:
            return False
        if (form.get("schema") != "stryktipslabbet-team-form-v1"
            or form["draw_number"] != base["draw_number"]
            or form["source_observed_at_utc"] != base["observed_at_utc"]
            or form["reg_close_time"] != base["reg_close_time"]
            or form.get("source_snapshot_sha256") != base.get("source_snapshot_sha256")
            or form["cutoff_date_exclusive"] != observed.date().isoformat()
            or len(form["matches"]) != 13):
            return False
        for m, original in zip(form["matches"], base["matches"]):
            if (m["number"] != original["number"] or m["home"] != original["home"] or
                m["away"] != original["away"] or m["market_p"] != original["p"]):
                return False
            if not all(isinstance(m[k], dict) for k in ("home_form", "away_form")):
                return False
        return True
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def build(base, personal, form, created=None):
    now = created or datetime.now(timezone.utc)
    if not source_ok(base, personal, form, now):
        raise ValueError("Modellen kräver tidsfryst förhandskupong och lagform")
    matches, all_p = [], []
    for row, f in zip(base["matches"], form["matches"]):
        improved, signal, applied, why = form_adjustment(row["p"], f["home_form"], f["away_form"])
        all_p.append(improved)
        matches.append({
            "number": row["number"], "home": row["home"], "away": row["away"],
            "market_p": row["p"][:], "form_p": improved,
            "delta_pp": [round(100*(improved[i]-row["p"][i]), 2) for i in range(3)],
            "data_coverage": f["coverage"],
            "used_form": applied, "form_signal": signal, "reason": why,
            "home_last5_ppg": f["home_form"]["last5"]["points_per_game"],
            "away_last5_ppg": f["away_form"]["last5"]["points_per_game"],
        })
    proposals = []
    for limit, baseline, prob_key in (
        (100, personal["systems"][0], "probability_all_13"),
        (1800, base["systems"][0], "p13_estimate"),
    ):
        cost = baseline["cost"]
        masks = optimize_exact(all_p, cost)
        selected = ["".join(SIGNS[j] for j in range(3) if mask & (1<<j)) for mask in masks]
        proposals.append({
            "budget_limit": limit, "cost": cost,
            "original_choices": baseline["choices"],
            "new_choices": selected,
            "original_market_p13": baseline[prob_key],
            "new_form_p13": round(evaluate_probability(masks, all_p), 9),
            "new_market_baseline_p13": round(evaluate_probability(masks, [m["p"] for m in base["matches"]]), 9),
            "different_matches": sum(a != b for a,b in zip(baseline["choices"],selected)),
        })
    return {
        "schema": SCHEMA, "model_version": MODEL, "weight": WEIGHT,
        "draw_number": base["draw_number"],
        "source_observed_at_utc": base["observed_at_utc"],
        "source_snapshot_sha256": base.get("source_snapshot_sha256"),
        "form_created_at_utc": form["created_at_utc"],
        "form_sha256": form_digest(form),
        "reg_close_time": base["reg_close_time"],
        "created_at_utc": now.isoformat(),
        "matches_with_form": sum(x["used_form"] for x in matches),
        "matches": matches, "budgets": proposals,
        "warning": ("Otestad kombination av förhandsodds och form. "
                    "Värdena är inte kalibrerade och ingen vinstökning är bevisad."),
    }


def validate(report, base, personal, form):
    try:
        if report.get("schema") != SCHEMA or report.get("model_version") != MODEL:
            return False
        return report == build(base, personal, form, created=instant(report["created_at_utc"]))
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return False


def settle(report, official):
    if report.get("schema") != SCHEMA:
        raise ValueError("Saknar säker förhandsmodell")
    close = instant(report["reg_close_time"])
    if instant(report["created_at_utc"]) >= close:
        raise ValueError("För sen modellrapport")
    if not valid_result(official, {report["draw_number"]:close}, instant(official["observed_at_utc"])):
        raise ValueError("Endast verifierat officiellt resultat")
    outcomes = official["outcome"]
    summary = {"market_brier_sum":0., "form_brier_sum":0.,
               "market_log_loss_sum":0., "form_log_loss_sum":0.,
               "market_top_correct":0, "form_top_correct":0}
    for i, sign in enumerate(outcomes):
        actual = SIGNS.index(sign)
        for label, key in (("market","market_p"),("form","form_p")):
            ps = report["matches"][i][key]
            summary[label+"_brier_sum"] += sum((ps[j]-(j==actual))**2 for j in range(3))
            summary[label+"_log_loss_sum"] -= math.log(max(ps[actual], 1e-12))
            summary[label+"_top_correct"] += int(max(range(3), key=lambda j:ps[j])==actual)
    def result_for(choices, cost):
        dist = correct_rows(choices, outcomes)
        winnings = sum(dist[n]*official["payouts"][str(n)] for n in (10,11,12,13))
        return {
            "cost": cost, "covered_matches": sum(s in c for c,s in zip(choices,outcomes)),
            "row_counts": {str(n):dist[n] for n in (10,11,12,13)},
            "paid": round(winnings, 2), "net": round(winnings-cost, 2),
        }
    budgets = []
    for b in report["budgets"]:
        budgets.append({
            "budget_limit": b["budget_limit"],
            "market_system": result_for(b["original_choices"],b["cost"]),
            "form_system": result_for(b["new_choices"],b["cost"]),
        })
    return {
        "schema": SETTLEMENT, "model_version": MODEL,
        "draw_number": report["draw_number"],
        "source_observed_at_utc": report["source_observed_at_utc"],
        "report_created_at_utc": report["created_at_utc"],
        "form_sha256": report["form_sha256"],
        "source_snapshot_sha256": report.get("source_snapshot_sha256"),
        "official_result_sha256": official.get("sha256"),
        "outcome": outcomes, "payouts": official["payouts"],
        "n": 13, "forecast_scores": {k:round(v, 8) for k,v in summary.items()},
        "budgets": budgets, "hypothetical": True,
        "caution": "Ej uppdelat på lottade matcher; modellens prognosfördel ej säkerställd.",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--outdir",default="data")
    args = p.parse_args()
    root = Path(args.outdir)
    now = datetime.now(timezone.utc)
    built=settled=0
    for file in sorted((root/"analysis").glob("*.json")):
        try:
            base=json.loads(file.read_text(encoding="utf-8"))
            if now >= instant(base["reg_close_time"]):
                continue
            solo_file=root/"personal"/file.name
            form_file=root/"form"/"features"/file.name
            if not solo_file.exists() or not form_file.exists():
                continue
            solo=json.loads(solo_file.read_text(encoding="utf-8"))
            form=json.loads(form_file.read_text(encoding="utf-8"))
            dest=root/"form_model"/file.name
            if dest.exists():
                old=json.loads(dest.read_text(encoding="utf-8"))
                if (old.get("source_observed_at_utc")==base["observed_at_utc"]
                    and old.get("form_sha256")==form_digest(form)
                    and validate(old,base,solo,form)):
                    continue
                hist=root/"form_model_history"/str(base["draw_number"])/(
                    old["source_observed_at_utc"].replace(":","_")+"-"+
                    old["form_sha256"][:12]+".json")
                if not hist.exists():
                    write_json(hist,old)
            current=build(base,solo,form,created=now)
            if not validate(current,base,solo,form):
                raise ValueError("Validering av v14 misslyckades")
            write_json(dest,current)
            built+=1
        except (OSError,KeyError,ValueError,TypeError,json.JSONDecodeError) as e:
            print("Formmodellen hoppades över:",file,str(e),file=sys.stderr)
    for file in sorted((root/"results").glob("*.json")):
        try:
            out=root/"form_model_settlements"/file.name
            source=root/"form_model"/file.name
            basefile=root/"analysis"/file.name
            solo_file=root/"personal"/file.name
            form_file=root/"form"/"features"/file.name
            if out.exists() or not all(p.exists() for p in (source,basefile,solo_file,form_file)):
                continue
            report=json.loads(source.read_text(encoding="utf-8"))
            base=json.loads(basefile.read_text(encoding="utf-8"))
            solo=json.loads(solo_file.read_text(encoding="utf-8"))
            form=json.loads(form_file.read_text(encoding="utf-8"))
            if not validate(report,base,solo,form):
                continue
            result=json.loads(file.read_text(encoding="utf-8"))
            write_json(out,settle(report,result))
            settled+=1
        except (OSError,KeyError,ValueError,TypeError,json.JSONDecodeError) as e:
            print("Formmodell-rättning hoppades över:",file,str(e),file=sys.stderr)
    print("Nya frysta formexperiment:",built,"| rättade:",settled)


if __name__=="__main__":
    main()
