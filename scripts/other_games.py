#!/usr/bin/env python3
"""V16: independent read-only Topptipset / Europatipset observations and models.

The product-specific public API data MUST validate before being displayed.
No Stryktipset fixtures, line counts or settlements are silently substituted.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen

from scripts.analyze import probabilities, search_probabilities, selected_signs
from scripts.collect import triplet, write_json, utc
from scripts.publish import instant

ROOT = "https://api.spela.svenskaspel.se/draw/1/"
SCHEMA = "stryktipslabbet-other-game-v16"
RESULT_SCHEMA = "stryktipslabbet-other-game-result-v16"
SETTLED_SCHEMA = "stryktipslabbet-other-game-settlement-v16"
CATEGORIES = {
    "topptipset": {"list_path":"topptipsetfamily", "detail_paths":["topptipsetfamily","topptipset"],
                    "matches":8,"outcome_prizes":[8],"label":"Topptipset"},
    "europatipset": {"list_path":"europatipset", "detail_paths":["europatipset"],
                    "matches":13,"outcome_prizes":[10,11,12,13],"label":"Europatipset"},
}
STATES = ("Open","NotOpened","Upcoming")


def fetch(relative):
    url=ROOT + relative.lstrip("/")
    request=Request(url,headers={"Accept":"application/json",
           "User-Agent":"Stryktipslabbet/16.0 (public read-only analysis)"})
    with urlopen(request, timeout=16) as response:
        raw=response.read(1_500_001)
        if response.status!=200 or len(raw)>1_500_000:
            raise ValueError("Ogiltigt API-svar eller för stora data")
    return json.loads(raw),raw,url


def family_matches(game, name):
    normalized=" ".join(str(name).casefold().split())
    if game=="europatipset":
        return normalized=="europatipset"
    return normalized.startswith("topptipset") or normalized.startswith("topptips ")


def draw_list(doc, game, now):
    entries=doc.get("draws") if isinstance(doc,dict) else doc
    if not isinstance(entries,list):
        raise ValueError("Oväntat format för öppna omgångar")
    candidates=[]
    for x in entries:
        try:
            if (not isinstance(x,dict) or not family_matches(game,x["productName"]) or
                x.get("drawState") not in STATES or
                utc(x["regCloseTime"]) <= now):
                continue
            number=int(x["drawNumber"])
            if number>0:
                candidates.append((utc(x["regCloseTime"]),number,x))
        except (ValueError,KeyError,TypeError):
            continue
    return sorted(candidates,key=lambda x:(x[0],x[1]))[:3]


def parse_draw(doc,game,number,now,url,raw):
    config=CATEGORIES[game]
    entry=doc.get("draw") if isinstance(doc,dict) and "draw" in doc else doc
    if not isinstance(entry,dict) or str(entry.get("drawNumber"))!=str(number):
        raise ValueError("Fel nummer")
    if not family_matches(game,entry.get("productName","")):
        raise ValueError("Fel spelprodukt")
    close=utc(entry["regCloseTime"])
    if entry.get("drawState") not in STATES or not now < close:
        raise ValueError("Omgång ej spelbar")
    events=entry.get("drawEvents")
    n=config["matches"]
    if not isinstance(events,list) or len(events)!=n:
        raise ValueError("Ej komplett kupong")
    if sorted(int(x.get("eventNumber",0)) for x in events)!=list(range(1,n+1)):
        raise ValueError("Saknar unika matcher")
    matches=[]
    for x in sorted(events,key=lambda x:x["eventNumber"]):
        m=x.get("match") or {}
        if x.get("cancelled") or m.get("sportEventStatus") in (
            "Started","InProgress","Finished","Cancelled"):
            raise ValueError("Matchen påbörjad/inställd")
        names={}
        for side in ("home","away"):
            people=[p.get("name") for p in m.get("participants",[])
                    if isinstance(p,dict) and p.get("type")==side]
            if len(people)!=1 or not isinstance(people[0],str) or not people[0].strip():
                raise ValueError("Ogiltigt lag")
            names[side]=people[0].strip()
        if names["home"]==names["away"]:
            raise ValueError("Samma hemmalag/bortalag")
        start=m.get("matchStart")
        if start and utc(start)<=now:
            raise ValueError("Match har börjat")
        # A real future fixture may be listed before valid odds are offered.
        # Keep the fixture but NEVER invent 1X2 probabilities or a system.
        try:
            odds=triplet(x.get("odds"),"odds")
            p=[round(v,9) for v in probabilities(odds)]
        except (ValueError, TypeError):
            odds=None
            p=None
        streck=triplet(x.get("svenskaFolket"),"streck")
        matches.append({"number":int(x["eventNumber"]),
                        "home":names["home"],"away":names["away"],
                        "odds":odds,"streck":streck,"p":p,
                        "match_start":start})
    return {"schema":SCHEMA,"game":game,"name":str(entry["productName"]),
            "draw_number":int(number),"reg_close_time":close.isoformat(),
            "observed_at_utc":now.isoformat(),"source_url":url,
            "source_snapshot_sha256":sha256(raw).hexdigest(),
            "with_valid_odds":sum(m["p"] is not None for m in matches),
            "matches":matches}


def optimize_n(ps,budget):
    n=len(ps)
    if n not in (8,13) or not 1<=budget<=1800:
        raise ValueError("Fel spel eller budget")
    dp={1:(0.,())}
    for p in ps:
        nx={}
        for cost,(score,ms) in dp.items():
            for mask in range(1,8):
                new=cost*mask.bit_count()
                if new>budget:
                    continue
                mass=sum(p[j] for j in range(3) if mask&(1<<j))
                candidate=(score+math.log(mass),ms+(mask,))
                if new not in nx or candidate[0]>nx[new][0]:
                    nx[new]=candidate
        dp=nx
    return max(dp.items(),key=lambda q:q[1][0])


def analyze(snapshot,now):
    if snapshot.get("schema")!=SCHEMA:
        raise ValueError("Ingen godkänd kupong")
    created=instant(now)
    if not instant(snapshot["observed_at_utc"])<=created<instant(snapshot["reg_close_time"]):
        raise ValueError("Efter spelstopp")
    ms=snapshot["matches"];n=CATEGORIES[snapshot["game"]]["matches"]
    if len(ms)!=n or len({x["number"] for x in ms})!=n:
        raise ValueError("Ofullständig kupong")
    complete=all(m["p"] is not None for m in ms)
    budgets=([100] if n==8 else [100,1800]) if complete else []
    profiles=[]
    for budget in budgets:
        for key,exponent in (("balanserad",0),("streckvarde",.45)):
            scores=[search_probabilities(m["p"],[x/sum(m["streck"]) for x in m["streck"]],exponent)
                    for m in ms]
            cost,(score,masks)=optimize_n(scores,budget)
            choices=[selected_signs(x) for x in masks]
            actual=math.prod(sum(p for j,p in enumerate(m["p"]) if "1X2"[j] in c)
                             for m,c in zip(ms,choices))
            profiles.append({"budget_limit":budget,"profile":key,"cost":cost,
                             "choices":choices,"estimated_all_correct":round(actual,10)})
    return {"schema":"stryktipslabbet-other-game-analysis-v16",
            "game":snapshot["game"],"name":snapshot["name"],
            "draw_number":snapshot["draw_number"],
            "matches":ms,
            "observed_at_utc":snapshot["observed_at_utc"],
            "source_snapshot_sha256":snapshot["source_snapshot_sha256"],
            "reg_close_time":snapshot["reg_close_time"],
            "created_at_utc":created.isoformat(),"systems":profiles,
            "complete_odds":complete,
            "note":("Hypotetiska matematiska system; ej inlämnade och ingen bevisad överavkastning."
                    if complete else "Verklig kupong men otillräckliga odds för systemförslag.")}


def distribution(choices,outcome):
    dp=[1]
    for c,s in zip(choices,outcome):
        good=int(s in c);nextv=[0]*(len(dp)+1)
        for i,v in enumerate(dp):
            nextv[i]+=(len(c)-good)*v
            nextv[i+1]+=good*v
        dp=nextv
    return dp


def parse_result(doc,game,number,now,url,raw):
    data=doc.get("result") if isinstance(doc,dict) else None
    if not isinstance(data,dict) or str(data.get("drawNumber"))!=str(number) or not family_matches(game,data.get("productName")):
        raise ValueError("Fel facitprodukt")
    n=CATEGORIES[game]["matches"]
    ev=data.get("events")
    if not isinstance(ev,list) or len(ev)!=n:
        raise ValueError("Ofullständigt facit")
    if sorted(e.get("eventNumber") for e in ev)!=list(range(1,n+1)):
        raise ValueError("Fel matchnummer")
    outcomes="".join(str(e["outcome"]).upper() for e in sorted(ev,key=lambda e:e["eventNumber"]))
    if len(outcomes)!=n or any(c not in "1X2" for c in outcomes):
        raise ValueError("Ogiltiga tecken")
    payouts={}
    import re
    for entry in data.get("distribution") or []:
        found=re.fullmatch(r"(\d{1,2}) r[äa]tt",str(entry.get("name","")).strip(),re.I)
        if found and int(found[1]) in CATEGORIES[game]["outcome_prizes"]:
            x=float(str(entry.get("amount")).replace(",",".")) # avoid money if invalid
            if not math.isfinite(x) or x<0 or x>1e10:
                raise ValueError("Ogiltig utdelning")
            payouts[found[1]]=x
    if set(payouts)!=set(str(i) for i in CATEGORIES[game]["outcome_prizes"]):
        raise ValueError("Utdelning ej officiellt verifierad")
    return {"schema":RESULT_SCHEMA,"game":game,"draw_number":number,
            "observed_at_utc":now.isoformat(),"source_url":url,
            "sha256":sha256(raw).hexdigest(),"outcome":outcomes,"payouts":payouts}


def settlement(analysis,result):
    if (result["game"]!=analysis["game"] or result["draw_number"]!=analysis["draw_number"] or
        instant(analysis["created_at_utc"])>=instant(analysis["reg_close_time"]) or
        instant(result["observed_at_utc"])<instant(analysis["reg_close_time"])):
        raise ValueError("Facit matchar inte")
    statuses=[]
    for system in analysis["systems"]:
        counts=distribution(system["choices"],result["outcome"])
        paid=sum(counts[i]*result["payouts"][str(i)] for i in CATEGORIES[result["game"]]["outcome_prizes"])
        statuses.append({"budget_limit":system["budget_limit"],"profile":system["profile"],
                         "cost":system["cost"],
                         "all_correct_rows":counts[len(result["outcome"])],
                         "covered_matches":sum(s in c for s,c in zip(result["outcome"],system["choices"])),
                         "paid":round(paid,2),"net":round(paid-system["cost"],2)})
    return {"schema":SETTLED_SCHEMA,"game":result["game"],"draw_number":result["draw_number"],
            "source_snapshot_sha256":analysis["source_snapshot_sha256"],
            "official_result_sha256":result["sha256"],"observed_at_utc":analysis["observed_at_utc"],
            "outcome":result["outcome"],"payouts":result["payouts"],
            "hypothetical":True,"systems":statuses}


def collect_product(data,game,now):
    config=CATEGORIES[game];folder=data/"other_games"/game
    doc,raw,url=fetch(config["list_path"]+"/draws")
    found=draw_list(doc,game,now)
    if not found:
        print("V16:",game,"ingen identifierad öppen omgång")
        return 0
    imported=0
    for close,num,entry in found:
        latest=folder/"latest.json"
        current=None
        try:current=json.loads(latest.read_text(encoding="utf-8"))
        except (ValueError,OSError):pass
        if (current and current.get("draw_number")==num and
            (now-utc(current["observed_at_utc"])).total_seconds()<1800):
            continue
        attempts=[(dict(entry),raw,url)]
        for detail in config["detail_paths"]:
            try:
                payload,source,sourceurl=fetch(detail+"/draws/"+str(num))
                attempts.insert(0,(payload,source,sourceurl))
                break
            except (ValueError, OSError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
                print("V16 detaljer saknas:",detail,num,str(exc)[:120],file=sys.stderr)
        snapshot=None
        for candidate,by,sourceurl in attempts:
            try:
                snapshot=parse_draw(candidate,game,num,datetime.now(timezone.utc),sourceurl,by)
                break
            except (ValueError,KeyError,TypeError) as exc:
                print("V16 ogiltig kupong:",game,num,str(exc)[:120],file=sys.stderr)
        if snapshot is None:
            continue
        hashpart=snapshot["source_snapshot_sha256"][:12]
        observed=instant(snapshot["observed_at_utc"])
        name=observed.strftime("%Y%m%dT%H%M%SZ")+"-"+hashpart+".json"
        path=folder/"snapshots"/str(num)/name
        if not path.exists():
            write_json(path,snapshot)
        write_json(latest,snapshot)
        derived=analyze(snapshot,datetime.now(timezone.utc))
        write_json(folder/"analysis"/(str(num)+".json"),derived)
        imported+=1
        time.sleep(.1)
    # "latest" must mean the nearest upcoming draw, not whichever family draw
    # happened to be processed last.
    available=[]
    for close,num,_entry in found:
        folder_for_draw=folder/"snapshots"/str(num)
        for candidate in sorted(folder_for_draw.glob("*.json"), reverse=True)[:1]:
            try:
                payload=json.loads(candidate.read_text(encoding="utf-8"))
                if (payload.get("game")==game and
                    payload.get("draw_number")==num and
                    instant(payload["observed_at_utc"])<close):
                    available.append((close,num,payload))
            except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError):
                pass
    if available:
        available.sort(key=lambda item:(item[0],item[1]))
        write_json(folder/"latest.json",available[0][2])
    return imported


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--outdir",default="data")
    args=ap.parse_args();root=Path(args.outdir)
    for game in CATEGORIES:
        try:
            count=collect_product(root,game,datetime.now(timezone.utc))
            print("V16:",game,"nya kuponger",count)
        except Exception as exc:
            print("V16:",game,"källa ej tillgänglig:",type(exc).__name__,str(exc)[:130],file=sys.stderr)
        folder=root/"other_games"/game
        for f in sorted((folder/"analysis").glob("*.json"))[-5:]:
            try:
                n=int(f.stem)
                if (folder/"settlements"/f.name).exists():continue
                analysis_doc=json.loads(f.read_text(encoding="utf-8"))
                if instant(analysis_doc["reg_close_time"])>=datetime.now(timezone.utc):
                    continue
                result=None
                for source in CATEGORIES[game]["detail_paths"]:
                    try:
                        doc,raw,url=fetch(source+"/draws/"+str(n)+"/result")
                        result=parse_result(doc,game,n,datetime.now(timezone.utc),url,raw)
                        break
                    except (ValueError,OSError,TimeoutError,KeyError,TypeError) as exc:
                        print("V16 facit ännu ej verifierat:",game,n,str(exc)[:110],file=sys.stderr)
                if result:
                    write_json(folder/"results"/f.name,result)
                    write_json(folder/"settlements"/f.name,settlement(analysis_doc,result))
            except (ValueError,OSError,TypeError,KeyError,json.JSONDecodeError) as exc:
                print("V16 rättning hoppades över:",game,str(exc)[:110],file=sys.stderr)


if __name__=="__main__":
    main()
