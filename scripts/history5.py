#!/usr/bin/env python3
"""Five-year historical coupon archive and *exploratory* walk-forward baseline.

Only earlier completed DRAWS update the Elo team ratings. Historical odds,
crowd percentages and official payouts are *not* inferred or fabricated.
Results date is registration-close DATE, not individual kickoff.
"""
import argparse
import csv
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
from collections import Counter, defaultdict

from scripts.analyze import optimize, selected_signs, correct_rows, evaluate_probability
from scripts.collect import write_json
from scripts.league_history import key_team

SUMMARY_SCHEMA = "stryktipslabbet-five-years-v1"
START = "2021-11-13"
SIGNS = "1X2"
MAX_DRAWS = 400


def read_rounds(path):
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    grouped = defaultdict(list)
    for r in rows:
        try:
            n = int(r["draw_number"])
            d = date.fromisoformat(r["date"]).isoformat()
            o = r["outcome"].upper()
            g1, g2 = int(r["score_home"]), int(r["score_away"])
            if not (START <= d <= datetime.now(timezone.utc).date().isoformat()
                    and 0 <= g1 <= 30 and 0 <= g2 <= 30
                    and o in SIGNS and n > 0):
                continue
            if (o == "1" and g1 <= g2 or o == "X" and g1 != g2 or o == "2" and g1 >= g2):
                # Some events are administratively settled ("lottade").
                # Preserve the coupon sign but never treat such rows as a
                # verified played football result in the forecast model.
                played = False
            else:
                played = True
            grouped[n].append({
                "draw": n, "date": d, "outcome": o,
                "home": key_team(r["team_home"]), "away": key_team(r["team_away"]),
                "score_home": g1, "score_away": g2,
                "played_consistent": played,
            })
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    rounds = []
    for n, rs in grouped.items():
        if len(rs) == 13 and len({r["date"] for r in rs}) == 1 and all(r["home"] != r["away"] for r in rs):
            rounds.append({"draw": n, "date": rs[0]["date"], "matches": rs})
    rounds.sort(key=lambda d: (d["date"], d["draw"]))
    if not 200 <= len(rounds) <= MAX_DRAWS:
        raise ValueError("Historiken behöver 200–400 fullständiga omgångar")
    return rounds


def pre_match_p(home, away, ratings, game_counts):
    # This is a fixed descriptive baseline, NOT calibrated/optimized on
    # five-year outcomes or based on historical sportsbook prices.
    hr = (ratings.get(home, 1500) - 1500) * game_counts.get(home, 0) / (game_counts.get(home, 0) + 8)
    ar = (ratings.get(away, 1500) - 1500) * game_counts.get(away, 0) / (game_counts.get(away, 0) + 8)
    diff = hr - ar + 70
    draw = min(.30, max(.17, .255 - .047 * min(1., abs(diff)/480)))
    home_weight = 1/(1 + math.exp(-diff/380))
    return [(1-draw)*home_weight, draw, (1-draw)*(1-home_weight)]


