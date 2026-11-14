#!/usr/bin/env python3
"""Optional API-Football ingestion for the existing GitHub Actions pipeline.

The API key is read from a GitHub Actions secret, never stored in published
HTML or git. No key, no live claims. Fixture matching requires BOTH team
identities and a kickoff time match; uncertain matches are skipped.
"""
import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.collect import write_json
from scripts.league_history import key_team
from scripts.publish import instant

BASE="https://v3.football.api-sports.io"
MAX_CALLS=50


class API:
    def __init__(self,key):
        self.key=key
        self.calls=0
    def get(self,path,params):
        if self.calls>=MAX_CALLS:
            raise RuntimeError("Källans anropsgräns nådd")
        self.calls+=1
        url=BASE+path+"?"+urlencode(params)
        req=Request(url,headers={"x-apisports-key":self.key,
                                  "Accept":"application/json",
                                  "User-Agent":"Stryktipslabbet/17 (read only)"})
        with urlopen(req,timeout=14) as response:
            raw=response.read(2_000_001)
        if len(raw)>2_000_000:
            raise ValueError("För stort API-svar")
        data=json.loads(raw)
        if not isinstance(data,dict) or data.get("errors"):
            raise ValueError("API-Football saknar tillgång eller har ett källfel")
        return data.get("response") or [],data


def resolve_fixture(match, fixtures):
    """Only unambiguous exact canonical home+away and kickoff within 4h."""
    if not match.get("match_start"):
        return None
    kickoff=instant(match["match_start"])
    wanted=(key_team(match["home"]),key_team(match["away"]))
    found=[]
    for f in fixtures:
        try:
            home=f["teams"]["home"]
            away=f["teams"]["away"]
            actual=(key_team(home["name"]),key_team(away["name"]))
            start=instant(f["fixture"]["date"])
            if (wanted==actual and
                abs((kickoff-start).total_seconds()) <= 4*3600 and
                int(f["fixture"]["id"])>0):
                found.append(f)
        except (KeyError,TypeError,ValueError,OverflowError):
            pass
    return found[0] if len(found)==1 else None


def player_statistics(api,team_id,league_id,season):
    """Complete pagination only. No quantitative importance from partial roster."""
    roster=[]
    first,meta=api.get("/players",{"team":team_id,"league":league_id,
                                  "season":season,"page":1})
    pages=int((meta.get("paging") or {}).get("total") or 1)
    if pages>5 or pages<1:
        return {}
    roster.extend(first)
    for p in range(2,pages+1):
        extra,_=api.get("/players",{"team":team_id,"league":league_id,
                                   "season":season,"page":p})
        roster.extend(extra)
    stats={}
    team_games=0
    for entry in roster:
        try:
            st=next(s for s in entry["statistics"] if int(s["league"]["id"])==int(league_id))
            g=st["games"]
            apps=int(g.get("appearences") or g.get("appearances") or 0)
            team_games=max(team_games,apps)
        except (KeyError,ValueError,TypeError,StopIteration):
            continue
    for entry in roster:
        try:
            st=next(s for s in entry["statistics"] if int(s["league"]["id"])==int(league_id))
            g=st["games"]
            pid=int(entry["player"]["id"])
            stats[pid]={"starts":int(g.get("lineups") or 0),
                        "appearances":int(g.get("appearences") or g.get("appearances") or 0),
                        "minutes":int(g.get("minutes") or 0),
                        "team_matches":team_games,
                        "goals":int((st.get("goals") or {}).get("total") or 0),
                        "assists":int((st.get("goals") or {}).get("assists") or 0),
                        "position":g.get("position"),
                        "season":season,"complete":True}
        except (KeyError,ValueError,TypeError,StopIteration):
            pass
    return stats


def injury_status(entry):
    player=entry.get("player") or {}
    label=(str(player.get("type") or "")+" "+str(player.get("reason") or "")).lower()
    if "suspend" in label or "ban" in label or "red card" in label:
        return "suspended"
    if "doubt" in label or "question" in label or "uncertain" in label:
        return "doubtful"
    return "out"


