"""V34: pre-cutoff team-news intake. Facts are separate from probabilities.
Provider data only with explicit existing credential + publication permission.
No raw responses or credentials persisted. Empty injury responses mean unknown.
"""
import argparse,json,os
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import urlsplit
from scripts.v25_history import read,instant
from scripts.collect import write_json
from scripts.api_football_adapter import APIClient,season_for,english_leagues,candidate_fixtures
from scripts.league_history import key_team

SCHEMA="v34-team-news-intake-v1"
DOCS="https://www.api-football.com/documentation_v3"
STATUSES={"out","suspended","doubtful","available"}
KINDS={"confirmed","predicted","provider_listed"}
def text(s):
    return isinstance(s,str) and bool(s.strip()) and len(s)<=180
def https(url):
    try:
        u=urlsplit(url)
        return u.scheme=="https" and bool(u.hostname) and not u.username and not u.password
    except (ValueError,TypeError):return False

def fixture_map(base,snap,now):
    close=instant(base["reg_close_time"])
    if not instant(base["observed_at_utc"])<=now<close or base["draw_number"]!=snap["draw_number"] or base["reg_close_time"]!=snap["reg_close_time"] or base["source_snapshot_sha256"]!=snap["sha256"] or base["observed_at_utc"]!=snap["observed_at_utc"]:
        raise ValueError("Coupon/snapshot mismatch")
    if len(base["matches"])!=13 or len(snap["matches"])!=13:raise ValueError("Invalid coupon")
    ms={}
    for a,b in zip(base["matches"],snap["matches"]):
        if any(a[k]!=b[k] for k in ("number","home","away")):raise ValueError("Fixture mismatch")
        k=instant(b["match_start"])
        if k<=now:raise ValueError("Match already started")
        ms[a["number"]]={**a,"kickoff":k.isoformat()}
    if set(ms)!=set(range(1,14)):raise ValueError("Invalid positions")
    return ms,close

def valid_entry(r,m,close,now,provider=False):
    try:
        if r["number"]!=m["number"] or (r["home"],r["away"])!=(m["home"],m["away"]) or instant(r["kickoff"])!=instant(m["kickoff"]) or r["side"] not in ("home","away") or r["team"]!=m[r["side"]]:return False
        observed=instant(r["checked_at"]);reported=instant(r["reported_at"])
        if not reported<=observed<=now or observed>=min(close,instant(m["kickoff"])) or now-observed>timedelta(hours=36):return False
        if not https(r["source_url"]) or not text(r["publisher"]):return False
        if provider:
            if r["review_method"]!="provider_feed" or r["publisher"]!="API-Football" or r["source_url"]!=DOCS or type(r["fixture_id"])!=int or r["fixture_id"]<=0:return False
        elif r["review_method"]!="manual_source_review":return False
        if r["type"]=="lineup":
            names=r["players"]
            return r["status"] in (KINDS if provider else {"confirmed","predicted"}) and isinstance(names,list) and len(names)==11 and all(text(x) for x in names) and len({x.strip().casefold() for x in names})==11
        if r["type"]=="absence":
            return text(r["player"]) and r["status"] in STATUSES and isinstance(r.get("reason",""),str) and len(r.get("reason",""))<=180
        return False
    except (KeyError,TypeError,ValueError,OverflowError):return False

