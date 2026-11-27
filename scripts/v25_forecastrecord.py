"""Read-only Forecast Record v2 export importer. Output is a review artifact,
not production data. Do not persist third-party quotes or odds from after cutoff."""
import argparse
import json
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, urljoin
from scripts.v25_history import instant, read

BASE = "https://forecastrecord.com"
URL = re.compile(r"https://forecastrecord\.com/football/matches/[a-z0-9-]+/")

def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD",s.casefold()) if c.isascii() and c.isalnum())

def fetch(url):
    if not URL.fullmatch(url):
        raise ValueError("Unapproved export URL")
    with urlopen(Request(url+"index.json",headers={"User-Agent":"Stryktipslabbet research/1.0","Accept":"application/json"}),timeout=30) as response:
        if response.geturl()!=url+"index.json":
            raise ValueError("Unexpected redirect")
        data=response.read(15_000_001)
        if len(data)>15_000_000:
            raise ValueError("Export too large")
        return json.loads(data)

def extract(doc, spec, base, official, now):
    close=instant(base["reg_close_time"])
    if doc.get("schema_version")!="2.0" or doc.get("page_type")!="event" or BASE+doc.get("canonical","")!=spec["url"]:
        raise ValueError("Unexpected export schema or canonical URL")
    ev=doc["event"]
    kickoff=instant(ev["starts_at"])
    if norm(ev["display_name"])!=norm(spec["display"]) or kickoff.date().isoformat()!=spec["date"]:
        raise ValueError("Fixture mismatch")
    if official is None:
        if now>=min(close,kickoff) or ev.get("status") not in ("scheduled","upcoming","not_started"):
            raise ValueError("Not a preclose upcoming fixture")
    else:
        if ev.get("status")!="finished":
            raise ValueError("Fixture not finished")
        h,a=map(int,ev["scoreline"].split("-"))
        sign="1" if h>a else "2" if h<a else "X"
        if sign!=official["outcome"][spec["number"]-1]:
            raise ValueError("Official result mismatch")
    match=base["matches"][spec["number"]-1]
    if match["number"]!=spec["number"] or base["draw_number"]!=spec["draw"]:
        raise ValueError("Wrong coupon position")
    summary=doc["match_summary"]["who_predicted_what"]
    by_id={x["record_id"]:x for x in summary}
    candidates=defaultdict(list)
    rejected=defaultdict(int)
    for e in doc["evidence_items"]:
        claim=e.get("author_claim") or {}
        if claim.get("market_key")!="1x2" or claim.get("period")!="match" or claim.get("choice_key") not in ("1","X","2","x"):
            continue
        try:
            if e.get("origin")!="recorded_before_kickoff" or e.get("withdrawn") is not False or e.get("late_publication") or e.get("link") or e.get("correction") or (e.get("source_info") or {}).get("material_removed"):
                raise ValueError("provenance")
            ts=instant(e["dates"]["detected_at"])
            if ts>=min(close,kickoff) or ts>now:
                raise ValueError("after cutoff")
            pub=e.get("published_at")
            if pub and instant(pub)>ts:
                raise ValueError("publication mismatch")
            if e.get("event",{}).get("event_id")!=ev["id"]:
                raise ValueError("event mismatch")
            identity=by_id[e["observation_id"]]
            author=identity["author"]
            path=identity["author_url"]
            identity_pattern = r"/(?:authors|sources)/[a-z0-9-]+/"
            if official is None:
                identity_pattern = r"/(?:authors/[a-z0-9-]+|sources/[a-z0-9-]+(?:/products/[a-z0-9-]+)?)/"
            if not isinstance(path,str) or not re.fullmatch(identity_pattern,path) or not isinstance(author,str) or not author.strip():
                raise ValueError("identity")
            auth=e.get("authorship") or {}
            if auth.get("excluded_from_individual_summaries"):
                raise ValueError("attribution")
            publisher=auth.get("publisher")
            original=(e.get("source_info") or {}).get("url")
            original_url=urlsplit(original) if isinstance(original,str) else None
            original_host=original_url.hostname if original_url and original_url.scheme=="https" and not original_url.username else None
            if official is None and not publisher:
                publisher=original_host.removeprefix("www.") if original_host else None
            if not isinstance(publisher,str) or not publisher.strip():
                raise ValueError("publisher")
            proof=e.get("url")
            direct_evidence = "/evidence/?pick="+e["observation_id"]
            if official is None and proof in (None,direct_evidence) and original_host and identity.get("url") is None and identity.get("before_kickoff") is True and instant(identity["recorded_at"])==ts:
                record_url=urljoin(BASE,proof) if proof else spec["url"]
            elif isinstance(proof,str) and proof.startswith(path):
                record_url=urljoin(BASE,proof)
            else:
                raise ValueError("proof path")
            candidates[path].append({"external_id":path,"name":author,"publisher":publisher,"kind":"human" if path.startswith("/authors/") else "site","number":spec["number"],"home":match["home"],"away":match["away"],"type":"result","sign":claim["choice_key"].upper(),"source":spec["url"],"record_url":record_url,"source_at":ts.isoformat(),"observed_at":now.isoformat(),"evidence":"archive_recorded","league":ev["competition_name"],"record_id":e["observation_id"]})
        except (KeyError,TypeError,ValueError) as exc:
            rejected[str(exc) if isinstance(exc,ValueError) else "missing field"]+=1
    rows=[]
    for path,group in sorted(candidates.items()):
        if len({x["sign"] for x in group})!=1:
            rejected["conflicting choice"]+=len(group)
            continue
        rows.append(min(group,key=lambda x:x["source_at"]))
    return rows,dict(rejected)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data",default="data")
    p.add_argument("--manifest",default="data/v25/forecastrecord_manifest.json")
    p.add_argument("--output",default="forecastrecord-review.json")
    p.add_argument("--limit",type=int,default=13)
    args=p.parse_args()
    if not 1<=args.limit<=20:
        p.error("Limit must be between 1 and 20")
    data=Path(args.data)
    manifest=read(Path(args.manifest))
    if manifest["schema"]!="forecastrecord-import-manifest-v1":
        raise ValueError("Wrong manifest")
    panel=(read(data/"v24/panel.json") or {"panel":[]})["panel"]+(read(data/"v25/sources.json") or {"panel":[]})["panel"]
    lookup=defaultdict(set)
    for s in panel:
        lookup[norm(s["name"])].add(s["id"])
    report={"schema":"forecastrecord-review-v1","matches":[],"rows":[],"errors":[]}
    for i,spec in enumerate(manifest["matches"][:args.limit]):
        if i: time.sleep(7)
        try:
            draw=spec["draw"]
            base=read(data/"analysis"/f"{draw}.json")
            official=read(data/"results"/f"{draw}.json")
            if not base or not official:
                raise ValueError("Missing original odds or official result")
            doc=fetch(spec["url"])
            rows,rejected=extract(doc,spec,base,official,datetime.now(timezone.utc))
            for row in rows:
                ids=lookup[norm(row["name"])]
                row["suggested_id"]=next(iter(ids)) if len(ids)==1 else None
                row["draw_number"]=draw
            report["rows"].extend(rows)
            report["matches"].append({"draw":draw,"number":spec["number"],"accepted":len(rows),"rejected":rejected})
            print("IMPORT",draw,spec["number"],len(rows),rejected,flush=True)
        except Exception as exc:
            report["errors"].append({"draw":spec["draw"],"number":spec["number"],"error":str(exc)})
            print("ERROR",spec["draw"],spec["number"],str(exc),flush=True)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("TOTAL",len(report["rows"]),"matches",len(report["matches"]),"errors",len(report["errors"]))
    if report["errors"]: raise SystemExit(1)

if __name__=="__main__":
    main()
