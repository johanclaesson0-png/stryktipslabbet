#!/usr/bin/env python3
"""V18: Compare fixed count-of-absences vs strictly prior-games minutes/starts.

All API responses, athlete identifiers and injured players remain ephemeral.
Historical absence records have no verified published-before-close timestamps,
so this is *retrospective sensitivity*, NOT a valid pre-close backtest.
"""
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

from scripts.api_football_historical_backtest import (
    APIClient, ROOT, adjust, dataset_from_api, elbow_snapshots, score, SIGNS,
)
from scripts.history5 import read_rounds
from scripts.analyze import optimize, correct_rows, selected_signs
from scripts.feature_model import optimize_exact

PRIOR_GAMES=3
MIN_VERIFIED_PRIOR_GAMES=2
WEIGHT_PER_FULL_IMPORTANCE=.065
QUESTIONABLE_FACTOR=.40
MAX_SIGNAL=.20


def prior_fixture_ids(catalog, team_id, target_date, max_games=PRIOR_GAMES):
    """Strictly older *dates*, never same-day or post-match player statistics."""
    items={}
    for matches in catalog.values():
        for f in matches:
            if f.get("played") and f.get("date") < target_date and (
                f.get("home_id")==team_id or f.get("away_id")==team_id):
                items[f["id"]]=f
    ordered=sorted(items.values(), key=lambda f:(f["date"],f["id"]),reverse=True)
    return [f["id"] for f in ordered[:max_games]]


def read_prior_minutes(client, fixture_id, team_id, cache):
    """Fixtures/players: only minutes and starting-XI status of games already played."""
    if fixture_id not in cache:
        cache[fixture_id]=client.get("fixtures/players",{"fixture":fixture_id})
    response=cache[fixture_id]
    result={}
    for row in response:
        if (row.get("team") or {}).get("id")!=team_id:
            continue
        for x in row.get("players") or []:
            player=x.get("player") or {}
            pid=player.get("id")
            stats=x.get("statistics") or []
            if type(pid) is not int or len(stats)!=1:
                continue
            games=(stats[0].get("games") or {})
            minutes=games.get("minutes")
            substitute=games.get("substitute")
            if (type(minutes) not in (int,float) or minutes<0 or minutes>130
                or type(substitute) is not bool):
                continue
            result[pid]=(float(minutes),int(minutes>0 and not substitute))
    return result


def importance_from_past_games(samples, min_games=MIN_VERIFIED_PRIOR_GAMES):
    """Relative team-importance; rank only on observations strictly before kickoff.

    Returns None on inadequate team-level history. For absent players with no
    recorded past appearance, caller must mark importance UNKNOWN, not zero.
    """
    if len(samples)<min_games or sum(bool(s) for s in samples)<min_games:
        return None
    totals=defaultdict(lambda:[0.,0,0])
    for sample in samples:
        for pid,(minutes,start) in sample.items():
            if type(pid) is not int or not(0<=minutes<=130 and start in (0,1)):
                continue
            vals=totals[pid]
            vals[0]+=minutes; vals[1]+=start; vals[2]+=1
    if len(totals)<8:
        return None
    max_minutes=max(v[0] for v in totals.values())
    max_starts=max(v[1] for v in totals.values())
    if max_minutes<=0 or max_starts<=0:
        return None
    return {pid:round(.55*val[0]/max_minutes+.45*val[1]/max_starts,6)
            for pid,val in totals.items() if val[2]>=1}


def absence_impact(rows,team_id,importance):
    """Weighted impact, or None if ANY reported injured player lacks past data."""
    if importance is None:
        return None
    seen=set()
    impact=0.
    for r in rows:
        if (r.get("team") or {}).get("id")!=team_id:
            continue
        player=r.get("player") or {}
        pid=player.get("id")
        if type(pid) is not int:
            return None
        typ=str(player.get("type") or "").lower().strip()
        if typ not in ("missing fixture","questionable") or pid in seen:
            continue
        seen.add(pid)
        if pid not in importance:
            return None
        impact+=importance[pid]*(QUESTIONABLE_FACTOR if typ=="questionable" else 1.)
    return impact


def weighted_sensitivity(p,home_impact,away_impact):
    """Same fixed weight for all periods, not fitted to test match outcomes."""
    signal=max(-MAX_SIGNAL,min(MAX_SIGNAL,
                WEIGHT_PER_FULL_IMPORTANCE*(away_impact-home_impact)))
    weights=[p[0]*math.exp(signal),p[1]*math.exp(-.12*abs(signal)),
             p[2]*math.exp(-signal)]
    z=sum(weights)
    return [x/z for x in weights]


