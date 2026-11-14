#!/usr/bin/env python3
"""Source-linked deep match facts frozen before draw close.

This is *explanatory* football context, not a second predictive model.
The model's odds, signs and staking recommendations do not change.
Uses only match results dated strictly before the source observation day.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone, date
import json
from pathlib import Path
import statistics
import sys

from scripts.analyze import valid_analysis
from scripts.collect import write_json
from scripts.league_history import read_db, key_team, result_for
from scripts.publish import instant

SCHEMA = "stryktipslabbet-match-insights-v1"
VERSION = "2026-11-14-v1"
NATIONAL = "men-national-teams"


def history_index(db):
    index = defaultdict(list)
    for game in db:
        try:
            d = date.fromisoformat(game["date"])
            if (not game.get("home") or not game.get("away") or
                game["home"] == game["away"] or
                not (isinstance(game["home_goals"],int) and isinstance(game["away_goals"],int))):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        index[game["home"]].append(game)
        index[game["away"]].append(game)
    for games in index.values():
        games.sort(key=lambda g:(g["date"], g["home"], g["away"]), reverse=True)
    return index


def last_games(index, team, cutoff, limit=10):
    key = key_team(team)
    out = []
    for game in index.get(key, []):
        if game["date"] >= cutoff:
            continue
        summary = result_for(key, game)
        summary["opponent"] = game["away"] if key == game["home"] else game["home"]
        summary["league"] = game.get("league","okänd")
        summary["season"] = game.get("season")
        summary["neutral"] = bool(game.get("neutral",False))
        summary["opponent_pre_form_ppg"] = opponent_prior_ppg(index, summary["opponent"], game["date"])
        out.append(summary)
        if len(out)>=limit:
            break
    return out


def opponent_prior_ppg(index, team, date_exclusive):
    games = [g for g in index.get(team,[]) if g["date"] < date_exclusive][:5]
    if len(games)<3:
        return None
    return round(sum(result_for(team,g)["points"] for g in games)/len(games),2)


def table_position(db, index, team, cutoff):
    """Approximate current league table from licensed match results.

    Does not account for disciplinary points deductions or postponed matches,
    and must never be described as the federation's official table.
    """
    canonical = key_team(team)
    recent = [g for g in index.get(canonical, [])
              if g["date"] < cutoff and g.get("league") != NATIONAL]
    if not recent:
        return None
    latest = recent[0]
    if (date.fromisoformat(cutoff)-date.fromisoformat(latest["date"])).days > 75:
        return None
    season, league = latest.get("season"), latest.get("league")
    if not season or not league:
        return None
    standings = defaultdict(lambda:{"played":0,"points":0,"gf":0,"ga":0})
    for m in db:
        if m.get("season") != season or m.get("league") != league or m["date"] >= cutoff:
            continue
        h, a = m["home"], m["away"]
        hg, ag = m["home_goals"],m["away_goals"]
        standings[h]["played"]+=1;standings[a]["played"]+=1
        standings[h]["gf"]+=hg;standings[h]["ga"]+=ag
        standings[a]["gf"]+=ag;standings[a]["ga"]+=hg
        if hg>ag: standings[h]["points"]+=3
        elif ag>hg:standings[a]["points"]+=3
        else:
            standings[h]["points"]+=1;standings[a]["points"]+=1
    if canonical not in standings or standings[canonical]["played"]<3:
        return None
    ordered = sorted(standings,key=lambda x:
        (-standings[x]["points"],-(standings[x]["gf"]-standings[x]["ga"]),
         -standings[x]["gf"],x))
    return {"league":league,"season":season,"position":ordered.index(canonical)+1,
            "of_teams":len(ordered),
            "points":standings[canonical]["points"],
            "played":standings[canonical]["played"],
            "goal_difference":standings[canonical]["gf"]-standings[canonical]["ga"],
            "method":"beräknat enbart från källans färdigspelade matcher; ej officiell tabell"}


def team_digest(db,index,team,cutoff):
    games = last_games(index,team,cutoff,10)
    recent5=games[:5]
    last_date = games[0]["date"] if games else None
    days = (date.fromisoformat(cutoff)-date.fromisoformat(last_date)).days if last_date else None
    def streak(predicate):
        n=0
        for g in games:
            if predicate(g):n+=1
            else:break
        return n
    opponents = [x["opponent_pre_form_ppg"] for x in recent5
                 if x["opponent_pre_form_ppg"] is not None]
    return {
        "team":team,
        "last10_matches":games,
        "last_match_date":last_date,
        "days_since_last_match_at_observation":days,
        "matches_last_7_days":sum(
            (date.fromisoformat(cutoff)-date.fromisoformat(x["date"])).days<=7
            for x in games),
        "matches_last_14_days":sum(
            (date.fromisoformat(cutoff)-date.fromisoformat(x["date"])).days<=14
            for x in games),
        "unbeaten_streak":streak(lambda x:x["outcome"]!="F"),
        "winless_streak":streak(lambda x:x["outcome"]!="V"),
        "clean_sheets_last5":sum(x["ga"]==0 for x in recent5),
        "both_scored_last5":sum(x["gf"]>0 and x["ga"]>0 for x in recent5),
        "opponent_pre_form_ppg_last5":round(statistics.mean(opponents),2)
            if len(opponents)>=3 else None,
        "opponent_form_samples":len(opponents),
        "inferred_league_table":table_position(db,index,team,cutoff),
    }


def recent_h2h(index, home, away, cutoff):
    h,a=key_team(home),key_team(away)
    pairs = [m for m in index.get(h,[]) if m["date"]<cutoff
             and ((m["home"]==h and m["away"]==a) or
                  (m["home"]==a and m["away"]==h))][:5]
    return [{"date":m["date"],"home":m["home"],"away":m["away"],
             "home_goals":m["home_goals"],"away_goals":m["away_goals"],
             "competition":m.get("league","okänd")}
            for m in pairs]


def build(base,db,source_files,created=None):
    now = created or datetime.now(timezone.utc)
    if not valid_analysis(base,now):
        raise ValueError("Saknar verifierad förhandskupong")
    obs=instant(base["observed_at_utc"])
    close=instant(base["reg_close_time"])
    if not obs <= now < close:
        raise ValueError("Matchfakta skapas endast efter observation och före stopp")
    cutoff=obs.date().isoformat()
    index=history_index(db)
    out=[]
    for m in base["matches"]:
        out.append({
            "number":m["number"],"home":m["home"],"away":m["away"],
            "home_facts":team_digest(db,index,m["home"],cutoff),
            "away_facts":team_digest(db,index,m["away"],cutoff),
            "head_to_head_last5":recent_h2h(index,m["home"],m["away"],cutoff),
            "odds_p":m["p"],"streck":m["streck"]
        })
    return {
        "schema":SCHEMA,"version":VERSION,
        "draw_number":base["draw_number"],
        "source_observed_at_utc":base["observed_at_utc"],
        "source_snapshot_sha256":base.get("source_snapshot_sha256"),
        "reg_close_time":base["reg_close_time"],
        "created_at_utc":now.isoformat(),
        "cutoff_date_exclusive":cutoff,
        "league_files_read":source_files,
        "sources":[
            {"name":"OpenFootball football.json","license":"CC0-1.0",
             "url":"https://github.com/openfootball/football.json"},
            {"name":"martj42/international_results","license":"CC0-1.0",
             "url":"https://github.com/martj42/international_results"}
        ],
        "matches":out,
        "notes":[
            "Matcher från observationsdagen och senare ingår aldrig.",
            "Vilodagar är dagar sedan senaste dokumenterade match vid observation, inte exakt tid till avspark.",
            "Motståndets poängsnitt är från deras matcher före respektive äldre match; ligor har olika nivå.",
            "Tabellpositioner är härledda från källans matcher utan avdrag/bonus; inte officiella tabeller.",
            "Inga skade-, xG- eller startelvuppgifter ingår; detta justerar inte tipsmodellen."
        ]
    }


def validate(report,base):
    try:
        if report.get("schema")!=SCHEMA or report.get("version")!=VERSION:
            return False
        if (report["draw_number"]!=base["draw_number"] or
            report["source_observed_at_utc"]!=base["observed_at_utc"] or
            report.get("source_snapshot_sha256")!=base.get("source_snapshot_sha256") or
            report["reg_close_time"]!=base["reg_close_time"] or
            report["cutoff_date_exclusive"]!=instant(base["observed_at_utc"]).date().isoformat()):
            return False
        created=instant(report["created_at_utc"])
        if not instant(base["observed_at_utc"])<=created<instant(base["reg_close_time"]):
            return False
        if len(report["matches"])!=13:
            return False
        for r,m in zip(report["matches"],base["matches"]):
            if (r["number"]!=m["number"] or r["home"]!=m["home"] or
                r["away"]!=m["away"] or r["odds_p"]!=m["p"] or
                r["streck"]!=m["streck"]):
                return False
            for side in ("home_facts","away_facts"):
                facts=r[side]
                if len(facts["last10_matches"])>10:
                    return False
                if (facts["last_match_date"] is not None and
                    facts["last_match_date"]>=report["cutoff_date_exclusive"]):
                    return False
                if any(x["date"]>=report["cutoff_date_exclusive"]
                       or x["opponent"]==key_team(facts["team"])
                       for x in facts["last10_matches"]):
                    return False
            if len(r["head_to_head_last5"])>5 or any(
                x["date"]>=report["cutoff_date_exclusive"]
                for x in r["head_to_head_last5"]):
                return False
        return True
    except (KeyError,TypeError,ValueError,OverflowError):
        return False


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--outdir",default="data")
    args=ap.parse_args()
    root=Path(args.outdir)
    db,source_files=read_db(root)
    now=datetime.now(timezone.utc)
    made=0
    for file in sorted((root/"analysis").glob("*.json")):
        try:
            base=json.loads(file.read_text(encoding="utf-8"))
            if now>=instant(base["reg_close_time"]):
                continue
            report=build(base,db,source_files,created=now)
            if not validate(report,base):
                raise ValueError("Felaktigt underlag")
            target=root/"match_insights"/file.name
            if target.exists():
                previous=json.loads(target.read_text(encoding="utf-8"))
                if (previous.get("source_observed_at_utc")==
                      report["source_observed_at_utc"] and previous["matches"]==report["matches"]):
                    continue
                history=root/"match_insights_history"/str(base["draw_number"])/(
                    previous["source_observed_at_utc"].replace(":","_")+".json")
                if not history.exists():
                    write_json(history,previous)
            write_json(target,report)
            made+=1
        except (ValueError,TypeError,KeyError,OSError,json.JSONDecodeError) as exc:
            print("Matchfakta hoppades över:",file,str(exc),file=sys.stderr)
    print("Matchfakta för frysta kuponger:",made)


if __name__=="__main__":
    main()
