#!/usr/bin/env python3
"""V20: explicitly hypothetical payout simulator for Stryktipset M systems.

Not a prediction of actual payout or true expected value. Assumptions:
independent market outcomes; independent public selections from marginal
streck; user-selectable hypothetical turnover; no jackpot, guarantee,
reallocation or systematic correlated bets. Simulations never use outcomes
after the snapshot or move actual systems. Costs are exact, never up-sold.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import statistics

from scripts.analyze import correct_rows
from scripts.feature_model import optimize_exact
from scripts.solo import validate as valid_solo
from scripts.v19_decision import original_ok
from scripts.v19_evaluation import json_doc
from scripts.publish import instant

SCHEMA="stryktipslabbet-payout-scenarios-v20"
SIGN="1X2"
# Svenska Spel Stryktipset: 65% return before the dedicated 8% fund share.
RETURN_FRACTION=0.65
POOL_SHARES={13:.40,12:.15,11:.12,10:.25} # the remaining 8% to guarantee fund
MIN_PAYOUT=15.0
STAKE_PER_ROW=1.0
TURNOVERS=(5_000_000,15_000_000,30_000_000) # ILLUSTRATIVE ONLY
CROWD_MULTIPLIERS=(.5,1.0,2.0) # uncertainty in other winners, not CI
EXPONENTS=(0.0,.25,.45,.70,1.0)
SAMPLES=6000
SEED=20261120
SOURCE_RULES_URL="https://spela.svenskaspel.se/fotboll/premier-league/stryktipset"


def valid_probability_rows(matches):
    if len(matches)!=13:
        raise ValueError("13 matcher krävs")
    market,crowd=[],[]
    for m in matches:
        p=m.get("p")
        streck=m.get("streck")
        if (not isinstance(p,list) or len(p)!=3
            or not all(type(v) in (float,int) and math.isfinite(v) and 0<v<1 for v in p)
            or abs(sum(p)-1)>0.0001):
            raise ValueError("Ogiltiga förhandsodds")
        if (not isinstance(streck,list) or len(streck)!=3
            or not all(type(v) in (float,int) and math.isfinite(v) and 0<=v<=100 for v in streck)
            or not 98.9<=sum(streck)<=101.1):
            raise ValueError("Ogiltiga förhandsstreck")
        market.append([float(v) for v in p])
        total=sum(streck)
        crowd.append([float(v)/total for v in streck])
    return market,crowd


def profile_probabilities(p,c,exponent):
    scores=[p[i]*(p[i]/max(c[i],.035))**exponent for i in range(3)]
    norm=sum(scores)
    return [v/norm for v in scores]


def generate_candidates(matches,baseline,cost):
    """Five fixed crowd-penalty scenarios; never optimize on official results."""
    market,crowd=valid_probability_rows(matches)
    if type(cost) is not int or cost>1800 or cost<1:
        raise ValueError("Otillåten systemkostnad")
    if (not isinstance(baseline,list) or len(baseline)!=13
        or math.prod(len(x) for x in baseline)!=cost):
        raise ValueError("Originalsystemet matchar inte radkostnaden")
    result={"odds":baseline[:]}
    for exponent in EXPONENTS[1:]:
        weighted=[profile_probabilities(p,c,exponent) for p,c in zip(market,crowd)]
        masks=optimize_exact(weighted,cost)
        choices=["".join(SIGN[i] for i in range(3) if m&(1<<i)) for m in masks]
        if math.prod(len(x) for x in choices)!=cost:
            raise ArithmeticError("Experimentet ändrade kostnaden")
        result["streck_"+str(exponent).replace(".","_")]=choices
    return result


def sample_outcomes(market,n=SAMPLES,seed=SEED):
    """Common Monte Carlo sample across strategies and turnover scenarios."""
    if not 300<=n<=40000:
        raise ValueError("Otillåtet simuleringsantal")
    rng=random.Random(seed)
    result=[]
    for _ in range(n):
        seq=[]
        for p in market:
            u=rng.random()
            seq.append(0 if u<p[0] else 1 if u<p[0]+p[1] else 2)
        result.append(tuple(seq))
    return result


def crowds_class_likelihood(crowd,observed):
    """Poisson-binomial distribution of 0..13 correct for one random line.

    This independence assumption is NOT observed public multi-match patterns.
    """
    dp=[1.0]
    for c,y in zip(crowd,observed):
        hit=c[y]
        nxt=[0.]*(len(dp)+1)
        for k,v in enumerate(dp):
            nxt[k]+=v*(1-hit)
            nxt[k+1]+=v*hit
        dp=nxt
    return {k:dp[k] for k in (10,11,12,13)}


def winning_rows(choices,outcome):
    return correct_rows(choices,"".join(SIGN[i] for i in outcome))


def potential_payout(rows,competitors,turnover,crowd_multiplier):
    """Expected row counts from crowd marginals: a *scenario*, not forecast.

    Include own winning rows in the denominator. Excludes jackpot, guarantees
    and actual reallocation of pools. The 15 SEK threshold is approximated.
    """
    if turnover<=0 or crowd_multiplier<=0:
        raise ValueError("Ogiltigt illustrativt scenario")
    prize=0.
    for k,share in POOL_SHARES.items():
        winners=rows[k]
        if not winners:
            continue
        pool=turnover*RETURN_FRACTION*share
        expected_other=competitors[k]*crowd_multiplier
        # Our own system is already among the hypothetical competing rows.
        per_row=pool/max(winners+expected_other,1.)
        if per_row>=MIN_PAYOUT:
            prize+=winners*per_row
    return prize


def analyze_strategies(matches,originals,simulations=SAMPLES,seed=SEED):
    """Return aggregate, bounded scenario statistics; no simulated individual bets."""
    market,crowd=valid_probability_rows(matches)
    if set(originals)!={100,1800}:
        raise ValueError("Saknar två jämförbara budgetar")
    candidates={}
    for budget,(cost,choices) in originals.items():
        candidates[budget]=(cost,generate_candidates(matches,choices,cost))
    outcomes=sample_outcomes(market,simulations,seed)
    likelihoods=[crowds_class_likelihood(crowd,seq) for seq in outcomes]
    row_maps={budget:{k:[winning_rows(choices,seq) for seq in outcomes]
                      for k,choices in candidate.items()}
              for budget,(cost,candidate) in candidates.items()}
    comparisons=[]
    for turnover in TURNOVERS:
        for multiplier in CROWD_MULTIPLIERS:
            groups=[]
            for budget,(cost,candidate) in candidates.items():
                rows_for_budget=turnover-cost
                evaluations=[]
                for key,choices in candidate.items():
                    payouts=[]
                    hit13=0
                    hit10=0
                    for r,crowd_like in zip(row_maps[budget][key],likelihoods):
                        hit13+=int(r[13]>0)
                        hit10+=int(any(r[k]>0 for k in (10,11,12,13)))
                        competitors={k:max(0.,rows_for_budget)*crowd_like[k]
                                     for k in (10,11,12,13)}
                        payouts.append(potential_payout(r,competitors,turnover,multiplier))
                    payouts.sort()
                    n=len(payouts)
                    avg=sum(payouts)/n
                    dev=statistics.stdev(payouts) if n>1 else 0.
                    # Sampling error only, not real-world uncertainty in payout.
                    se=dev/math.sqrt(n)
                    evaluations.append({
                        "id":key,"cost":cost,"choices":choices,
                        "changed_matches":sum(a!=b for a,b in zip(candidate["odds"],choices)),
                        "estimated_mean_paid_kr":round(avg),
                        "estimated_mean_net_kr":round(avg-cost),
                        "median_net_kr":round(payouts[n//2]-cost),
                        "p90_net_kr":round(payouts[min(n-1,int(n*.90))]-cost),
                        "prob_positive_net":round(sum(x>cost for x in payouts)/n,5),
                        "prob_at_least_10_correct":round(hit10/n,5),
                        "prob_at_least_one_13":round(hit13/n,5),
                        "simulated_mean_se_kr":round(se),
                        "sampling_only_ci95_kr":[round(avg-cost-1.96*se),
                                                  round(avg-cost+1.96*se)],
                    })
                # Scenario ranking is model-specific and illustrative only.
                ranked=sorted(evaluations,key=lambda x:x["estimated_mean_net_kr"],reverse=True)
                groups.append({"budget":budget,"exact_cost":cost,
                               "scenario_top_by_estimated_kr":ranked[0]["id"],
                               "strategies":evaluations})
            comparisons.append({"assumed_turnover_kr":turnover,
                                "crowd_winner_multiplier":multiplier,
                                "budgets":groups})
    return comparisons


def build(snapshot,base,solo,now,simulations=SAMPLES):
    if (not original_ok(snapshot,base,now)
        or not valid_solo(solo,base)
        or now>=instant(base["reg_close_time"])):
        raise ValueError("Kräver verifierad tidsfryst öppen kupong")
    budget_systems={
        100:(solo["systems"][0]["cost"],solo["systems"][0]["choices"]),
        1800:(base["systems"][0]["cost"],base["systems"][0]["choices"]),
    }
    if any(c!=math.prod(len(x) for x in signs) for c,signs in budget_systems.values()):
        raise ValueError("Systemkostnaden är inkonsekvent")
    scenarios=analyze_strategies(base["matches"],budget_systems,simulations)
    market,crowd=valid_probability_rows(base["matches"])
    upsets=[]
    for m,p,c in zip(base["matches"],market,crowd):
        # Rank unexpectedness AND relative underplay, no prediction of a
        # specific *joint* upset or promise of kronor.
        for i,sign in enumerate(SIGN):
            if p[i]<.5 and c[i] < p[i] and p[i] >= .06:
                upsets.append({
                    "match":m["number"],"home":m["home"],"away":m["away"],
                    "sign":sign,"market_probability_pct":round(100*p[i],1),
                    "public_streck_pct":round(100*c[i],1),
                    "underplayed_pp":round(100*(p[i]-c[i]),1),
                    "relative_underplay":round(p[i]/max(.001,c[i]),2),
                    "note":"Underskattat i strecken enligt odds, inte bevisad vinstchans i kronor",
                })
    upsets.sort(key=lambda r:(-r["underplayed_pp"],-r["relative_underplay"],r["match"]))
    return {
        "schema":SCHEMA,
        "source_rule":"Actual verified pre-close Svenska Spel match odds and crowd",
        "draw_number":base["draw_number"],
        "source_snapshot_sha256":base.get("source_snapshot_sha256"),
        "observed_at_utc":base["observed_at_utc"],
        "reg_close_time":base["reg_close_time"],
        "observed_turnover_so_far_kr":snapshot.get("observed_turnover_so_far_kr"),
        "sales_observed_at_utc":snapshot.get("sales_observed_at_utc"),
        "generated_at_utc":now.isoformat(),
        "draw_status":"hypotetisk utdelningsmodell – faktisk omsättning och vinstutfall okända",
        "simulation_draws":simulations,
        "assumptions":{
            "turnover":"ILLUSTRATIVE; not actual draw turnover",
            "turnover_scenarios_kr":list(TURNOVERS),
            "independence":"Both match outcomes and crowd line selections assumed independent",
            "crowd_multipliers":list(CROWD_MULTIPLIERS),
            "min_row_payout_kr":MIN_PAYOUT,
            "return_fraction":RETURN_FRACTION,
            "pool_allocation_pct":{str(k):round(v*100) for k,v in POOL_SHARES.items()},
            "guarantee_and_jackpot":"EXCLUDED; no false guarantee of high payouts",
            "sampling_ci":"Monte Carlo sampling only; excludes market and crowd-model uncertainty",
            "pricing":"Other winning rows are estimated, not known",
        },
        "upsets":upsets[:18],
        "scenarios":scenarios,
        "warnings":[
            "Alla kronbelopp bygger på illustrativ omsättning, marginalstreck och oberoende antaganden.",
            "Faktiska 13/12/11/10-rättsutdelningar kan skilja sig kraftigt, särskilt vid skräll.",
            "Stryktipsets jackpot, ensamvinstgaranti och pottomfördelningar ingår inte.",
            "Beräknade värden är inte validerad förväntad avkastning och inte spelrekommendationer.",
            "Förhandsfrysta originalsystem ändras inte och inga spel lämnas in.",
        ]
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--outdir",default="data")
    parser.add_argument("--simulations",type=int,default=SAMPLES)
    args=parser.parse_args()
    root=Path(args.outdir)
    now=datetime.now(timezone.utc)
    result={"schema":SCHEMA,"draw_status":"Ingen öppen tidsfryst kupong",
            "generated_at_utc":now.isoformat(),
            "scenarios":[],"upsets":[],"simulation_draws":0}
    for p in sorted((root/"analysis").glob("*.json"),reverse=True):
        base=json_doc(p)
        if not isinstance(base,dict):
            continue
        try:
            if now>=instant(base["reg_close_time"]):
                continue
            solo=json_doc(root/"personal"/p.name)
            if solo is None:continue
            for f in (root/"snapshots"/p.stem).glob("*.json"):
                snap=json_doc(f)
                if (isinstance(snap,dict) and
                    snap.get("observed_at_utc")==base.get("observed_at_utc") and
                    snap.get("sha256")==base.get("source_snapshot_sha256")):
                    result=build(snap,base,solo,now,args.simulations)
                    break
            if result.get("scenarios"):
                break
        except (KeyError,ValueError,TypeError,OverflowError,ZeroDivisionError):
            continue
    target=root/"v20"/"simulator.json"
    # Preserve the last originally generated pre-close V20 scenario when the
    # draw changes or closes. The archived source is never generated using
    # the outcome and may only be used LATER for real after-close calibration.
    prior=json_doc(target)
    if isinstance(prior,dict) and prior.get("schema")==SCHEMA and prior.get("scenarios"):
        try:
            old_draw=prior["draw_number"]
            created=instant(prior["generated_at_utc"])
            closed=instant(prior["reg_close_time"])
            if (type(old_draw) is int and created<closed and
                not (result.get("draw_number")==old_draw and result.get("scenarios"))):
                hist=root/"v20_history"/(str(old_draw)+".json")
                if not hist.exists():
                    hist.parent.mkdir(parents=True,exist_ok=True)
                    hist.write_text(json.dumps(prior,ensure_ascii=False,indent=2)+"\n",
                                    encoding="utf-8")
                    print("V20: sparade originalprognos före spelstopp för",old_draw)
        except (KeyError,TypeError,ValueError,OverflowError):
            pass
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("V20:",result["draw_status"],"simulerade utfall:",
          result["simulation_draws"],"scenarier:",len(result["scenarios"]))


if __name__=="__main__":
    main()