def evaluate(client,rounds,batch_index=1):
    base=elbow_snapshots(rounds)
    matched,counts,coverage,catalog,injuries=dataset_from_api(
        client,rounds,batch_index=batch_index,per_group=1,return_catalog=True)
    fixture_players_cache={}
    roster_cache={}
    rows=[]
    by_draw=defaultdict(dict)
    for draw in rounds:
        for i,m in enumerate(draw["matches"]):
            f=matched.get((draw["draw"],i))
            if f is None:
                continue
            past_rosters=[]
            raw=injuries.get(f["id"],[])
            for side in ("home","away"):
                tid=f[side+"_id"]
                has_reported=any((r.get("team") or {}).get("id")==tid and
                    str((r.get("player") or {}).get("type","")).lower() in
                    ("missing fixture","questionable") for r in raw)
                if not has_reported:
                    past_rosters.append(0.)
                    continue
                key=(tid,f["date"],f["id"])
                if key not in roster_cache:
                    ids=prior_fixture_ids(catalog,tid,f["date"])
                    samples=[]
                    for pid in ids:
                        try:
                            samples.append(read_prior_minutes(client,pid,tid,fixture_players_cache))
                        except RuntimeError:
                            samples.append({})
                    roster_cache[key]=importance_from_past_games(samples)
                past_rosters.append(absence_impact(raw,tid,roster_cache[key]))
            home_w,away_w=past_rosters
            original=base[draw["draw"]][i]
            injury=counts.get(f["id"],{})
            h=injury.get(f["home_id"],{})
            a=injury.get(f["away_id"],{})
            count_p=adjust(original,h.get("out",0),a.get("out",0),
                           h.get("doubtful",0),a.get("doubtful",0))
            if home_w is None or away_w is None:
                # Never pretend a missing player's prior stats imply no impact.
                rows.append({"draw":draw["draw"],"coverage":"missing_prior_stats"})
                continue
            weighted=weighted_sensitivity(original,home_w,away_w)
            b,lb,ab=score(original,m["outcome"])
            c,lc,ac=score(count_p,m["outcome"])
            w,lw,aw=score(weighted,m["outcome"])
            rows.append({"draw":draw["draw"],"coverage":"verified_prior_games",
                         "baseline_brier":b,"count_brier":c,"weighted_brier":w,
                         "baseline_logloss":lb,"count_logloss":lc,
                         "weighted_logloss":lw,
                         "baseline_top1":ab,"count_top1":ac,"weighted_top1":aw,
                         "changed":abs(home_w-away_w)>1e-12})
            by_draw[draw["draw"]][i]=weighted
    eligible=[r for r in rows if r["coverage"]=="verified_prior_games"]
    report={"schema":"stryktipslabbet-retrospective-player-weights-v18",
            "sample_batch":batch_index,
            "source_coverage":"Retrospective injuries, NOT verified known before historic close",
            "prior_game_rule":"Strictly earlier fixture calendar dates; max three team fixtures",
            "selected_matches":len(matched),"evaluated_with_past_stats":len(eligible),
            "missing_or_unknown_prior_stats":len(rows)-len(eligible),
            "api_calls":client.calls,"seasons":[2022,2023,2024]}
    if eligible:
        for metric in ("brier","logloss","top1"):
            for model in ("baseline","count","weighted"):
                report[model+"_"+metric]=round(sum(r[model+"_"+metric] for r in eligible)/len(eligible),6)
        report["net_brier_improvement"]=round(report["baseline_brier"]-report["weighted_brier"],6)
    report["system_checks"]=[]
    # Keep every preexisting coupon probability unchanged unless valid prior
    # reports cover the specific match; then recompute EXACT baseline row cost.
    for draw in rounds:
        indexed=by_draw.get(draw["draw"],{})
        if not indexed or not any(
           indexed[i] != base[draw["draw"]][i] for i in indexed):
            continue
        alternative=[indexed.get(i,p) for i,p in enumerate(base[draw["draw"]])]
        actual="".join(m["outcome"] for m in draw["matches"])
        entry={"draw":draw["draw"],"n_weighted_matches":len(indexed)}
        for budget in (100,1800):
            cost,masks=optimize(base[draw["draw"]],budget)
            weighted_masks=optimize_exact(alternative,cost)
            assert math.prod(m.bit_count() for m in weighted_masks)==cost
            original=[selected_signs(m) for m in masks]
            revised=[selected_signs(m) for m in weighted_masks]
            count0=correct_rows(original,actual)
            count1=correct_rows(revised,actual)
            entry[str(budget)]={"cost":cost,
                "changed_matches":sum(a!=b for a,b in zip(original,revised)),
                "original_hits":{str(k):int(count0[k]>0) for k in (10,11,12,13)},
                "weighted_hits":{str(k):int(count1[k]>0) for k in (10,11,12,13)}}
        report["system_checks"].append(entry)
    # Safe aggregate only: no provider player/fixture identities, personal data
    print("WEIGHTED_BACKTEST:",json.dumps(report,ensure_ascii=False,sort_keys=True))
    return report


def main():
    key=os.getenv("APIFOOTBALL_KEY")
    if not key:
        raise SystemExit("APIFOOTBALL_KEY missing")
    idx=int(os.getenv("WEIGHTED_BATCH_INDEX","1"))
    client=APIClient(key,max_calls=85)
    rounds=read_rounds(ROOT/"data/history/stryktipset-five-years.csv")
    result=evaluate(client,rounds,idx)
    if not result["evaluated_with_past_stats"]:
        raise SystemExit("No evaluable strictly prior-game stats: do not claim model improvement")


if __name__=="__main__":
    main()
