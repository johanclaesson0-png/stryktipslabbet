#!/usr/bin/env python3
"""Version 17: source-bound, strictly pre-close experimental player availability.

This is a separate probability/system scenario, NEVER a replacement for the
market, form, or pool-value models. The estimated effect is an uncalibrated
sensitivity analysis; absence is usually already partly priced into odds.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

from scripts.analyze import valid_analysis
from scripts.collect import write_json
from scripts.feature_model import optimize_exact
from scripts.analyze import selected_signs
from scripts.player_availability import verify_report
from scripts.publish import instant
from scripts.solo import validate as validate_solo

SCHEMA = "stryktipslabbet-player-factor-v17"
MODEL = "experimental-player-sensitivity-2026-11-14-v1"
SIGNS = "1X2"
STRENGTH = 0.19
MAX_SIDE = 1.35


def importance(record):
    """0..1 bounded participation proxy, NOT estimated player on/off xG."""
    if record.get("verified_by") != "api_football":
        return None
    s = record.get("stats")
    if not isinstance(s, dict) or s.get("complete") is not True:
        return None
    try:
        starts = float(s["starts"])
        apps = float(s["appearances"])
        minutes = float(s["minutes"])
        games = float(s["team_matches"])
        goals = float(s.get("goals") or 0)
        assists = float(s.get("assists") or 0)
        if not (3 <= games <= 80 and 0 <= starts <= apps <= games + 3
                and 0 <= minutes <= games * 100 + 300
                and 0 <= goals <= 60 and 0 <= assists <= 40):
            return None
        usage = min(1.0, starts / games)
        load = min(1.0, minutes / (90 * games))
        production = min(1.0, (goals + 0.65 * assists) / games * 2)
        value = 0.68 * usage + 0.22 * load + 0.10 * production
        return round(min(1.0, max(0.0, value)), 5)
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        return None


def adjusted(p, delta):
    if len(p) != 3 or any(not isinstance(x, (int,float)) or
                          not math.isfinite(x) or x <= 0 for x in p):
        raise ValueError("Felaktiga marknadssannolikheter")
    if abs(sum(p) - 1) > 0.0001:
        raise ValueError("Sannolikheter måste summera till ett")
    w = [p[0] * math.exp(delta), p[1] * math.exp(-0.08 * abs(delta)),
         p[2] * math.exp(-delta)]
    z = sum(w)
    result = [round(w[0] / z, 9), 0, round(w[2] / z, 9)]
    result[1] = round(1 - result[0] - result[2], 9)
    return result


def source_ok(base, availability, personal, created):
    try:
        obs = instant(base["observed_at_utc"])
        ac = instant(availability["created_at_utc"])
        close = instant(base["reg_close_time"])
        if not (valid_analysis(base, created) and validate_solo(personal, base)
                and obs <= ac <= created < close):
            return False
        if (availability.get("schema") != "stryktipslabbet-player-availability-v1"
                or availability["draw_number"] != base["draw_number"]
                or availability["source_observed_at_utc"] != base["observed_at_utc"]
                or availability.get("source_snapshot_sha256") != base.get("source_snapshot_sha256")
                or len(availability["matches"]) != len(base["matches"])):
            return False
        for report, match in zip(availability["matches"], base["matches"]):
            if report["number"] != match["number"]:
                return False
            for side in ("home", "away"):
                team = report[side]
                if team["team"] != match[side]:
                    return False
                for entry in team["reported_absences"]:
                    if not verify_report(entry, obs):
                        return False
                    if entry.get("match_number",match["number"]) != match["number"]:
                        return False
        return True
    except (TypeError, ValueError, KeyError, OverflowError):
        return False


def build(base, availability, personal, created=None):
    now = created or datetime.now(timezone.utc)
    if not source_ok(base, availability, personal, now):
        raise ValueError("Spelarstatus måste vara verifierad och bunden till samma förhandskupong")
    output, probs = [], []
    used = 0
    for old, item in zip(base["matches"], availability["matches"]):
        losses = {}
        for side in ("home", "away"):
            seen = set()
            ranked = []
            for r in item[side]["reported_absences"]:
                key = (r.get("provider_player_id") or r["player"]).__str__().casefold()
                if key in seen:
                    continue
                seen.add(key)
                score = importance(r)
                # Only a provider-observed, source-bound absence with complete
                # season data changes this hypothetical scenario.
                factor = {"out": 1.0, "suspended": 1.0, "doubtful": 0.40}[r["status"]]
                weight = round(score * factor, 5) if score is not None else 0.0
                if weight > 0:
                    used += 1
                ranked.append({"player": r["player"], "status": r["status"],
                               "source": r["publisher"], "source_url": r["source_url"],
                               "observed_at_utc": r["checked_at_utc"],
                               "importance": score, "weight": weight,
                               "position": (r.get("stats") or {}).get("position"),
                               "data_quality": "season_sample" if score is not None else "unknown"})
            ranked.sort(key=lambda x: (-x["weight"], x["player"]))
            losses[side] = {"players": ranked,
                            "total_weight": round(min(MAX_SIDE,sum(x["weight"] for x in ranked)),5)}
        delta = round(STRENGTH * (losses["away"]["total_weight"] -
                                  losses["home"]["total_weight"]), 7)
        new_p = adjusted(old["p"], delta)
        probs.append(new_p)
        output.append({"number": old["number"], "home": old["home"], "away": old["away"],
                       "market_p": old["p"], "player_p": new_p,
                       "delta_pp": [round(100*(a-b),2) for a,b in zip(new_p,old["p"])],
                       "home": old["home"], "away": old["away"],
                       "home_players": losses["home"]["players"],
                       "away_players": losses["away"]["players"],
                       "strength_delta": delta,
                       "coverage": "experiment" if abs(delta)>1e-9 else "ingen kvantifierad effekt"})
    systems=[]
    for limit, baseline in ((100, personal["systems"][0]), (1800, base["systems"][0])):
        cost = baseline["cost"]
        masks = optimize_exact(probs, cost)
        choices = [selected_signs(mask) for mask in masks]
        systems.append({"budget_limit": limit, "cost":cost,
                        "original_choices": baseline["choices"],
                        "player_choices": choices,
                        "changed_matches": sum(a!=b for a,b in zip(baseline["choices"],choices)),
                        "player_probability_cover_all": round(math.prod(
                            sum(p[SIGNS.index(ch)] for ch in choice)
                            for p,choice in zip(probs,choices)),9)})
    return {"schema": SCHEMA,"model_version": MODEL,
            "draw_number": base["draw_number"],
            "source_observed_at_utc":base["observed_at_utc"],
            "source_snapshot_sha256":base.get("source_snapshot_sha256"),
            "reg_close_time":base["reg_close_time"],
            "availability_created_at_utc":availability["created_at_utc"],
            "created_at_utc":now.isoformat(),
            "source_type":"API-Football or human-reviewed evidence; only complete API stats quantified",
            "used_player_count":used,"matches":output,"systems":systems,
            "assumption":"Scenario om frånvaron INTE redan är inprisad. Varken effektstorlek eller förbättring är validerad.",
            "main_models_unchanged":True}


def validate(obj, base, availability, personal):
    try:
        if obj.get("schema") != SCHEMA or obj.get("model_version") != MODEL:
            return False
        return obj == build(base, availability, personal, created=instant(obj["created_at_utc"]))
    except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError):
        return False


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--outdir",default="data")
    root=Path(ap.parse_args().outdir)
    now=datetime.now(timezone.utc)
    saved=0
    for path in sorted((root/"analysis").glob("*.json")):
        try:
            base=json.loads(path.read_text(encoding="utf-8"))
            if not instant(base["observed_at_utc"]) <= now < instant(base["reg_close_time"]):
                continue
            available=json.loads((root/"player_reports"/"analysis"/path.name).read_text(encoding="utf-8"))
            personal=json.loads((root/"personal"/path.name).read_text(encoding="utf-8"))
            report=build(base,available,personal,created=now)
            target=root/"player_factor"/path.name
            if target.exists():
                previous=json.loads(target.read_text(encoding="utf-8"))
                if (previous.get("source_observed_at_utc")==report["source_observed_at_utc"]
                        and previous.get("matches")==report["matches"]
                        and validate(previous,base,available,personal)):
                    continue
                history=root/"player_factor_history"/str(base["draw_number"])/(
                    previous["source_observed_at_utc"].replace(":","_")+".json")
                if not history.exists():
                    write_json(history,previous)
            if not validate(report,base,available,personal):
                raise ValueError("Spelarprognosen går inte att återskapa")
            write_json(target,report);saved+=1
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
            print("Spelarprognos hoppades över:",path,str(e),file=sys.stderr)
    print("Nya, separata spelarscenarier:",saved)


if __name__=="__main__":
    main()
