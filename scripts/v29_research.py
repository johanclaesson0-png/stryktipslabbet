"""V29: chronological, research-only skill and blend validation.
Uses only strict retrospective import records, separately from live model.
Weights are relative to market probabilities; no optimisation on the test draw.
Never deploys or places bets. Legacy retrospective evidence cannot prove prospective performance."""
import argparse, json, math
from collections import defaultdict
from pathlib import Path
from scripts.v25_history import read, instant, valid_pick, strict_scope, losses, blend, SIGNS
from scripts.v28_shadow import probability

WEIGHTS=(0,.05,.10,.15,.20)
MIN_TRAIN=50
MIN_TRAIN_DRAWS=8
MIN_PROMOTION_MATCHES=500
MIN_PROMOTION_DRAWS=30

def reliability(stats, id, league, sign, p):
    # Prior mean: no excess skill beyond market. Shrink by 40 picks globally
    # and 60 within league/sign/market-probability bucket.
    keys=[((id,"all"),40),((id,"league",league),60),((id,"sign",sign),60),((id,"bucket",min(4,int(p*5))),60)]
    residual=0
    for key,prior in keys:
        n,s=stats.get(key,(0,0))
        residual+=s/(n+prior)
    return min(2.0,max(.5,math.exp(2*residual/len(keys))))

def update(stats, row):
    actual=row["actual"]; p=row["p"]
    for r in row["experts"]:
        j=SIGNS.index(r["sign"])
        residual=float(j==actual)-p[j]
        for key in [(r["id"],"all"),(r["id"],"league",r["league"]),(r["id"],"sign",r["sign"]),(r["id"],"bucket",min(4,int(p[j]*5)))]:
            n,s=stats.get(key,(0,0)); stats[key]=(n+1,s+residual)

def shares(row,stats=None):
    groups=defaultdict(list)
    for r in row["experts"]:
        j=SIGNS.index(r["sign"])
        w=reliability(stats,r["id"],r["league"],r["sign"],row["p"][j]) if stats is not None else 1
        groups[r["group"]].append((j,w))
    if len(groups)<2: return None
    # Equal total influence per publisher, skill within groups and bounded
    # average skill across groups. Avoid simply counting many syndications.
    vectors=[]
    for g in groups.values():
        total=sum(w for j,w in g)
        v=[sum(w for j,w in g if j==i)/total for i in range(3)]
        vectors.append((v,total/len(g)))
    return [sum(v[i]*w for v,w in vectors)/sum(w for v,w in vectors) for i in range(3)]

def read_rows(data):
    panel={x["id"]:x for x in read(data/"v24/panel.json")["panel"]}
    for x in (read(data/"v25/sources.json") or {"panel":[]})["panel"]: panel.setdefault(x["id"],x)
    rows=[]
    for path in sorted((data/"v25/imported").glob("*.json")):
        doc=read(path); draw=doc["draw_number"]
        base=read(data/"analysis"/path.name); result=read(data/"results"/path.name)
        if not base or not result or doc["mode"]!="retrospective": continue
        close=instant(base["reg_close_time"]); odds_at=instant(base["observed_at_utc"])
        if odds_at>=close or result["draw_number"]!=draw or len(result["outcome"])!=13 or any(x not in SIGNS for x in result["outcome"]): continue
        settled=instant(result["observed_at_utc"])
        if settled<=close: continue
        strict_scope([doc],base["matches"],panel,close)
        form=read(data/"form_model"/path.name)
        forms={}
        if form and form.get("draw_number")==draw and form.get("source_snapshot_sha256")==base.get("source_snapshot_sha256") and form.get("source_observed_at_utc")==base["observed_at_utc"] and instant(form["created_at_utc"])<close:
            forms={m["number"]:m for m in form["matches"]}
        for m in base["matches"]:
            n=m["number"]; p=probability(m["p"]); f=forms.get(n)
            fp=p
            if f and f.get("used_form") and (f["home"],f["away"])==(m["home"],m["away"]):
                fp=probability(f["form_p"])
            experts=[]
            for r in doc["picks"]:
                if r["number"]!=n or panel[r["id"]]["kind"]!="human": continue
                experts.append({"id":r["id"],"group":r.get("publisher_group",panel[r["id"]]["group"]),"league":r.get("league","unknown"),"sign":r["sign"]})
            row={"draw":draw,"number":n,"cutoff":close,"settled":settled,"p":p,"form":fp,"actual":SIGNS.index(result["outcome"][n-1]),"experts":experts}
            if shares(row) is not None: rows.append(row)
    return rows

