#!/usr/bin/env python3
"""Collect licensed public-domain league results; pre-match form only.

Source: https://github.com/openfootball/football.json (CC0 1.0).
No automated fetching from football-data.co.uk (restricted use terms).
Only dates STRICTLY before the observation day may enter pre-match features.
No current injuries/lineups are invented or inferred.
"""
import argparse
import csv
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json
import re
import sys
import time
import unicodedata

from scripts.collect import write_json
from scripts.analyze import valid_analysis
from scripts.publish import instant

BASE = "https://raw.githubusercontent.com/openfootball/football.json/master/"
SOURCE = "OpenFootball football.json · CC0 1.0"
FORM_SCHEMA = "stryktipslabbet-team-form-v1"
DATA_SCHEMA = "stryktipslabbet-league-results-v1"
MAX_BYTES = 1_250_000

# These paths are verified to exist in the OpenFootball source repository.
SOURCES = {
    "2021-22": ["at.1","de.1","de.2","en.1","en.2","es.1","fr.1","it.1","nl.1","pt.1"],
    "2022-23": ["at.1","de.1","de.2","en.1","en.2","es.1","fr.1","it.1","nl.1","pt.1"],
    "2023-24": ["at.1","de.1","de.2","en.1","en.2","es.1","fr.1","it.1","nl.1","pt.1"],
    "2024-25": ["at.1","at.2","au.1","be.1","de.1","de.2","en.1","en.2","en.3","en.4","es.1","es.2","fr.1","fr.2","gr.1","it.1","it.2","nl.1","pt.1","sco.1","tr.1"],
    "2025-26": ["at.1","at.2","be.1","de.1","de.2","en.1","en.2","en.3","en.4","es.1","es.2","fr.1","fr.2","gr.1","it.1","it.2","nl.1","pt.1","sco.1","tr.1"],
    "2026-27": ["de.1","en.1","en.2","es.1","fr.1","it.1","nl.1","pt.1"],
}

ALIASES = {
    "manchester u":"manchester united",
    "man utd":"manchester united",
    "manchester united":"manchester united",
    "manchester c":"manchester city",
    "man city":"manchester city",
    "nottingham":"nottingham forest",
    "nottingham forest":"nottingham forest",
    "newcastle":"newcastle united",
    "newcastle united":"newcastle united",
    "west bromwich":"west bromwich albion",
    "west bromwich albion":"west bromwich albion",
    "wolves":"wolverhampton wanderers",
    "wolverhampton":"wolverhampton wanderers",
    "wolverhampton wanderers":"wolverhampton wanderers",
    "brighton":"brighton hove albion",
    "brighton hove albion":"brighton hove albion",
    "qpr":"queens park rangers",
    "queens park rang":"queens park rangers",
    "queens park rangers":"queens park rangers",
    "bournemouth":"bournemouth",
    "afc bournemouth":"bournemouth",
    "sheffield u":"sheffield united",
    "sheffield w":"sheffield wednesday",
    "sheffield united":"sheffield united",
    "sheffield wednesday":"sheffield wednesday",
    "leeds":"leeds united",
    "leeds united":"leeds united",
    "ipswich":"ipswich town",
    "ipswich town":"ipswich town",
    "luton":"luton town",
    "luton town":"luton town",
    "derby":"derby county",
    "derby county":"derby county",
    "huddersfield":"huddersfield town",
    "huddersfield town":"huddersfield town",
    "cardiff":"cardiff city",
    "cardiff city":"cardiff city",
    "swansea":"swansea city",
    "swansea city":"swansea city",
    "birmingham":"birmingham city",
    "birmingham city":"birmingham city",
    "leicester":"leicester city",
    "leicester city":"leicester city",
    "bristol rovers":"bristol rovers",
    "blackburn":"blackburn rovers",
    "blackburn rovers":"blackburn rovers",
    "bolton":"bolton wanderers",
    "bolton wanderers":"bolton wanderers",
    "wigan":"wigan athletic",
    "wigan athletic":"wigan athletic",
    "preston":"preston north end",
    "preston north end":"preston north end",
    "charlton":"charlton athletic",
    "charlton athletic":"charlton athletic",
    "oxford":"oxford united",
    "oxford united":"oxford united",
    "wimbledon":"wimbledon",
    "afc wimbledon":"wimbledon",
    "cambridge":"cambridge united",
    "cambridge united":"cambridge united",
    "lincoln":"lincoln city",
    "lincoln city":"lincoln city",
    "plymouth":"plymouth argyle",
    "plymouth argyle":"plymouth argyle",
    "reading":"reading",
    "grimsby":"grimsby town",
    "grimsby town":"grimsby town",
    "swindon":"swindon town",
    "swindon town":"swindon town",
    "northampton":"northampton town",
    "northampton town":"northampton town",
    "harrogate":"harrogate town",
    "harrogate town":"harrogate town",
    "crawley":"crawley town",
    "crawley town":"crawley town",
    "stevenage":"stevenage",
    "milton keynes dons":"milton keynes dons",
    "mk dons":"milton keynes dons",
    "bayern munchen":"bayern munchen",
    "bayern munich":"bayern munchen",
    "atletico madrid":"atletico madrid",
    "inter":"internazionale",
    "inter milan":"internazionale",
    "internazionale":"internazionale",
    "ac milan":"milan",
    "milan":"milan",
    "paris saint germain":"paris saint germain",
    "sverige":"sweden",
    "norge":"norway",
    "danmark":"denmark",
    "finland":"finland",
    "polen":"poland",
    "rumanien":"romania",
    "nordirland":"northern ireland",
    "osterrike":"austria",
    "irland":"republic of ireland",
    "georgien":"georgia",
    "ungern":"hungary",
    "schweiz":"switzerland",
    "bosnien hercegovina":"bosnia herzegovina",
    "bosnia herzegovina":"bosnia herzegovina",
    "slovenien":"slovenia",
    "grekland":"greece",
    "kroatien":"croatia",
    "tjeckien":"czech republic",
    "czechia":"czech republic",
    "ukraina":"ukraine",
    "spanien":"spain",
    "tyskland":"germany",
    "frankrike":"france",
    "nederlanderna":"netherlands",
    "belgien":"belgium",
    "skottland":"scotland",
    "england":"england",
    "nordmakedonien":"north macedonia",
    "serbien":"serbia",
    "albanien":"albania",
    "montenegro":"montenegro",
    "estland":"estonia",
    "litauen":"lithuania",
    "lettland":"latvia",
    "island":"iceland",
    "turkiet":"turkey",
    "turkiye":"turkey",
    "cypern":"cyprus",
    "luxemburg":"luxembourg",
    "psg":"paris saint germain",
}


