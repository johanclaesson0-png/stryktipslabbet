"""Pre-submission audit only; no bets, model overrides or stake changes."""
import argparse,json,math
from datetime import datetime,timezone
from pathlib import Path
from scripts.v25_history import read,instant
from scripts.analyze import valid_analysis

def review(data,now):
    latest=read(data/"latest.json");draw=latest["draw_number"]
    base=read(data/"analysis"/f"{draw}.json")
    close=instant(latest["reg_close_time"])
    observed=instant(latest["observed_at_utc"])
    if not observed<=now<close:raise ValueError("Current snapshot stale in date or cutoff passed")
    if not valid_analysis(base,now) or base["source_snapshot_sha256"]!=latest["sha256"] or base["reg_close_time"]!=latest["reg_close_time"] or base["observed_at_utc"]!=latest["observed_at_utc"]:raise ValueError("Base and latest snapshot mismatch")
    for m,s in zip(base["matches"],latest["matches"]):
        if (m["number"],m["home"],m["away"],m["odds"],m["streck"])!=(s["number"],s["home"],s["away"],s["odds"],s["streck"]):raise ValueError("Fixture or prices differ")
        p=[1/v for v in s["odds"]];p=[v/sum(p) for v in p]
        if any(abs(a-b)>1e-7 for a,b in zip(p,m["p"])):raise ValueError("Market probabilities differ")
    doc=read(data/"v31/prospective_review.json") or {"rows":[]}
    accepted=[]
    for r in doc["rows"]:
        if r.get("draw_number")!=draw:continue
        n=r["number"]
        if type(n)!=int or not 1<=n<=13:continue
        m=base["matches"][n-1]
        if (m["home"],m["away"])!=(r["home"],r["away"]) or not instant(r["source_at"])<=instant(r["observed_at"])<=now or instant(r["observed_at"])>=min(close,instant(r["kickoff"])) or instant(r["reg_close_time"])!=close:continue
        accepted.append(r)
    return {"schema":"v32-submission-readiness-v1","draw_number":draw,"reg_close_time":close.isoformat(),"observed_at":observed.isoformat(),"snapshot_age_minutes":round((now-observed).total_seconds()/60,1),"verified_current_review_rows":len(accepted),"current_review_identities":len({r["external_id"] for r in accepted}),"current_review_positions":len({r["number"] for r in accepted}),"rows":base["matches"],"baseline_systems":base["systems"],"production_expert_weight":0,"warning":"Snapshot must be refreshed and matched to the actual coupon before submission. Current expert review is separate, sparse and not a validated probability adjustment. Legacy manual observations and community data are not independently verified."}

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--data",default="data");ap.add_argument("--output",default="v32-readiness.json");a=ap.parse_args()
    r=review(Path(a.data),datetime.now(timezone.utc))
    Path(a.output).write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n")
    print("READINESS",json.dumps({k:r[k] for k in ("draw_number","reg_close_time","observed_at","snapshot_age_minutes","verified_current_review_rows","current_review_identities","current_review_positions","production_expert_weight")}),flush=True)