def build(base,snap,manual,provider,now):
    ms,close=fixture_map(base,snap,now)
    rows=[]; rejected=0
    for doc,is_provider in ((manual,False),(provider,True)):
        if not doc:continue
        if doc.get("schema")!=SCHEMA or doc.get("draw_number")!=base["draw_number"] or instant(doc["reg_close_time"])!=close or (is_provider and doc.get("publication_reviewed") is not True):
            rejected+=len(doc.get("entries",[]));continue
        for r in doc["entries"]:
            if not isinstance(r,dict):rejected+=1;continue
            m=ms.get(r.get("number"))
            if m and valid_entry(r,m,close,now,is_provider):rows.append(r)
            else:rejected+=1
    matches=[]
    for n,m in sorted(ms.items()):
        sides={}
        for side in ("home","away"):
            items=[r for r in rows if r["number"]==n and r["side"]==side]
            # Do not combine contradictory reports or infer an absence from a missing starter.
            ls=[r for r in items if r["type"]=="lineup"]
            official=[r for r in ls if r["status"]=="confirmed"]
            pool=official or [r for r in ls if r["status"]=="provider_listed"] or ls
            lineup=max(pool,key=lambda x:instant(x["checked_at"])) if pool else None
            conflict=bool(lineup and any(set(x["players"])!=set(lineup["players"]) for x in pool))
            if conflict:lineup=None
            a=defaultdict(list)
            for r in items:
                if r["type"]=="absence":a[r["player"].strip().casefold()].append(r)
            absences=[];conflicts=[]
            starters={x.strip().casefold() for x in lineup["players"]} if lineup and lineup["status"]=="confirmed" else set()
            for name,v in sorted(a.items()):
                statuses={x["status"] for x in v}
                if len(statuses)>1 or (name in starters and statuses&{"out","suspended"}):
                    conflicts.append(v[0]["player"]);continue
                absences.append(max(v,key=lambda x:instant(x["checked_at"])))
            sides[side]={"team":m[side],"lineup":lineup,"lineup_conflict":conflict,"absences":absences,"absence_conflicts":conflicts,"coverage":"reports_found" if absences else "unknown"}
        matches.append({"number":n,"home":m["home"],"away":m["away"],"kickoff":m["kickoff"],"lineup_window_after_cutoff":instant(m["kickoff"])-timedelta(minutes=40)>=close,"sides":sides})
    return {"schema":"v34-team-news-public-v1","draw_number":base["draw_number"],"reg_close_time":close.isoformat(),"generated_at":now.isoformat(),"market_observed_at":base["observed_at_utc"],"provider_status":(provider or {}).get("status","not_collected"),"rejected":rejected,"matches":matches,"coverage":{"confirmed_lineup_teams":sum(s["lineup"] is not None and s["lineup"]["status"]=="confirmed" for m in matches for s in m["sides"].values()),"provider_lineup_teams":sum(s["lineup"] is not None and s["lineup"]["status"]=="provider_listed" for m in matches for s in m["sides"].values()),"absence_reports":sum(len(s["absences"]) for m in matches for s in m["sides"].values())},"model_effect":"0; source review only. Provider lineups are not independently confirmed. Unknown is not healthy. No adjustment to odds, expert model or systems."}

