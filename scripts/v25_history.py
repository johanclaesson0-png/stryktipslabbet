"""V25: offline retrospective audit and fixed-weight probability experiment.
Never modifies production odds or mixes reconstructed and frozen samples.
Run: python -m scripts.v25_history --outdir data
"""
import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SIGNS = "1X2"
WEIGHTS = (0, .05, .10, .15, .20)
EVIDENCE = {"article_timestamp", "article_date_upper_bound", "archive_recorded"}

def read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

def instant(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def valid_pick(p, close, mode):
    try:
        src, seen = instant(p["source_at"]), instant(p["observed_at"])
        signs = p["sign"]
        return (src < close and src <= seen and p["source"].startswith("https://")
                and p["type"] in ("result", "first", "system")
                and signs in ("1","X","2","1X","12","X2","1X2")
                and (p["type"] == "system" or len(signs) == 1)
                and (p["evidence"] in EVIDENCE if mode == "retrospective"
                     else seen < close and p["evidence"] in EVIDENCE | {"direct_preclose"}))
    except (KeyError, ValueError, TypeError):
        return False

def blend(p, shares, weight):
    if shares is None:
        return list(p)
    return [(1-weight)*a + weight*b for a,b in zip(p,shares)]

def losses(p, actual):
    return sum((v - int(i == actual))**2 for i,v in enumerate(p)), -math.log(max(p[actual], 1e-15))

def evaluate(data):
    archive = {x["draw"]: x for x in read(data/"history/summary.json")["archive"]}
    pools = read(data/"history/official_pools.json")["draws"]
    panel = {x["id"]:x for x in read(data/"v24/panel.json")["panel"]}
    profiles, metrics, coverage = {}, {}, []
    for mode in ("retrospective", "prospective"):
        profiles[mode] = defaultdict(lambda: {"n":0,"hits":0,"fractional_hits":0.0,"odds_n":0,"odds_hits":0})
        metrics[mode] = {str(w): {"n":0,"brier_sum":0.0,"logloss_sum":0.0} for w in WEIGHTS}
    docs = {}
    for root in (data/"v25/recovered", data/"v24/reports"):
        for path in sorted(root.glob("*.json")):
            doc = read(path)
            docs.setdefault(doc["draw_number"], []).append(doc)
    for draw, entries in sorted(docs.items()):
        base = read(data/"analysis"/f"{draw}.json")
        official = read(data/"results"/f"{draw}.json") or pools.get(str(draw))
        if not official or len(official.get("outcome","")) != 13:
            continue
        if base:
            close = instant(base["reg_close_time"])
            matches = base["matches"]
            has_odds = instant(base["observed_at_utc"]) < close
        elif draw in archive:
            matches = archive[draw]["matches"]
            close = instant(entries[0]["reg_close_time"])
            has_odds = False
        else:
            continue
        actuals = official["outcome"]
        if any(x not in SIGNS for x in actuals) or len(matches) != 13:
            continue
        for mode in ("retrospective", "prospective"):
            votes = defaultdict(list)
            for doc in entries:
                if doc["mode"] != mode or instant(doc["reg_close_time"]) != close:
                    continue
                if mode == "prospective" and instant(doc["created_at_utc"]) >= close:
                    continue
                for p in doc["picks"]:
                    n = p.get("number",0)
                    if not isinstance(n,int) or not 1 <= n <= 13 or p.get("id") not in panel:
                        continue
                    m = matches[n-1]
                    if (p.get("home"),p.get("away")) != (m["home"],m["away"]) or not valid_pick(p,close,mode):
                        continue
                    if draw in archive and not archive[draw]["matches"][n-1].get("played_consistent",False):
                        continue
                    votes[(p["id"],n,p["type"])].append(p)
            accepted = []
            for key, observations in votes.items():
                # Conflicting recovered versions are excluded rather than chosen using hindsight.
                if len({p["sign"] for p in observations}) == 1:
                    accepted.append(observations[0])
            if not accepted:
                continue
            coverage.append({"draw":draw,"mode":mode,"observations":len(accepted),"sources":len({p["id"] for p in accepted}),"odds_available":has_odds})
            groups = defaultdict(lambda: defaultdict(list))
            for p in accepted:
                n = p["number"]
                actual = actuals[n-1]
                k = (p["id"],p["type"])
                r = profiles[mode][k]
                r["n"] += 1
                r["hits"] += int(actual in p["sign"])
                r["fractional_hits"] += int(actual in p["sign"])/len(p["sign"])
                if has_odds:
                    odds = matches[n-1]["p"]
                    r["odds_n"] += 1
                    r["odds_hits"] += int(SIGNS[max(range(3),key=lambda i:odds[i])] == actual)
                    if p["type"] == "result" and panel[p["id"]]["kind"] == "human":
                        groups[n][panel[p["id"]]["group"]].append(SIGNS.index(p["sign"]))
            for n, publishers in groups.items():
                p = matches[n-1]["p"]
                shares = [sum(v.count(i)/len(v) for v in publishers.values())/len(publishers) for i in range(3)]
                actual = SIGNS.index(actuals[n-1])
                for w in WEIGHTS:
                    b,l = losses(blend(p,shares,w),actual)
                    r = metrics[mode][str(w)]
                    r["n"] += 1
                    r["brier_sum"] += b
                    r["logloss_sum"] += l
    return {"schema":"v25-history-audit-v1","created_at_utc":datetime.now(timezone.utc).isoformat(),
            "coverage":coverage,"profiles":{m:[{"id":i,"type":t,**v} for (i,t),v in sorted(r.items())] for m,r in profiles.items()},
            "fixed_weight_experiments":{m:[{"weight":float(w),"matches":v["n"],"brier":v["brier_sum"]/v["n"] if v["n"] else None,"log_loss":v["logloss_sum"]/v["n"] if v["n"] else None} for w,v in r.items()] for m,r in metrics.items()},
            "warning":"Retrospective source timestamps do not prove article versions were frozen. Fixed weights are descriptive, not trained or validated. Community and system/first picks excluded from probability experiment. No production change."}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--outdir",default="data")
    args=ap.parse_args()
    data=Path(args.outdir)
    report=evaluate(data)
    dest=data/"v25/audit.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("V25 coverage:",report["coverage"])

if __name__ == "__main__":
    main()