def key_team(name):
    text = unicodedata.normalize("NFKD", name.casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("&", " and ").replace("'", "").replace(".", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    for ending in (" football club", " fc", " afc", " cf"):
        if text.endswith(ending):
            text = text[:-len(ending)]
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" and ", " ")
    return ALIASES.get(text, text)


def parse_source(doc, season, league, fetched_at):
    if not isinstance(doc, dict) or not isinstance(doc.get("matches"), list):
        raise ValueError("Ogiltig liga-fil")
    matches = []
    for e in doc["matches"]:
        try:
            d = e["date"]
            datetime.strptime(d, "%Y-%m-%d")
            team1, team2 = e["team1"], e["team2"]
            score = e.get("score", {}).get("ft")
            if not isinstance(score, list) or len(score) != 2:
                continue
            if any(type(v) is not int or not (0 <= v <= 30) for v in score):
                continue
            h, a = key_team(team1), key_team(team2)
            if not h or not a or h == a:
                continue
            matches.append({"date": d, "home": h, "away": a,
                            "home_goals": score[0], "away_goals": score[1]})
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    if len(matches) < 20:
        # It might be a partially published current season. Do not store
        # misleadingly tiny or malformed "league" data.
        raise ValueError("För få verifierade ligamatcher")
    matches.sort(key=lambda m: (m["date"], m["home"], m["away"]))
    return {"schema": DATA_SCHEMA, "season": season, "league": league,
            "source": SOURCE, "source_url": BASE + season + "/" + league + ".json",
            "fetched_at_utc": fetched_at.isoformat(), "matches": matches}


def read_nationals(path):
    """Load public-domain men's national team results, including neutral venues."""
    if not path.exists():
        return []
    matches = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                d = datetime.strptime(r["date"], "%Y-%m-%d").date().isoformat()
                h, a = key_team(r["home_team"]), key_team(r["away_team"])
                hg, ag = int(r["home_score"]), int(r["away_score"])
                if not ("2020-01-01" <= d <= "2027-12-31" and
                        0 <= hg <= 30 and 0 <= ag <= 30 and h and a and h != a):
                    continue
                matches.append({
                    "date": d, "home": h, "away": a,
                    "home_goals": hg, "away_goals": ag,
                    "neutral": r["neutral"].strip().upper() == "TRUE",
                    "league": "men-national-teams", "season": d[:4],
                })
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
    return matches


def update_nationals(data, now):
    """Daily bounded refresh; only commit the CSV when source rows changed."""
    csv_path = data / "form" / "national_team_results.csv"
    state_path = data / "form" / "national_fetch_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        last = instant(state["checked_at_utc"])
        if (now - last).total_seconds() < 24*3600:
            return 0
    except (OSError, KeyError, ValueError, TypeError):
        pass
    try:
        url = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
        req = Request(url, headers={"User-Agent": "Stryktipslabbet/12.0 (public domain international results)"})
        with urlopen(req, timeout=25) as response:
            raw = response.read(6_000_001)
        if len(raw) > 6_000_000:
            raise ValueError("Landslagsarkiv för stort")
        lines = raw.decode("utf-8-sig").replace("\r", "").split("\n")
        if not lines or not lines[0].startswith("date,home_team,away_team,"):
            raise ValueError("Landslagskällans kolumner har ändrats")
        relevant = [line for line in lines[1:]
                    if line[:10] >= "2020-01-01" and line[:10] <= now.date().isoformat()
                    and re.match(r"^\d{4}-\d{2}-\d{2},", line)]
        if len(relevant) < 4000:
            raise ValueError("För få landskamper, källan kan vara ofullständig")
        new = lines[0] + "\n" + "\n".join(relevant) + "\n"
        current = csv_path.read_text(encoding="utf-8") if csv_path.exists() else ""
        if new != current:
            csv_path.parent.mkdir(parents=True,exist_ok=True)
            csv_path.write_text(new,encoding="utf-8")
            changed = 1
        else:
            changed = 0
        write_json(state_path, {
            "source": "martj42/international_results (CC0 1.0)",
            "source_url": url,
            "checked_at_utc": now.isoformat(),
            "rows": len(relevant),
        })
        print("Landslagsdata:",len(relevant),"matcher,", "uppdaterad" if changed else "oförändrad")
        return changed
    except (OSError, ValueError, URLError, HTTPError, TimeoutError) as exc:
        print("Landslagsuppdatering misslyckades, senast sparade fil används:",str(exc)[:120],
              file=sys.stderr)
        return 0


def read_db(data):
    matches = []
    files = sorted((data / "form" / "leagues").glob("*/*.json"))
    for f in files:
        try:
            x = json.loads(f.read_text(encoding="utf-8"))
            if x.get("schema") != DATA_SCHEMA or not isinstance(x.get("matches"), list):
                continue
            for m in x["matches"]:
                matches.append({**m, "season": x["season"], "league": x["league"]})
        except (ValueError, OSError, TypeError):
            continue
    matches.extend(read_nationals(data / "form" / "national_team_results.csv"))
    # Cross-source duplicates are removed by team/date/score, not by league.
    seen = set()
    out = []
    for m in sorted(matches, key=lambda x: (x["date"], x["home"], x["away"], x["league"])):
        ident = (m["date"], m["home"], m["away"], m["home_goals"], m["away_goals"])
        if ident not in seen:
            seen.add(ident)
            out.append(m)
    return out, len(files)


def update_leagues(data, now, limit=14):
    folder = data / "form" / "leagues"
    state_path = data / "form" / "fetch_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    done = 0
    for season, leagues in sorted(SOURCES.items(), reverse=True):
        for code in leagues:
            dest = folder / season / (code + ".json")
            ref = season + "/" + code
            # Historical seasons are immutable for our purposes, and live
            # season refreshes at most daily, even on 30min Actions schedules.
            if dest.exists() and season != "2026-27":
                continue
            last = state.get(ref)
            if dest.exists() and last:
                try:
                    if now - datetime.fromisoformat(last) < timedelta(hours=24):
                        continue
                except ValueError:
                    pass
            if done >= limit:
                return done
            try:
                req = Request(BASE + ref + ".json",
                              headers={"Accept": "application/json",
                                       "User-Agent": "Stryktipslabbet/12.0 (public domain league form)"})
                with urlopen(req, timeout=18) as response:
                    raw = response.read(MAX_BYTES + 1)
                    if len(raw) > MAX_BYTES:
                        raise ValueError("Källfil för stor")
                doc = json.loads(raw)
                parsed = parse_source(doc, season, code, now)
                write_json(dest, parsed)
                state[ref] = now.isoformat()
                print("Ligadata:", ref, len(parsed["matches"]), "matcher")
            except (HTTPError, URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError) as exc:
                print("Kunde inte hämta", ref, str(exc)[:140], file=sys.stderr)
                # Reserve a bounded retry window but keep trying other leagues.
                state[ref] = now.isoformat()
            finally:
                done += 1
                write_json(state_path, state)
            time.sleep(.15)
    return done


def result_for(team, match):
    if match["home"] == team:
        gf, ga, own_home = match["home_goals"], match["away_goals"], True
    else:
        gf, ga, own_home = match["away_goals"], match["home_goals"], False
    pts = 3 if gf > ga else 1 if gf == ga else 0
    return {"date": match["date"], "gf": gf, "ga": ga, "points": pts,
            "venue": "neutral" if match.get("neutral") else "home" if own_home else "away",
            "outcome": "V" if gf > ga else "O" if gf == ga else "F"}


def team_form(team, cutoff, db, venue):
    canonical = key_team(team)
    rows = [result_for(canonical, m) for m in db if m["date"] < cutoff
            and (m["home"] == canonical or m["away"] == canonical)]
    rows.sort(key=lambda r: r["date"], reverse=True)
    recent5, recent10 = rows[:5], rows[:10]
    venue5 = [r for r in rows if r["venue"] == venue][:5]
    def digest(items):
        if not items:
            return {"n": 0, "points_per_game": None, "goals_for_per_game": None,
                    "goals_against_per_game": None, "wins": 0, "draws": 0, "losses": 0}
        n = len(items)
        return {
            "n": n,
            "points_per_game": round(sum(r["points"] for r in items) / n, 2),
            "goals_for_per_game": round(sum(r["gf"] for r in items) / n, 2),
            "goals_against_per_game": round(sum(r["ga"] for r in items) / n, 2),
            "wins": sum(r["outcome"] == "V" for r in items),
            "draws": sum(r["outcome"] == "O" for r in items),
            "losses": sum(r["outcome"] == "F" for r in items),
        }
    return {
        "canonical_name": canonical,
        "games_available": len(rows),
        "last5": digest(recent5),
        "last10": digest(recent10),
        "venue5": digest(venue5),
        "last_match_date": rows[0]["date"] if rows else None,
        "form_last5": "".join(r["outcome"] for r in reversed(recent5)) if recent5 else None,
    }


def build_features(analysis, db, source_files, created=None):
    now = created or datetime.now(timezone.utc)
    if not valid_analysis(analysis, now):
        raise ValueError("Ogiltig förhandsanalys")
    observed, close = instant(analysis["observed_at_utc"]), instant(analysis["reg_close_time"])
    if not observed < now < close:
        raise ValueError("Formrapport får endast skapas före spelstopp")
    cutoff = observed.date().isoformat()
    rows = []
    for m in analysis["matches"]:
        home = team_form(m["home"], cutoff, db, "home")
        away = team_form(m["away"], cutoff, db, "away")
        h2h = [x for x in db if x["date"] < cutoff and
               ((x["home"] == home["canonical_name"] and x["away"] == away["canonical_name"]) or
                (x["home"] == away["canonical_name"] and x["away"] == home["canonical_name"]))]
        h2h.sort(key=lambda x: x["date"], reverse=True)
        rows.append({
            "number": m["number"], "home": m["home"], "away": m["away"],
            "market_p": m["p"], "streck": m["streck"],
            "home_form": home, "away_form": away,
            "h2h_last5": len(h2h[:5]),
            "coverage": "båda" if home["last5"]["n"]>=3 and away["last5"]["n"]>=3
                       else "delvis" if home["last5"]["n"] or away["last5"]["n"] else "saknas",
        })
    return {
        "schema": FORM_SCHEMA, "draw_number": analysis["draw_number"],
        "source_observed_at_utc": analysis["observed_at_utc"],
        "reg_close_time": analysis["reg_close_time"],
        "source_snapshot_sha256": analysis.get("source_snapshot_sha256"),
        "created_at_utc": now.isoformat(),
        "cutoff_date_exclusive": cutoff,
        "source": SOURCE,
        "league_files_read": source_files,
        "complete_matches": sum(x["coverage"] == "båda" for x in rows),
        "partial_matches": sum(x["coverage"] == "delvis" for x in rows),
        "missing_matches": sum(x["coverage"] == "saknas" for x in rows),
        "matches": rows,
        "note": "Hemma-/bortaform enbart från tidigare daterade ligamatcher; inga skador, lineups eller oddsmodeller är bekräftade.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data")
    ap.add_argument("--limit", type=int, default=14)
    args = ap.parse_args()
    data = Path(args.outdir)
    now = datetime.now(timezone.utc)
    national_refreshed = update_nationals(data, now)
    got = update_leagues(data, now, max(0, min(30, args.limit)))
    db, nfiles = read_db(data)
    created = 0
    for f in sorted((data / "analysis").glob("*.json")):
        try:
            analysis = json.loads(f.read_text(encoding="utf-8"))
            if now >= instant(analysis["reg_close_time"]):
                continue
            result = build_features(analysis, db, nfiles, created=now)
            write_json(data / "form" / "features" / f.name, result)
            created += 1
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            print("Formrapport saknas:", f, exc, file=sys.stderr)
    print("Nya källfiler:", got, "| landslagsuppdatering:", national_refreshed, "| ligamatcher och landskamper:", len(db),
          "| ligafiler:", nfiles, "| förhandsrapporter:", created)


if __name__ == "__main__":
    main()
