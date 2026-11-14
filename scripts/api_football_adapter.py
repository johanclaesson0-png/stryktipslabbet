#!/usr/bin/env python3
"""Optional v17 API-Football adapter for English 1st–4th tier Stryktipset fixtures.

Opt-in only: provider key AND confirmed data-publication rights required.
Public GitHub repository must never contain API credentials or raw responses.
Emits minimal derived player metrics, fixture IDs and absence labels. If league,
team or fixture identification is ambiguous, marks coverage missing.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.analyze import valid_analysis
from scripts.collect import write_json
from scripts.league_history import key_team
from scripts.player_impact import SCHEMA, ALLOWED_LEAGUES
from scripts.publish import instant

API = "https://v3.football.api-sports.io/"
MAX_CALLS = 80
MAX_PAGES = 2
SOURCE = "https://www.api-football.com/documentation_v3"


class APIClient:
    def __init__(self, key, max_calls=MAX_CALLS, transport=None):
        if not key:
            raise ValueError("API-nyckel krävs")
        self.key = key
        self.max_calls = max_calls
        self.calls = 0
        self.transport = transport

    def get(self, route, params):
        if self.calls >= self.max_calls:
            raise ValueError("Daglig förfrågningsbudget för denna körning uppnådd")
        self.calls += 1
        if self.transport:
            result = self.transport(route, params)
        else:
            url = API + route + "?" + urlencode(params)
            req = Request(url, headers={
                "x-apisports-key": self.key,
                "Accept": "application/json",
                "User-Agent": "Stryktipslabbet/17 (source-checked research)"
            })
            with urlopen(req, timeout=16) as response:
                if response.status != 200:
                    raise ValueError("Leverantören svarade med felstatus")
                raw = response.read(1_200_001)
                if len(raw) > 1_200_000:
                    raise ValueError("För stort API-svar")
                result = json.loads(raw)
        if not isinstance(result, dict) or not isinstance(result.get("response"), list):
            raise ValueError("Felaktigt API-svar")
        if result.get("errors"):
            raise ValueError("API-Football angav fel i svaret")
        return result


def season_for(dt):
    # English season named by its starting year, e.g. 2026/27 -> 2026.
    return dt.year if dt.month >= 7 else dt.year - 1


def english_leagues(client, season):
    doc = client.get("leagues", {"country": "England", "season": season})
    found = {}
    for item in doc["response"]:
        league = item.get("league", {})
        country = item.get("country", {})
        name = league.get("name")
        if (name not in ALLOWED_LEAGUES or league.get("type") != "League"
            or country.get("name") != "England" or not isinstance(league.get("id"), int)):
            continue
        seasons = [s for s in item.get("seasons", []) if s.get("year") == season]
        if len(seasons) != 1:
            continue
        coverage = seasons[0].get("coverage") or {}
        found[name] = {
            "id": league["id"], "season": season,
            "players": coverage.get("players") is True,
            "injuries": coverage.get("injuries") is True,
            "fixtures": True
        }
    return found


def candidate_fixtures(client, leagues, close):
    begin = close.date()
    end = begin + timedelta(days=2)
    matches = []
    for name, info in sorted(leagues.items()):
        try:
            doc = client.get("fixtures", {
                "league": info["id"], "season": info["season"],
                "from": begin.isoformat(), "to": end.isoformat()
            })
            for x in doc["response"]:
                fixture = x.get("fixture") or {}
                teams = x.get("teams") or {}
                home = (teams.get("home") or {})
                away = (teams.get("away") or {})
                fid = fixture.get("id")
                start = fixture.get("date")
                try:
                    kickoff = instant(start)
                except (ValueError, TypeError, OverflowError):
                    continue
                if not (type(fid) is int and fid > 0 and kickoff > close
                        and type(home.get("id")) is int and type(away.get("id")) is int):
                    continue
                if not isinstance(home.get("name"), str) or not isinstance(away.get("name"), str):
                    continue
                matches.append({
                    "fixture_id": fid, "league": name, "league_id": info["id"],
                    "season": info["season"], "kickoff": kickoff.isoformat(),
                    "home": home, "away": away,
                    "players_covered": info["players"],
                    "injuries_covered": info["injuries"]
                })
        except (ValueError, OSError, TimeoutError) as exc:
            print("Engelsk liga ej tillgänglig:", name, type(exc).__name__, file=sys.stderr)
    return matches


def matching_fixture(match, candidates):
    # Exact canonical pairs only, no fuzzy guesses. Ambiguous pairs -> missing.
    home = key_team(match["home"])
    away = key_team(match["away"])
    choices = [
        f for f in candidates
        if key_team(f["home"]["name"]) == home and key_team(f["away"]["name"]) == away
    ]
    return choices[0] if len(choices) == 1 else None


def safe_number(value):
    try:
        x = float(value)
        return max(0, x) if 0 <= x < 10**8 else 0
    except (ValueError, TypeError, OverflowError):
        return 0


def get_players(client, team_id, league_id, season):
    rows = []
    seen = set()
    for page in range(1, MAX_PAGES + 1):
        doc = client.get("players", {
            "team": team_id, "league": league_id, "season": season, "page": page
        })
        for x in doc["response"]:
            player = x.get("player") or {}
            pid = player.get("id")
            if type(pid) is not int or pid <= 0 or pid in seen:
                continue
            valid = [
                s for s in x.get("statistics", [])
                if (s.get("team") or {}).get("id") == team_id
                and (s.get("league") or {}).get("id") == league_id
            ]
            if len(valid) != 1:
                continue
            s = valid[0]
            games = s.get("games") or {}
            goals = s.get("goals") or {}
            seen.add(pid)
            rows.append({
                "id": pid, "name": str(player.get("name") or "")[:100],
                "position": str(games.get("position") or "Unknown")[:32],
                "appearances": safe_number(games.get("appearences")),  # vendor spelling
                "minutes": safe_number(games.get("minutes")),
                "starts": safe_number(games.get("lineups")),
                "goals": safe_number(goals.get("total")),
                "assists": safe_number(goals.get("assists"))
            })
        paging = doc.get("paging") or {}
        if not doc["response"] or page >= int(paging.get("total") or 1):
            break
    return rows


def get_absences(client, fixture_id, team_id):
    doc = client.get("injuries", {"fixture": fixture_id})
    seen = set()
    out = []
    for item in doc["response"]:
        if (item.get("fixture") or {}).get("id") != fixture_id:
            continue
        if (item.get("team") or {}).get("id") != team_id:
            continue
        player = item.get("player") or {}
        pid = player.get("id")
        if type(pid) is not int or pid <= 0 or pid in seen:
            continue
        provider_type = str(player.get("type") or "").lower()
        if provider_type == "missing fixture":
            reason = str(player.get("reason") or "")
            status = "suspended" if "suspend" in reason.lower() else "out"
        elif provider_type == "questionable":
            status = "doubtful"
        else:
            continue  # never assume any unrecognized status
        seen.add(pid)
        out.append({
            "player_id": pid, "status": status,
            "reason": str(player.get("reason") or "")[:110]
        })
    return out


def build_feed(analysis, client, now):
    if not valid_analysis(analysis, now) or now >= instant(analysis["reg_close_time"]):
        raise ValueError("Endast aktiv och verifierad Stryktipskupong")
    close = instant(analysis["reg_close_time"])
    season = season_for(close)
    leagues = english_leagues(client, season)
    fixtures = candidate_fixtures(client, leagues, close)
    lines = []
    roster_cache = {}
    injury_cache = {}
    for row in analysis["matches"]:
        item = {
            "number": row["number"], "home": row["home"], "away": row["away"],
            "league": None, "fixture_id": None, "home_feed": {},
            "away_feed": {}
        }
        f = matching_fixture(row, fixtures)
        if not f:
            lines.append(item)
            continue
        item["league"] = f["league"]
        item["fixture_id"] = f["fixture_id"]
        if not f["players_covered"] or not f["injuries_covered"]:
            lines.append(item)
            continue
        for side in ("home", "away"):
            team_id = f[side]["id"]
            item[side + "_feed"] = {"coverage": "missing",
                                  "players_covered": False,
                                  "injuries_covered": False}
            try:
                cachekey = (team_id, f["league_id"], season)
                if cachekey not in roster_cache:
                    roster_cache[cachekey] = get_players(
                        client, team_id, f["league_id"], season)
                if f["fixture_id"] not in injury_cache:
                    injury_cache[f["fixture_id"]] = client.get(
                        "injuries", {"fixture": f["fixture_id"]})["response"]
                # Validate this fixture's injury rows without any extra network calls.
                entries = injury_cache[f["fixture_id"]]
                subset = {"response": entries}
                # Normalize using the same strict player/team/fixture checks.
                absences = []
                seen = set()
                for record in subset["response"]:
                    if ((record.get("fixture") or {}).get("id") != f["fixture_id"]
                        or (record.get("team") or {}).get("id") != team_id):
                        continue
                    player = record.get("player") or {}
                    pid = player.get("id")
                    if type(pid) is not int or pid <= 0 or pid in seen:
                        continue
                    typ = str(player.get("type") or "").lower()
                    reason = str(player.get("reason") or "")[:110]
                    status = (
                        "suspended" if typ == "missing fixture" and "suspend" in reason.lower()
                        else "out" if typ == "missing fixture"
                        else "doubtful" if typ == "questionable" else None
                    )
                    if status:
                        seen.add(pid)
                        absences.append({"player_id": pid, "status": status, "reason": reason})
                item[side + "_feed"] = {
                    "coverage": "verified_provider_feed",
                    "players_covered": True, "injuries_covered": True,
                    "team_id": team_id, "players": roster_cache[cachekey],
                    "absences": absences
                }
            except (ValueError, OSError, TimeoutError) as exc:
                print("Spelarfakta otillgänglig för lag", team_id,
                      type(exc).__name__, file=sys.stderr)
        lines.append(item)
    captured = datetime.now(timezone.utc)
    if captured >= close:
        raise ValueError("API-insamlingen hann inte klart före spelstopp")
    return {
        "schema": SCHEMA, "provider": "API-Football", "provider_docs": SOURCE,
        "draw_number": analysis["draw_number"],
        "source_snapshot_sha256": analysis.get("source_snapshot_sha256"),
        "source_observed_at_utc": analysis["observed_at_utc"],
        "reg_close_time": analysis["reg_close_time"],
        "collected_at_utc": captured.isoformat(), "matches": lines,
        "coverage_warning": "Leverantören garanterar inte komplett skadebevakning. "
                            "Orapporterade spelare är inte verifierat spelklara.",
        "publication_reviewed": True  # Set only behind explicit env approval
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data")
    args = ap.parse_args()
    # Explicit rights gating: API-Football does not grant publication licences itself.
    if os.getenv("PLAYER_DATA_PUBLICATION_APPROVED") != "1":
        print("V17: inga data hämtas förrän publiceringsrättigheter bekräftats")
        return
    key = os.getenv("APIFOOTBALL_KEY")
    if not key:
        print("V17: APIFOOTBALL_KEY saknas, originalmodellen fortsätter oförändrad")
        return
    root = Path(args.outdir)
    now = datetime.now(timezone.utc)
    client = APIClient(key)
    count = 0
    for file in sorted((root/"analysis").glob("*.json")):
        try:
            original = json.loads(file.read_text(encoding="utf-8"))
            if now >= instant(original["reg_close_time"]):
                continue
            dest = root/"player_feed"/file.name
            if dest.exists():
                previous = json.loads(dest.read_text(encoding="utf-8"))
                if instant(previous["collected_at_utc"]).date() == now.date():
                    continue  # one collection per draw/day, avoid blowing API quota
            feed = build_feed(original, client, now)
            write_json(dest, feed)
            count += 1
        except (ValueError, TypeError, KeyError, OSError, TimeoutError,
                json.JSONDecodeError) as exc:
            print("V17: datainsamling avbröts för kupong", file.name,
                  type(exc).__name__, str(exc)[:80], file=sys.stderr)
    print("V17 insamlade engelska kuponger:", count, "API-anrop:", client.calls)


if __name__ == "__main__":
    main()
