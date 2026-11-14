#!/usr/bin/env python3
"""Källkontrollerad spelartillgänglighet – inget automatiskt påhitt om skador.

Optional input data/player_reports/verified.json must contain human-reviewed
source URLs and observation timestamps. No source => UNKNOWN, never available.
The main market model deliberately never changes; a separate test scenario can be generated.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from scripts.analyze import valid_analysis
from scripts.collect import write_json
from scripts.publish import instant
from scripts.league_history import key_team

SCHEMA="stryktipslabbet-player-availability-v1"
ALLOWED={"out","suspended","doubtful"}
LABELS={"out":"Rapporterad frånvaro","suspended":"Avstängd","doubtful":"Osäker medverkan"}


def verify_report(r, observed):
    try:
        if not isinstance(r,dict) or r.get("status") not in ALLOWED:
            return False
        for name in ("team","player","publisher","source_url","reported_at_utc","checked_at_utc"):
            if not isinstance(r.get(name),str) or not r[name].strip():
                return False
        if len(r["player"])>160 or len(r["team"])>160:
            return False
        if not r["source_url"].startswith("https://"):
            return False
        when=instant(r["reported_at_utc"]);checked=instant(r["checked_at_utc"])
        # Source must have been observed independently before the tip snapshot.
        if when>checked or checked>observed or (observed-checked).total_seconds()>7*86400:
            return False
        # No real-world proof can be inferred from metadata alone:
        # only externally checked & timestamped reports are admitted.
        if r.get("verified_by")=="manual_source_review":
            return True
        if r.get("verified_by")=="api_football":
            return (r.get("publisher")=="API-Football" and
                    r.get("source_url","").startswith("https://v3.football.api-sports.io/injuries?fixture=") and
                    type(r.get("provider_fixture_id")) is int and r["provider_fixture_id"]>0 and
                    type(r.get("provider_team_id")) is int and r["provider_team_id"]>0 and
                    type(r.get("match_number")) is int and 1<=r["match_number"]<=13 and
                    type(r.get("draw_number")) is int and r["draw_number"]>0)
        return False
        return True
    except (ValueError,KeyError,TypeError,OverflowError):
        return False


def build(analysis, records, created=None):
    now=created or datetime.now(timezone.utc)
    if not valid_analysis(analysis, now):
        raise ValueError("Ogiltig originalkupong")
    observed=instant(analysis["observed_at_utc"])
    if not observed<=now<instant(analysis["reg_close_time"]):
        raise ValueError("Förhandsuppgifter bara före spelstopp")
    accepted=[r for r in records if verify_report(r,observed)]
    lines=[]
    for m in analysis["matches"]:
        teams=[]
        for side in ("home","away"):
            chosen=[{**r,"status_label":LABELS[r["status"]]}
                    for r in accepted if key_team(r["team"])==key_team(m[side]) and
                    (r.get("draw_number") is None or r["draw_number"]==analysis["draw_number"]) and
                    (r.get("match_number") is None or r["match_number"]==m["number"])]
            chosen.sort(key=lambda x:(x["status"],x["player"]))
            teams.append({"side":side,"team":m[side],
                          "reported_absences":chosen,
                          "coverage":"rapporterade uppgifter finns" if chosen else "ej verifierat – okänt"})
        lines.append({"number":m["number"],"home":teams[0],"away":teams[1]})
    return {
        "schema":SCHEMA,"draw_number":analysis["draw_number"],
        "source_observed_at_utc":analysis["observed_at_utc"],
        "source_snapshot_sha256":analysis.get("source_snapshot_sha256"),
        "reg_close_time":analysis["reg_close_time"],
        "created_at_utc":now.isoformat(),"matches":lines,
        "reports_included":sum(len(team["reported_absences"]) for m in lines for team in (m["home"],m["away"])),
        "coverage_note":"Frånvaro redovisas bara när en källa är kontrollerad. Saknade uppgifter betyder INTE att truppen är skadefri.",
        "model_effect":"Inga spelarskador eller avstängningar används i tipsprognoserna utan ett validerat datamaterial."
    }


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--outdir",default="data")
    args=ap.parse_args();root=Path(args.outdir)
    now=datetime.now(timezone.utc)
    source=root/"player_reports"/"verified.json"
    try:
        doc=json.loads(source.read_text(encoding="utf-8"))
        records=doc.get("reports",[])
        restricted=doc.get("applicable_draw_numbers",[])
        if not isinstance(records,list) or not isinstance(restricted,list):
            raise ValueError("Fel källformat")
    except (OSError,ValueError,TypeError,json.JSONDecodeError):
        records=[]
    # Do not interpret an API fetch after the market observation as
    # information that was known when earlier odds were recorded.
    provider=root/"player_reports"/"provider_latest.json"
    try:
        api=json.loads(provider.read_text(encoding="utf-8"))
        if api.get("schema")!="stryktipslabbet-player-provider-v1":
            api={}
    except (OSError,ValueError,TypeError,json.JSONDecodeError):
        api={}
    n=0
    for f in sorted((root/"analysis").glob("*.json")):
        try:
            base=json.loads(f.read_text(encoding="utf-8"))
            if now>=instant(base["reg_close_time"]):
                continue
            target=root/"player_reports"/"analysis"/f.name
            scoped=records if not restricted or base["draw_number"] in restricted else []
            extra=(api.get("reports",[]) if api.get("draw_number")==base["draw_number"]
                    and api.get("source_snapshot_sha256")==base.get("source_snapshot_sha256")
                    and instant(api["checked_at_utc"])<=instant(base["observed_at_utc"]) else [])
            report=build(base,scoped+extra,now)
            # Historical snapshots are never silently overwritten after close.
            if target.exists():
                old=json.loads(target.read_text(encoding="utf-8"))
                if old["source_observed_at_utc"]==report["source_observed_at_utc"] and old["matches"]==report["matches"]:
                    continue
            write_json(target,report);n+=1
        except (OSError,TypeError,ValueError,KeyError,json.JSONDecodeError) as e:
            print("Spelarstatus hoppades över:",f,str(e),file=sys.stderr)
    print("Verifierade spelarstatusrapporter skapade:",n)


if __name__=="__main__":
    main()