def evaluate(rows):
    by_draw=defaultdict(list)
    for r in rows: by_draw[r["draw"]].append(r)
    ordered=sorted(by_draw.values(),key=lambda g:g[0]["cutoff"])
    past=[]; scored=[]; profiles={}; candidate_history=[]
    for group in ordered:
        # All members of one coupon predicted using only already settled prior coupons.
        cutoff=min(r["cutoff"] for r in group)
        eligible=[r for r in past if r["settled"]<cutoff]
        stats={}
        for r in eligible: update(stats,r)
        ready=len(eligible)>=MIN_TRAIN and len({r["draw"] for r in eligible})>=MIN_TRAIN_DRAWS
        known_scores=[x for x in candidate_history if x["settled"]<cutoff]
        # Candidate losses are from sequential earlier predictions, never current results.
        if ready and known_scores:
            selected=min(WEIGHTS,key=lambda w:(sum(x["losses"][str(w)] for x in known_scores)/len(known_scores),w))
        else: selected=0
        current=[]
        for r in group:
            eq=shares(r); adaptive=shares(r,stats)
            q={str(w):blend(r["form"],adaptive,w) for w in WEIGHTS}
            metrics={"market":losses(r["p"],r["actual"]),"form_only":losses(r["form"],r["actual"]),"equal_5":losses(blend(r["p"],eq,.05),r["actual"]),"adaptive_5":losses(blend(r["p"],adaptive,.05),r["actual"]),"selected_combined":losses(q[str(selected)],r["actual"])}
            current.append({"settled":r["settled"],"losses":{w:losses(v,r["actual"])[1] for w,v in q.items()}})
            scored.append({"draw":r["draw"],"number":r["number"],"train_matches":len(eligible),"train_draws":len({x["draw"] for x in eligible}),"selected_weight":selected,"eligible_for_holdout":ready,"metrics":metrics})
        candidate_history.extend(current);past.extend(group)
    def aggregate(rs):
        if not rs:return {}
        return {k:{"n":len(rs),"brier":sum(x["metrics"][k][0] for x in rs)/len(rs),"log_loss":sum(x["metrics"][k][1] for x in rs)/len(rs)} for k in rs[0]["metrics"]}
    holdout=[r for r in scored if r["eligible_for_holdout"]]
    for r in rows:update(profiles,r)
    return {"schema":"v29-research-v1","matches":len(rows),"draws":len(ordered),"chronological_preview":aggregate(scored),"holdout":aggregate(holdout),"holdout_matches":len(holdout),"holdout_draws":len({r["draw"] for r in holdout}),"promotion_min_matches":MIN_PROMOTION_MATCHES,"promotion_min_draws":MIN_PROMOTION_DRAWS,"production_expert_weight":0,"promotion":"blocked; independent prospective validation and manual review required","profiles":[{"id":key[0],"matches":v[0],"market_adjusted_hit_residual":v[1]/v[0]} for key,v in sorted(profiles.items()) if key[1]=="all"],"per_match":scored,"warning":"Strict retrospective dataset only. Existing records are not prospectively frozen. Form when valid; community and player effects remain disabled until independently verified, temporally matched numerical data exist. No production changes."}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",default="data")
    ap.add_argument("--output",default="v29-research.json")
    args=ap.parse_args()
    report=evaluate(read_rows(Path(args.data)))
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print("V29",json.dumps({k:report[k] for k in ("matches","draws","holdout_matches","holdout_draws","chronological_preview","promotion")}))
if __name__=="__main__": main()
