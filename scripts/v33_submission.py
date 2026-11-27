"""Read-only side-by-side scenarios based on validated current market data.
Never changes the production model. Archive-provider claims are not independent
verification of original articles or a calibrated expert probability."""
import math
from collections import defaultdict
from scripts.analyze import optimize,selected_signs,evaluate_probability
from scripts.v25_history import instant,SIGNS
from scripts.v28_shadow import probability

def compare(base,doc,now,budget=1800):
    if not 1<=budget<=1800:raise ValueError("Budget")
    close=instant(base["reg_close_time"])
    if not instant(base["observed_at_utc"])<=now<close:raise ValueError("Not current")
    if len(base["matches"])!=13:raise ValueError("Invalid coupon")
    rows=[]; ids=set(); nclaims=0
    for m in base["matches"]:
        n=m["number"]; p=probability(m["p"])
        claims=defaultdict(list)
        for r in (doc or {}).get("rows",[]):
            if r.get("draw_number")!=base["draw_number"] or r.get("number")!=n:continue
            try:
                if r["cutoff_status"]!="prospective_review" or r["type"]!="result" or r["evidence"]!="archive_recorded" or r["sign"] not in ("1","X","2") or (r["home"],r["away"])!=(m["home"],m["away"]):continue
                if not r["record_url"].startswith("https://forecastrecord.com/") or not r["source"].startswith("https://forecastrecord.com/football/matches/"):continue
                if instant(r["reg_close_time"])!=close or not instant(r["source_at"])<=instant(r["observed_at"])<=now or instant(r["observed_at"])>=min(close,instant(r["kickoff"])):continue
                claims[r["external_id"]].append(r)
            except (TypeError,KeyError,ValueError):continue
        groups=defaultdict(list); votes=[0,0,0]; sources=[]
        for id,rr in claims.items():
            if len({r["sign"] for r in rr})!=1:continue
            r=min(rr,key=lambda r:r["observed_at"]); ids.add(id); nclaims+=1
            sources.append({"name":r["name"],"kind":r["kind"],"sign":r["sign"],"source":r["source"]})
            if r["kind"]!="human":continue
            k=r["publisher"].strip().lower()
            if not k:continue
            if "sportytrader" in k:k="sportytrader"
            if k.startswith("t.me"):k="telegram"
            j=SIGNS.index(r["sign"]);groups[k].append(j);votes[j]+=1
        q=[sum(v.count(i)/len(v) for v in groups.values())/len(groups) for i in range(3)] if len(groups)>=2 else None
        scenario=[.95*x+.05*y for x,y in zip(p,q)] if q else p
        rows.append({"number":n,"home":m["home"],"away":m["away"],"p":p,"streck":m["streck"],"scenario":scenario,"human_votes":votes,"groups":len(groups),"sources":sources})
    def scenario(key):
        cost,masks=optimize([r[key] for r in rows],budget)
        return {"cost":cost,"choices":[selected_signs(m) for m in masks],"p13_market":evaluate_probability(masks,[r["p"] for r in rows]),"p13_scenario":evaluate_probability(masks,[r[key] for r in rows])}
    return {"schema":"v33-submission-comparison-v1","draw_number":base["draw_number"],"market_observed_at":base["observed_at_utc"],"reg_close_time":base["reg_close_time"],"generated_at":now.isoformat(),"budget":budget,"observations":nclaims,"identities":len(ids),"expert_eligible_matches":sum(r["groups"]>=2 for r in rows),"rows":rows,"market":scenario("p"),"expert":scenario("scenario"),"production_expert_weight":0,"expert_experimental_weight":.05,"warning":"Expertkällor enligt Forecast Record, inte oberoende kontroll av originalartiklar. Oprövad expertjustering, endast med minst två publicistgrupper. Ingen automatisk förändring av grundmodell. xG och spelarskador ej separat viktade."}