def walk_forward(rounds):
    ratings, game_counts = {}, Counter()
    rolling = Counter({"1": 25, "X": 25, "2": 25})
    byyear = defaultdict(lambda: {"draws":0,"matches":0,"elo_brier_sum":0.,
                                  "rolling_brier_sum":0.,"systems_96_10plus":0,
                                  "systems_96_13":0,"systems_1800_10plus":0,
                                  "systems_1800_13":0,"spent_96":0,"spent_1800":0})
    test_draws = 0
    calendar_scores = []
    for draw in rounds:
        # Snapshot all forecasts before ANY outcome in the draw enters rating.
        frozen = []
        for m in draw["matches"]:
            frozen.append(pre_match_p(m["home"], m["away"], ratings, game_counts))
        rolled = [rolling[s]/sum(rolling.values()) for s in SIGNS]
        if draw["date"] >= "2022-11-13":
            stats = byyear[draw["date"][:4]]
            test_draws += 1
            stats["draws"] += 1
            outcomes = "".join(m["outcome"] for m in draw["matches"])
            for m, p in zip(draw["matches"], frozen):
                if not m["played_consistent"]:
                    continue
                y = SIGNS.index(m["outcome"])
                stats["matches"] += 1
                stats["elo_brier_sum"] += sum((p[j]-(j==y))**2 for j in range(3))
                stats["rolling_brier_sum"] += sum((rolled[j]-(j==y))**2 for j in range(3))
            for limit, name in ((100, "96"), (1800, "1800")):
                cost, masks = optimize(frozen, limit)
                choices = [selected_signs(x) for x in masks]
                distribution = correct_rows(choices, outcomes)
                stats["spent_"+name] += cost
                stats["systems_"+name+"_10plus"] += int(any(distribution[k] > 0 for k in (10,11,12,13)))
                stats["systems_"+name+"_13"] += int(distribution[13] > 0)
            calendar_scores.append({"draw": draw["draw"], "date": draw["date"],
                "elo_p13_100": round(evaluate_probability(optimize(frozen,100)[1], frozen),8)})
        # Do not count fictitious match scores or lottad outcomes as matches.
        pending = []
        for m, p in zip(draw["matches"], frozen):
            if not m["played_consistent"]:
                continue
            actual = 1 if m["outcome"]=="1" else .5 if m["outcome"]=="X" else 0
            expected = p[0] + .5*p[1]
            pending.append((m["home"], m["away"], 30*(actual-expected)))
            rolling[m["outcome"]] += 1
        # Update all Elo differences simultaneously after draw outcomes.
        diff = defaultdict(float)
        appearances = Counter()
        for h,a,delta in pending:
            diff[h]+=delta;diff[a]-=delta
            appearances[h]+=1;appearances[a]+=1
        for team in diff:
            ratings[team] = ratings.get(team,1500) + diff[team]
            game_counts[team]+=appearances[team]

    years = []
    for name, row in sorted(byyear.items()):
        n = row["matches"]
        years.append({
            "year": name, "draws": row["draws"], "evaluated_played_matches": n,
            "elo_brier": round(row["elo_brier_sum"]/n,4) if n else None,
            "rolling_baseline_brier": round(row["rolling_brier_sum"]/n,4) if n else None,
            "systems_96_10plus": row["systems_96_10plus"],
            "systems_1800_10plus": row["systems_1800_10plus"],
            "systems_96_13": row["systems_96_13"], "systems_1800_13": row["systems_1800_13"],
            "spent_96": row["spent_96"], "spent_1800": row["spent_1800"],
        })
    return {"test_draws": test_draws, "years": years, "test_since": "2022-11-13",
            "note": "Elo-testet är en historisk övning med endast tidigare kupongresultat. Ingen gammal odds- eller streckhistorik eller verifierad utdelning."}


def summarize(rounds):
    outcomes = Counter()
    years = defaultdict(lambda: {"draws":0,"matches":0,"outcomes":Counter(),"goals":0,"score_consistent":0})
    for d in rounds:
        y = years[d["date"][:4]]
        y["draws"] += 1
        for m in d["matches"]:
            outcomes[m["outcome"]] += 1
            y["outcomes"][m["outcome"]] += 1
            y["matches"] += 1
            if m["played_consistent"]:
                y["goals"] += m["score_home"]+m["score_away"]
                y["score_consistent"] += 1
    test = walk_forward(rounds)
    return {
        "schema": SUMMARY_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "from": rounds[0]["date"], "to": rounds[-1]["date"],
        "rounds": len(rounds),
        "matches": sum(len(r["matches"]) for r in rounds),
        "draw_numbers": [rounds[0]["draw"], rounds[-1]["draw"]],
        "outcomes": {s: outcomes[s] for s in SIGNS},
        "years": [{"year":year, **{**row,"outcomes":{s:row["outcomes"][s] for s in SIGNS}}}
                  for year,row in sorted(years.items())],
        "backtest": test,
        "source":"community mirror of Svenska Spels public settled results: andreyhgl/stryktipset-results",
        "limits":[
            "De flesta gamla omgångar saknar dokumenterade förhandsodds, folkstreck och verifierade officiella utdelningar.",
            "Historiska modellprognoser är en rekonstruktion med tidigare resultat – inte sparade råd som faktiskt gavs då.",
            "Omgångens datum är registreringsdatum, inte individuella matchers avspark.",
            "Misstänkt lottade/administrativa tecken används för kupongresultat men inte modellens träning eller Brier.",
            "Systemträffar är inte samma sak som kronor i vinst."
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="data")
    args = parser.parse_args()
    root = Path(args.outdir)
    rounds = read_rounds(root / "history" / "stryktipset-five-years.csv")
    report = summarize(rounds)
    write_json(root / "history" / "summary.json", report)
    print("Fem år:", report["rounds"], "omgångar,", report["matches"], "matcher,",
          report["backtest"]["test_draws"], "kronologiskt testade omgångar")


if __name__ == "__main__":
    main()
