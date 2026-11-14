#!/usr/bin/env python3
"""V17: källfrysta engelska nyckelspelare och hypotetisk 1/X/2-känslighet.

Ingen information efter spelstopp. Detta är INTE en kalibrerad prognos eller
rekommendation; skador kan redan vara inprisade i bookmakerodds.
Okänd truppstatus är aldrig lika med tillgänglig.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

from scripts.analyze import valid_analysis, selected_signs
from scripts.collect import write_json
from scripts.feature_model import optimize_exact
from scripts.solo import validate as valid_personal
from scripts.league_history import key_team
from scripts.publish import instant

SCHEMA = "stryktipslabbet-player-feed-v17"
REPORT_SCHEMA = "stryktipslabbet-player-impact-v17"
MODEL = "player-sensitivity-untrained-2026-11-14-v17"
ALLOWED_LEAGUES = {"Premier League", "Championship", "League One", "League Two"}
MAX_AGE_HOURS = 36
MAX_TEAM_PENALTY = 0.20
STATUS_WEIGHTS = {"out": 1.0, "suspended": 1.0, "doubtful": 0.40}


def bounded(x, low=0.0, high=1.0):
    return min(high, max(low, x))


def nonneg(value):
    try:
        x = float(value)
        return x if math.isfinite(x) and x >= 0 else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def ranked_players(players):
    """Rankas inom laget; minuter/starter väger tyngre än mål och assist.

    Heuristisk relativ betydelse, inte kausal on/off-effekt. Spelare med färre
    än fyra framträdanden får lägre tillförlitlighet. Stats är per lag+liga.
    """
    if not isinstance(players, list):
        return []
    unique = {}
    for p in players:
        if not isinstance(p, dict) or type(p.get("id")) is not int or p["id"] <= 0:
            continue
        if p["id"] in unique:
            continue  # flera säsongsrader får inte dubbelräknas
        if not isinstance(p.get("name"), str) or not p["name"].strip():
            continue
        appearances = nonneg(p.get("appearances"))
        minutes = nonneg(p.get("minutes"))
        starts = nonneg(p.get("starts"))
        if not appearances or not minutes:
            continue
        unique[p["id"]] = {
            "id": p["id"], "name": p["name"].strip()[:100],
            "position": str(p.get("position") or "Okänd")[:32],
            "minutes": minutes, "starts": starts,
            "appearances": appearances,
            "goals": nonneg(p.get("goals")), "assists": nonneg(p.get("assists"))
        }
    if len(unique) < 5:
        return []  # inga tillförlitliga jämförelser om truppen är ofullständig
    roster = list(unique.values())
    max_minutes = max(x["minutes"] for x in roster)
    max_starts = max(x["starts"] for x in roster)
    for p in roster:
        per90 = (p["goals"] + 0.7*p["assists"]) * 90 / p["minutes"]
        availability = .52 * p["minutes"] / max_minutes
        starting = .30 * p["starts"] / max(1, max_starts)
        production = .18 * bounded(per90 / .75)
        confidence = bounded(p["appearances"] / 8)
        p["importance"] = round((availability + starting + production) * confidence, 4)
        p["importance_basis"] = "minuter, starter, mål, assist (heuristisk)"
    return sorted(roster, key=lambda p: (-p["importance"], -p["minutes"], p["name"]))


def side_impact(side):
    """Returnerar (straff, nyckelspelare, felorsak). Bara fixture-specifik frånvaro."""
    if (not isinstance(side, dict) or side.get("coverage") != "verified_provider_feed"
        or not side.get("players_covered") or not side.get("injuries_covered")):
        return None, [], "Ligakällan saknar verifierad spelar- eller frånvarotäckning"
    roster = ranked_players(side.get("players", []))
    if not roster:
        return None, [], "Otillräcklig statistik för att rangordna truppen"
    by_id = {p["id"]: p for p in roster}
    absences = side.get("absences", [])
    if not isinstance(absences, list):
        return None, [], "Ogiltig skadeinformation"
    relevant, seen = [], set()
    for item in absences:
        if (not isinstance(item, dict) or type(item.get("player_id")) is not int
            or item.get("status") not in STATUS_WEIGHTS):
            return None, [], "Ofullständiga frånvarouppgifter"
        pid = item["player_id"]
        if pid in seen:
            continue
        seen.add(pid)
        if pid not in by_id:
            # Ingen gissning om stor effekt när statistik för spelaren saknas.
            return None, [], "Saknar tillförlitlig statistik för rapporterad spelare"
        player = by_id[pid]
        relevant.append({
            "id": pid, "name": player["name"], "position": player["position"],
            "importance": player["importance"],
            "status": item["status"], "reason": str(item.get("reason") or "")[:110],
            "estimated_weight": STATUS_WEIGHTS[item["status"]]
        })
    penalty = sum(.095 * a["importance"] * a["estimated_weight"] for a in relevant)
    return min(MAX_TEAM_PENALTY, penalty), sorted(relevant, key=lambda p: -p["importance"]), None


def sensitivity(prior, home_penalty, away_penalty):
    """Symmetrisk log-viktsjustering, inte uppskattad kausal goal-difference."""
    if (not isinstance(prior, list) or len(prior) != 3
        or not all(type(x) in (float, int) and 0 < x < 1 for x in prior)
        or abs(sum(prior)-1) > 1e-4):
        raise ValueError("Ogiltig originalprognos")
    signal = bounded(away_penalty - home_penalty, -.20, .20)
    scaled = [prior[0]*math.exp(signal), prior[1]*(1 + .1*abs(signal)),
              prior[2]*math.exp(-signal)]
    total = sum(scaled)
    return [x/total for x in scaled]


def source_ok(analysis, feed, now):
    if not valid_analysis(analysis, now) or not isinstance(feed, dict):
        return False
    try:
        observed = instant(analysis["observed_at_utc"])
        close = instant(analysis["reg_close_time"])
        collected = instant(feed["collected_at_utc"])
        if (feed.get("schema") != SCHEMA or
            feed.get("provider") != "API-Football" or
            feed.get("draw_number") != analysis["draw_number"] or
            not isinstance(feed.get("source_snapshot_sha256"), (str, type(None))) or
            feed.get("reg_close_time") != analysis["reg_close_time"] or
            instant(feed["source_observed_at_utc"]) > collected or
            not collected <= now < close or
            (now-collected).total_seconds() > MAX_AGE_HOURS*3600):
            return False
        ms = feed["matches"]
        if not isinstance(ms, list) or len(ms) != 13:
            return False
        for row, original in zip(ms, analysis["matches"]):
            if (row["number"] != original["number"] or
                key_team(row["home"]) != key_team(original["home"]) or
                key_team(row["away"]) != key_team(original["away"])):
                return False
        return True
    except (ValueError, KeyError, TypeError, OverflowError):
        return False



def equal_cost_scenarios(analysis, results, personal):
    """Compare exactly equal-cost original/player systems; never change the original."""
    if not valid_personal(personal, analysis):
        raise ValueError("100-kronorssystemet hör inte till samma kupong")
    supported = sum(m["scenario_p"] is not None for m in results)
    if supported == 0:
        return []
    # Missing team information retains the published market probability.
    # It is NOT evidence that any specific player is healthy.
    probs = [m["scenario_p"] if m["scenario_p"] is not None else m["market_p"]
             for m in results]
    signs = "1X2"
    def cover(choices):
        out = 1.0
        for choice, p in zip(choices, probs):
            out *= sum(p[signs.index(c)] for c in choice)
        return round(out, 9)
    scenarios = []
    for budget, baseline in ((100, personal["systems"][0]),
                             (1800, analysis["systems"][0])):
        cost = baseline["cost"]
        masks = optimize_exact(probs, cost)
        choices = [selected_signs(mask) for mask in masks]
        if len(choices) != 13 or math.prod(len(c) for c in choices) != cost:
            raise ValueError("Spelarscenariot förändrade radkostnaden")
        scenarios.append({
            "budget_limit": budget, "cost": cost,
            "source_market_choices": baseline["choices"],
            "player_scenario_choices": choices,
            "changed_matches": sum(a != b for a,b in zip(baseline["choices"],choices)),
            "covered_by_player_data": supported,
            "unknown_matches_using_market_only": 13-supported,
            "original_p13_under_scenario": cover(baseline["choices"]),
            "player_p13_under_scenario": cover(choices),
            "experimental": True
        })
    return scenarios


def build(analysis, feed, created=None, personal=None):
    now = created or datetime.now(timezone.utc)
    if not source_ok(analysis, feed, now):
        raise ValueError("Källan är för gammal, efter spelstopp eller felaktigt matchad")
    results = []
    for original, row in zip(analysis["matches"], feed["matches"]):
        baseline = original["p"][:]
        league = row.get("league")
        output = {
            "number": original["number"], "home": original["home"],
            "away": original["away"], "league": league,
            "market_p": baseline, "scenario_p": None,
            "delta_pp": None, "top_players_home": [], "top_players_away": [],
            "absences_home": [], "absences_away": [], "reason": ""
        }
        if league not in ALLOWED_LEAGUES or not row.get("fixture_id"):
            output["reason"] = "Utanför täckningen / match ej entydigt identifierad"
        else:
            home, away = row.get("home_feed", {}), row.get("away_feed", {})
            hp, abs_h, why_h = side_impact(home)
            ap, abs_a, why_a = side_impact(away)
            output["absences_home"] = abs_h
            output["absences_away"] = abs_a
            output["top_players_home"] = ranked_players(home.get("players", []))[:5]
            output["top_players_away"] = ranked_players(away.get("players", []))[:5]
            if hp is None or ap is None:
                output["reason"] = "; ".join(x for x in (why_h, why_a) if x)
            else:
                revised = sensitivity(baseline, hp, ap)
                output["scenario_p"] = [round(p, 9) for p in revised]
                output["delta_pp"] = [round(100*(a-b), 2) for a,b in zip(revised, baseline)]
                output["reason"] = (
                    "Illustrativ påverkan om rapporterad frånvaro INTE redan ingår i oddsen. "
                    "En tom frånvarolista bevisar inte att alla är tillgängliga."
                )
        results.append(output)
    return {
        "schema": REPORT_SCHEMA, "model": MODEL,
        "draw_number": analysis["draw_number"],
        "source_snapshot_sha256": analysis.get("source_snapshot_sha256"),
        "source_observed_at_utc": analysis["observed_at_utc"],
        "provider_collected_at_utc": feed["collected_at_utc"],
        "reg_close_time": analysis["reg_close_time"],
        "created_at_utc": now.isoformat(),
        "matches": results,
        "systems": equal_cost_scenarios(analysis, results, personal) if personal is not None else [],
        "coverage": {
            "scenario_matches": sum(x["scenario_p"] is not None for x in results),
            "unknown_matches": sum(x["scenario_p"] is None for x in results)
        },
        "model_effect": "Endast hypotetisk känslighetsanalys. Ursprungsmodellen, spikval, radbudget och inlämning påverkas inte.",
        "warning": "Ej kalibrerad. Frånvaro kan redan vara inprisad. Utvärdera mot frysta framtida omgångar."
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="data")
    args = parser.parse_args()
    root = Path(args.outdir)
    count = 0
    now = datetime.now(timezone.utc)
    for file in sorted((root/"analysis").glob("*.json")):
        try:
            original = json.loads(file.read_text(encoding="utf-8"))
            if now >= instant(original["reg_close_time"]):
                continue
            source = root/"player_feed"/file.name
            if not source.exists():
                continue
            feed = json.loads(source.read_text(encoding="utf-8"))
            personal_path=root/"personal"/file.name
            personal=(json.loads(personal_path.read_text(encoding="utf-8"))
                      if personal_path.exists() else None)
            report = build(original, feed, now, personal=personal)
            write_json(root/"player_impact"/file.name, report)
            count += 1
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            print("Spelarpåverkan hoppades över:", file.name, str(exc)[:130], file=sys.stderr)
    print("V17 hypotetiska spelarprognoser:", count)


if __name__ == "__main__":
    main()