def collect(base,snap,client,now,late):
    ms,close=fixture_map(base,snap,now)
    leagues=english_leagues(client,season_for(close))
    candidates=candidate_fixtures(client,leagues,close)
    entries=[];errors=[]
    def common(m,f,side,at):
        return {"number":m["number"],"home":m["home"],"away":m["away"],"kickoff":m["kickoff"],"side":side,"team":m[side],"fixture_id":f["fixture_id"],"publisher":"API-Football","source_url":DOCS,"checked_at":at.isoformat(),"reported_at":at.isoformat(),"review_method":"provider_feed","timestamp_note":"Provider response observed at this time; original publication time not supplied."}
    for n,m in ms.items():
        fs=[f for f in candidates if key_team(f["home"]["name"])==key_team(m["home"]) and key_team(f["away"]["name"])==key_team(m["away"]) and instant(f["kickoff"])==instant(m["kickoff"])]
        if len(fs)!=1:errors.append({"number":n,"reason":"fixture_missing_or_ambiguous"});continue
        f=fs[0];fid=f["fixture_id"]
        if f["injuries_covered"]:
            try:
                rs=client.get("injuries",{"fixture":fid})["response"];at=datetime.now(timezone.utc)
                for r in rs:
                    if (r.get("fixture") or {}).get("id")!=fid:continue
                    sides=[s for s in ("home","away") if (r.get("team") or {}).get("id")==f[s]["id"]]
                    if len(sides)!=1:continue
                    p=r.get("player") or {};typ=str(p.get("type","")).lower();reason=str(p.get("reason") or "")[:180]
                    status="suspended" if typ=="missing fixture" and "suspend" in reason.lower() else "out" if typ=="missing fixture" else "doubtful" if typ=="questionable" else None
                    if status and text(p.get("name")):
                        entry={**common(m,f,sides[0],at),"type":"absence","player":p["name"],"status":status,"reason":reason}
                        if valid_entry(entry,m,close,at,True):entries.append(entry)
            except (OSError,ValueError,KeyError,TypeError) as e:errors.append({"number":n,"reason":"injury_fetch_failed","class":type(e).__name__})
        if late and instant(m["kickoff"])-now<=timedelta(minutes=90):
            try:
                rs=client.get("fixtures/lineups",{"fixture":fid})["response"];at=datetime.now(timezone.utc)
                for side in ("home","away"):
                    subset=[r for r in rs if (r.get("team") or {}).get("id")==f[side]["id"]]
                    if len(subset)!=1:continue
                    xi=[(p.get("player") or {}).get("name") for p in subset[0].get("startXI",[])]
                    r={**common(m,f,side,at),"type":"lineup","status":"provider_listed","players":xi}
                    if valid_entry(r,m,close,at,True):entries.append(r)
            except (OSError,ValueError,KeyError,TypeError) as e:errors.append({"number":n,"reason":"lineup_fetch_failed","class":type(e).__name__})
        if datetime.now(timezone.utc)>=close:break
    return {"schema":SCHEMA,"draw_number":base["draw_number"],"reg_close_time":base["reg_close_time"],"publication_reviewed":True,"status":"provider_review","entries":entries,"errors":errors,"calls":client.calls}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--outdir",default="data");ap.add_argument("--check-config",action="store_true");a=ap.parse_args()
    key=os.getenv("APIFOOTBALL_KEY");rights=os.getenv("PLAYER_DATA_PUBLICATION_APPROVED")=="1"
    print("V34 CONFIG", "key configured" if key else "key missing", "publication approved" if rights else "publication not approved")
    if a.check_config:return
    data=Path(a.outdir);snap=read(data/"latest.json");now=datetime.now(timezone.utc)
    if not snap:return
    close=instant(snap["reg_close_time"])
    if not now<close or now.date()!=close.date():return
    base=read(data/"analysis"/f'{snap["draw_number"]}.json')
    if not base:return
    path=data/"v34"/"provider"/f'{snap["draw_number"]}.json'
    old=read(path) or {}
    phase="late" if timedelta(minutes=3)<=close-now<=timedelta(minutes=20) else "morning" if timedelta(hours=2)<=close-now<=timedelta(hours=8) else None
    if not phase or phase in old.get("attempted_phases",[]):return
    if not key or not rights:
        print("V34: provider inactive, manual input remains available");return
    # Two distinct attempts, each <= 35 calls; V17 is skipped on this matchday.
    phases=old.get("attempted_phases",[])+[phase]
    marker={"schema":SCHEMA,"draw_number":base["draw_number"],"reg_close_time":base["reg_close_time"],"publication_reviewed":True,"status":"attempt_started","entries":old.get("entries",[]),"attempted_phases":phases}
    write_json(path,marker)
    try:
        doc=collect(base,snap,APIClient(key,max_calls=35),now,phase=="late")
        # Preserve morning news but let the latest provider response replace the
        # exact same player's status. No extra inference from an empty response.
        combined={}
        for r in old.get("entries",[])+doc["entries"]:
            k=(r["number"],r["side"],r["type"],r.get("player","").casefold())
            combined[k]=r
        doc["entries"]=list(combined.values());doc["attempted_phases"]=phases
        write_json(path,doc);print("V34",phase,"rows",len(doc["entries"]),"calls",doc["calls"])
    except (OSError,ValueError,KeyError,TypeError) as e:
        marker["status"]="provider_error";write_json(path,marker);print("V34 provider error",type(e).__name__)
if __name__=="__main__":main()
