#!/usr/bin/env python3
"""Retrospective, aggregated API-Football absence sensitivity against 2021-26 Elo.

Exploratory only: retrospectively recovered absence reports have NO verified
historical publication timestamp. Do not represent these observations as
pre-close knowledge, confirmed 1/X/2 performance, or gambling returns.

All provider responses remain in ephemeral GitHub Actions memory and are
neither written to data/ nor published to GitHub Pages.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import random
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.analyze import correct_rows, optimize, selected_signs
from scripts.feature_model import optimize_exact
from scripts.history5 import read_rounds, pre_match_p
from scripts.league_history import key_team

API = "https://v3.football.api-sports.io/"
SOURCE = "https://www.api-football.com/documentation_v3"
SEASONS = (2022, 2023, 2024)
LEAGUES = ("Premier League", "Championship")
MAX_CALLS = 65
MAX_INJURY_FIXTURES = 48  # 8 chronological fixtures per supported league-season
RATE_SECONDS = 6.5
SIMPLE_ABSENCE_WEIGHT = .045
QUESTIONABLE_WEIGHT = .018
MAX_LOG_SHIFT = .22
SIGNS = "1X2"
ROOT = Path(__file__).resolve().parents[1]


class APIClient:
    def __init__(self, secret, delay=RATE_SECONDS, max_calls=MAX_CALLS, transport=None):
        if not secret:
            raise ValueError("API-nyckel saknas")
        self._secret = secret
        self.delay = delay
        self.max_calls = max_calls
        self.transport = transport
        self.calls = 0
        self._last_call = None

    def get(self, route, params):
        if self.calls >= self.max_calls:
            raise RuntimeError("Förfrågningsbudget för denna körning uppnådd")
        if self._last_call is not None and self.delay:
            time.sleep(max(0, self.delay - (time.monotonic() - self._last_call)))
        self.calls += 1
        self._last_call = time.monotonic()
        if self.transport is not None:
            doc = self.transport(route, params)
        else:
            url = API + route + "?" + urlencode(params)
            req = Request(url, headers={
                "x-apisports-key": self._secret, "Accept": "application/json",
                "User-Agent": "StryktipslabbetHistoricalResearch/1.0"
            })
            try:
                with urlopen(req, timeout=24) as response:
                    raw = response.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise ValueError("API-svar för stort")
                doc = json.loads(raw)
            except (OSError, ValueError) as exc:
                raise RuntimeError("API-nätverk/svar-fel: " + type(exc).__name__) from None
        if not isinstance(doc, dict) or not isinstance(doc.get("response"), list):
            raise RuntimeError("API-svar har fel struktur")
        if doc.get("errors"):
            errs = doc["errors"]
            kinds = ",".join(str(k) for k in errs.keys()) if isinstance(errs, dict) else "other"
            raise RuntimeError("API-nekad förfrågan; kategorier: "+ kinds[:80])
        return doc["response"]


def date_utc(iso):
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(timezone.utc).date()


def elbow_snapshots(rounds):
    """Same pre-round Elo as scripts.history5.walk_forward, without look-ahead."""
    ratings = {}
    counts = Counter()
    out = {}
    for draw in rounds:
        base = [pre_match_p(m["home"], m["away"], ratings, counts) for m in draw["matches"]]
        out[draw["draw"]] = base
        diffs = defaultdict(float)
        appearances = Counter()
        for m,p in zip(draw["matches"],base):
            if not m["played_consistent"]:
                continue
            actual = 1 if m["outcome"]=="1" else .5 if m["outcome"]=="X" else 0
            expected = p[0]+.5*p[1]
            update = 30*(actual-expected)
            diffs[m["home"]]+=update
            diffs[m["away"]]-=update
            appearances[m["home"]]+=1
            appearances[m["away"]]+=1
        for team,delta in diffs.items():
            ratings[team] = ratings.get(team,1500)+delta
            counts[team]+=appearances[team]
    return out


def adjust(p, out_home, out_away, doubtful_home=0, doubtful_away=0):
    """Explicit scenario, fixed before the retrospective test (NOT fitted)."""
    signal = SIMPLE_ABSENCE_WEIGHT*(out_away-out_home) + QUESTIONABLE_WEIGHT*(doubtful_away-doubtful_home)
    signal = min(MAX_LOG_SHIFT, max(-MAX_LOG_SHIFT, signal))
    weights = [p[0]*math.exp(signal),p[1]*math.exp(-.12*abs(signal)),p[2]*math.exp(-signal)]
    z=sum(weights)
    return [w/z for w in weights]


def injury_counts(rows, fixtures):
    """Count uniquely identified reported absences per fixture + team."""
    result = {f: defaultdict(lambda: {"out":0,"doubtful":0}) for f in fixtures}
    seen = set()
    for row in rows:
        if not isinstance(row,dict):
            continue
        fix = (row.get("fixture") or {}).get("id")
        team = (row.get("team") or {}).get("id")
        player = (row.get("player") or {})
        pid = player.get("id")
        if fix not in result or type(team) is not int or type(pid) is not int:
            continue
        dedupe=(fix,team,pid)
        if dedupe in seen:
            continue
        typ=str(player.get("type") or "").strip().lower()
        if typ not in ("missing fixture","questionable"):
            continue
        seen.add(dedupe)
        result[fix][team]["out" if typ=="missing fixture" else "doubtful"]+=1
    return result


def confidence_interval(rows, metric, seed=20261114, rounds=1200):
    """Paired draw-block bootstrap of base-minus-adjusted average score."""
    groups=defaultdict(list)
    for r in rows:
        groups[r["draw"]].append(r)
    keys=sorted(groups)
    if len(keys)<3:
        return None
    rng=random.Random(seed)
    values=[]
    for _ in range(rounds):
        selected=[m for _ in keys for m in groups[rng.choice(keys)]]
        if selected:
            values.append(sum(metric(r) for r in selected)/len(selected))
    values.sort()
    return [round(values[int(.025*len(values))],6),
            round(values[min(len(values)-1,int(.975*len(values)))],6)]


def score(p, outcome):
    y=SIGNS.index(outcome)
    return (sum((v-int(i==y))**2 for i,v in enumerate(p)), -math.log(p[y]),
            int(max(range(3),key=lambda i:p[i])==y))


def matched_fixture(draw_date, match, indexes):
    candidates = indexes.get((match["home"],match["away"]), ())
    good=[]
    for f in candidates:
        gap=(f["date"]-date.fromisoformat(draw_date)).days
        if 0 <= gap <=3 and f["played"] and f["sign"]==match["outcome"] and (
            f["gh"]==match["score_home"] and f["ga"]==match["score_away"]):
            good.append(f)
    return good[0] if len(good)==1 else None


def dataset_from_api(client, rounds, batch_index=0, per_group=None, return_catalog=False):
    """Build only joined fixture metadata; never store/transmit provider responses."""
    indexes=defaultdict(list)
    coverage=[]
    for season in SEASONS:
        leagues=client.get("leagues",{"country":"England","season":season})
        options={}
        for row in leagues:
            league=row.get("league") or {}
            country=row.get("country") or {}
            if league.get("name") not in LEAGUES or country.get("name")!="England" or league.get("type")!="League":
                continue
            current=next((s for s in row.get("seasons",[]) if s.get("year")==season),None)
            if not current:continue
            flags=current.get("coverage") or {}
            options[league["name"]]={
                "id":league["id"],"injuries":flags.get("injuries") is True
            }
        for league in LEAGUES:
            meta=options.get(league)
            coverage.append((season,league, bool(meta and meta["injuries"])))
            if not meta or not meta["injuries"]:
                continue
            fixtures=client.get("fixtures",{"league":meta["id"],"season":season})
            for row in fixtures:
                fix=row.get("fixture") or {}
                teams=row.get("teams") or {}
                home=teams.get("home") or {}
                away=teams.get("away") or {}
                goals=row.get("goals") or {}
                if not(type(fix.get("id")) is int and type(home.get("id")) is int
                    and type(away.get("id")) is int and type(goals.get("home")) is int
                    and type(goals.get("away")) is int
                    and isinstance(home.get("name"),str) and isinstance(away.get("name"),str)):
                    continue
                try: kickoff=date_utc(fix["date"])
                except (ValueError,TypeError,KeyError):continue
                gh,ga=goals["home"],goals["away"]
                entry={"id":fix["id"],"home_id":home["id"],"away_id":away["id"],
                    "date":kickoff,"played":(fix.get("status") or {}).get("short")=="FT",
                    "gh":gh,"ga":ga,"sign":"1" if gh>ga else "2" if gh<ga else "X",
                    "league":league,"season":season}
                indexes[(key_team(home["name"]),key_team(away["name"]))].append(entry)
    matched={}
    for d in rounds:
        for i,m in enumerate(d["matches"]):
            if not m["played_consistent"]:
                continue
            f=matched_fixture(d["date"],m,indexes)
            if f is not None:
                matched[(d["draw"],i)]=f
    # Historical endpoint check (14 Nov 2026): individual fixture works for
    # Free, but the otherwise documented ids batch filter returns errors.plan.
    # Predefine the sample without inspecting absence or outcome patterns:
    # earliest up to eight score-verified matches from each league and season.
    if not isinstance(batch_index, int) or batch_index < 0 or batch_index > 40:
        raise ValueError("Historiskt batch-index måste vara 0–40")
    if per_group is None:
        per_group = MAX_INJURY_FIXTURES // (len(SEASONS)*len(LEAGUES))
    if not 1 <= per_group <= 8:
        raise ValueError("Högst åtta matcher per liga och säsong/körning")
    selected=set()
    for season in SEASONS:
        for league in LEAGUES:
            eligible={(f["date"],f["id"]) for f in matched.values()
                      if f["season"]==season and f["league"]==league}
            selected.update(fid for _,fid in sorted(eligible)[batch_index*per_group:(batch_index+1)*per_group])
    matched={k:v for k,v in matched.items() if v["id"] in selected}
    ids_by_date={f["id"]:f["date"] for f in matched.values()}
    fixture_ids=sorted(selected, key=lambda fid:(ids_by_date[fid],fid))
    absence={}
    complete=set()
    for fid in fixture_ids:
        try:
            rows=client.get("injuries",{"fixture":fid})
        except RuntimeError as exc:
            print("BACKTEST: Skadestatus kunde inte läsas för utvald match. "
                  "Avbryter återstående API-anrop; feltyp:",
                  str(exc).split(":")[0],file=sys.stderr)
            break
        absence.update(injury_counts(rows,[fid]))
        complete.add(fid)
    # A failed fetch is MISSING coverage, never interpreted as zero absences.
    matched={k:v for k,v in matched.items() if v["id"] in complete}
    if return_catalog:
        return matched,absence,coverage,indexes
    return matched,absence,coverage


def results_for(rounds,base_snapshots,matched,absence):
    metrics=[]
    selected_draws={}
    for d in rounds:
        base=base_snapshots[d["draw"]]
        revised=[p[:] for p in base]
        any_delta=False
        for i,m in enumerate(d["matches"]):
            f=matched.get((d["draw"],i))
            if f is None:continue
            counts=absence.get(f["id"],{})
            home=counts.get(f["home_id"],{})
            away=counts.get(f["away_id"],{})
            h,a=home.get("out",0),away.get("out",0)
            qh,qa=home.get("doubtful",0),away.get("doubtful",0)
            adj=adjust(base[i],h,a,qh,qa)
            revised[i]=adj
            affected=any(abs(a-b)>1e-12 for a,b in zip(adj,base[i]))
            any_delta |= affected
            brier_b,log_b,acc_b=score(base[i],m["outcome"])
            brier_a,log_a,acc_a=score(adj,m["outcome"])
            metrics.append({"draw":d["draw"],"season":f["season"],"league":f["league"],
                "out":h+a,"doubtful":qh+qa,"changed":affected,
                "dbrier":brier_b-brier_a,"dlog":log_b-log_a,
                "base_brier":brier_b,"api_brier":brier_a,"base_log":log_b,"api_log":log_a,
                "base_correct":acc_b,"api_correct":acc_a})
        if any_delta:
            sys={}
            for budget in (100,1800):
                cost,baseline_masks=optimize(base,budget)
                comparison_masks=optimize_exact(revised,cost)
                assert math.prod(m.bit_count() for m in comparison_masks)==cost
                orig=[selected_signs(mask) for mask in baseline_masks]
                adjusted=[selected_signs(mask) for mask in comparison_masks]
                actual="".join(m["outcome"] for m in d["matches"])
                dist_base=correct_rows(orig,actual)
                dist_api=correct_rows(adjusted,actual)
                sys[budget]={
                    "cost":cost,"changed_signs":sum(x!=y for x,y in zip(orig,adjusted)),
                    "base":{k:dist_base[k] for k in (10,11,12,13)},
                    "api":{k:dist_api[k] for k in (10,11,12,13)}
                }
            selected_draws[d["draw"]]=sys
    return metrics,selected_draws


def aggregate(rows):
    if not rows:
        return None
    n=len(rows)
    return {"n":n,"draws":len({r["draw"] for r in rows}),
        "original_brier":round(sum(r["base_brier"] for r in rows)/n,6),
        "with_absences_brier":round(sum(r["api_brier"] for r in rows)/n,6),
        "brier_improvement":round(sum(r["dbrier"] for r in rows)/n,6),
        "brier_diff_95ci":confidence_interval(rows,lambda r:r["dbrier"]),
        "original_logloss":round(sum(r["base_log"] for r in rows)/n,6),
        "with_absences_logloss":round(sum(r["api_log"] for r in rows)/n,6),
        "logloss_improvement":round(sum(r["dlog"] for r in rows)/n,6),
        "top1_original":round(sum(r["base_correct"] for r in rows)/n,4),
        "top1_with_absences":round(sum(r["api_correct"] for r in rows)/n,4),
        "total_absences":sum(r["out"] for r in rows),
        "total_questionable":sum(r["doubtful"] for r in rows)}


def summarize(metrics,draws,coverage,requests):
    print("BACKTEST: Ex ante odds och 2026/27-data används INTE; historiska API-skador saknar verifierad observationstid.")
    print("BACKTEST: RESULTAT: API-anrop totalt:",requests)
    print("BACKTEST: Täckning:",json.dumps(
        [{"season":s,"league":l,"injuries_covered":c} for s,l,c in coverage],
        ensure_ascii=False))
    print("BACKTEST: Alla exakt scorematchade API-fixtures:",json.dumps(aggregate(metrics),ensure_ascii=False))
    changed=[r for r in metrics if r["changed"]]
    print("BACKTEST: Matcherna med nettoförändrad skadebalans:",json.dumps(aggregate(changed),ensure_ascii=False))
    for season in SEASONS:
        subset=[r for r in metrics if r["season"]==season]
        if subset:
            print("BACKTEST: Säsong",str(season)+":",json.dumps(aggregate(subset),ensure_ascii=False))
    print("BACKTEST: Omgångar med minst en justerad 1/X/2:",len(draws))
    for budget in (100,1800):
        cases=[x[budget] for x in draws.values()]
        if not cases:continue
        costset=sorted({x["cost"] for x in cases})
        orig={str(k):sum(int(x["base"][k]>0) for x in cases) for k in (10,11,12,13)}
        api={str(k):sum(int(x["api"][k]>0) for x in cases) for k in (10,11,12,13)}
        # Hit rates are number of coupon rounds obtaining at least one row in class.
        print("BACKTEST: System",budget,"kr:",json.dumps({
            "draws":len(cases),"exact_equal_costs":costset,
            "rounds_with_changed_system":sum(x["changed_signs"]>0 for x in cases),
            "original_rounds_with_hit_class":orig,"api_rounds_with_hit_class":api
        },ensure_ascii=False))
    print("BACKTEST: OBS! Retrospektiva frånvarodata; resultat kan ha varit okända vid spelstopp.")
    print("BACKTEST: OBS! Elo-jämförelse, inte originalmarknadens historiska odds eller verifierat nettoutfall.")
    print("BACKTEST: Inga råa leverantörsdata, nycklar eller individuella spelaruppgifter publicerade.")


def main():
    key=os.getenv("APIFOOTBALL_KEY")
    if not key:
        raise SystemExit("APIFOOTBALL_KEY finns inte i detta arbetsflöde")
    rounds=read_rounds(ROOT/"data/history/stryktipset-five-years.csv")
    snapshots=elbow_snapshots(rounds)
    client=APIClient(key)
    batch=int(os.getenv("HISTORICAL_BATCH_INDEX", "0"))
    matched,absences,coverage=dataset_from_api(client,rounds,batch_index=batch)
    print("BACKTEST: Historisk batch:", batch, "(urvalet förblir kronologiskt, vikter oförändrade)")
    metrics,draws=results_for(rounds,snapshots,matched,absences)
    summarize(metrics,draws,coverage,client.calls)
    if not metrics:
        raise SystemExit("Inga historiska API-fixtures kunde kopplas säkert till kupongens matchresultat")


if __name__ == "__main__":
    main()