def collect(root, api, now):
    snapshot=json.loads((root/"latest.json").read_text(encoding="utf-8"))
    n=snapshot["draw_number"]
    analysis=json.loads((root/"analysis"/(str(n)+".json")).read_text(encoding="utf-8"))
    if (analysis["observed_at_utc"]!=snapshot["observed_at_utc"]
        or analysis.get("source_snapshot_sha256")!=snapshot.get("sha256")
        or now>=instant(snapshot["reg_close_time"])):
        raise ValueError("Ingen aktuell, sammanhängande förhandskupong")
    matches=[m for m in snapshot["matches"] if m.get("match_start")]
    dates=set()
    for m in matches:
        dt=instant(m["match_start"])
        # API-Football's UTC date may differ from the local kickoff date.
        dates.add(dt.date().isoformat())
        dates.add(str(m["match_start"])[:10])
    if len(dates)>6:
        raise ValueError("Orimligt många matchdatum")
    fixtures=[]
    for d in sorted(dates):
        try:
            fetched,_=api.get("/fixtures",{"date":d})
            fixtures.extend(fetched)
        except (ValueError,OSError,RuntimeError):
            continue
    reports=[]
    matched=0
    incomplete=0
    cache={}
    for m in matches:
        fixture=resolve_fixture(m,fixtures)
        if fixture is None:
            incomplete+=1
            continue
        matched+=1
        fid=int(fixture["fixture"]["id"])
        league=fixture["league"]
        league_id=int(league["id"])
        season=int(league["season"])
        try:
            injured,_=api.get("/injuries",{"fixture":fid})
        except (OSError,ValueError,RuntimeError):
            incomplete+=1
            continue
        if not isinstance(injured,list):
            continue
        for side in ("home","away"):
            team=fixture["teams"][side]
            tid=int(team["id"])
            relevant=[r for r in injured
                      if isinstance(r,dict) and (r.get("team") or {}).get("id")==tid]
            if not relevant:
                continue
            roster_key=(tid,league_id,season)
            if roster_key not in cache:
                try:
                    cache[roster_key]=player_statistics(api,*roster_key)
                except (OSError,TypeError,ValueError,RuntimeError):
                    cache[roster_key]={}
            for entry in relevant:
                person=entry.get("player") or {}
                pid=person.get("id")
                if not pid or not person.get("name"):
                    continue
                reports.append({
                    "draw_number":n,"match_number":m["number"],
                    "team":m[side],"player":str(person["name"]),
                    "provider_player_id":int(pid),"provider_team_id":tid,
                    "provider_fixture_id":fid,
                    "status":injury_status(entry),
                    "publisher":"API-Football",
                    "source_url":BASE+"/injuries?fixture="+str(fid),
                    "reported_at_utc":now.isoformat(),
                    "checked_at_utc":now.isoformat(),
                    "verified_by":"api_football",
                    "stats":cache[roster_key].get(int(pid)),
                    "notes":"Leverantörens skade-/avstängningslista, kontrollerad vid angiven tid. Ingen garanti för spelstatus eller oddsjustering."
                })
    doc={"schema":"stryktipslabbet-player-provider-v1",
         "provider":"API-Football","draw_number":n,
         "source_observed_at_utc":snapshot["observed_at_utc"],
         "source_snapshot_sha256":analysis.get("source_snapshot_sha256"),
         "checked_at_utc":now.isoformat(),
         "fixtures_matched":matched,
         "fixtures_unmatched_or_incomplete":incomplete,
         "reports":reports,
         "coverage_note":"Tom lista är INTE bevis för att alla spelare är tillgängliga."}
    target=root/"player_reports"/"provider_latest.json"
    write_json(target,doc)
    return doc


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--outdir",default="data")
    root=Path(parser.parse_args().outdir)
    key=os.environ.get("API_FOOTBALL_KEY","").strip()
    if not key:
        print("API_FOOTBALL_KEY saknas: bara källgranskad manuell frånvaro används.")
        return
    try:
        report=collect(root,API(key),datetime.now(timezone.utc))
        print("API-Football matchningar:",report["fixtures_matched"],
              "osäkra/ej täckta:",report["fixtures_unmatched_or_incomplete"],
              "rapporter:",len(report["reports"]))
    except (OSError,ValueError,KeyError,TypeError,RuntimeError,json.JSONDecodeError) as e:
        print("Spelarleverantören kunde inte uppdateras:",str(e),file=sys.stderr)


if __name__=="__main__":
    main()
