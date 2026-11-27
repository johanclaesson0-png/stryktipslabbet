"""Rebuild a research-only canonical provenance store from five exact reviewed
GitHub Actions exports. No network, no raw quotations, no production changes."""
import argparse,json,hashlib,re,unicodedata
from collections import Counter,defaultdict
from pathlib import Path
from scripts.v25_history import read,instant
from scripts.v25_forecastrecord import URL
from scripts.v25_forecastrecord_api import team

ARTIFACTS={
"initial":(15233213903,"forecastrecord-review.json","41821ba467243fac2a362dc1ceebb90d992c7ac4b23b55d97969d7bf19de6425"),
"incremental":(15234058123,"forecastrecord-historical-review.json","44167b70af17776333b5c53e0e8cd98d1d3de83b200a7b2314be661cf"),
"bulk":(15235445280,"september-review.json","e80e4a6189225a859e7f84a4450c7e5a7848b9bbfcaaec3d937f756817980b35"),
"metadata":(15235172093,"official-metadata-review.json","b4e7eadb58eda1e9d191c35e09e67a42962ada346cb8affb0718f3f20a2e2cef"),
"league":(15235356325,"league-review.json","0b18f66a95a99f161cd54a053fb2a25b8e708ab8245f759bcf244ff8997a4d9b")}
ALIASES={"spanien":"spain","tjeckien":"czechia","czech republic":"czechia","kroatien":"croatia","nordmakedonien":"north macedonia","skottland":"scotland","schweiz":"switzerland","slovenien":"slovenia","cambridge":"cambridge united","huddersfield":"huddersfield town","brighton":"brighton hove albion","blackburn":"blackburn rovers","cardiff":"cardiff city","preston":"preston north end","west bromwich":"west bromwich albion","plymouth":"plymouth argyle","sheffield w":"sheffield wednesday","swansea":"swansea city","birmingham":"birmingham city"}
FIELDS=("external_id","name","publisher","kind","number","home","away","type","sign","source","record_url","source_at","observed_at","evidence","league","record_id","draw_number","event_id","kickoff","result_received_at","actual","result_source")

def alias(s):
    v=s.strip().casefold()
    return "".join(c for c in unicodedata.normalize("NFKD",ALIASES.get(v,v)) if c.isascii() and c.isalnum())

def load(root,key):
    aid,name,h=ARTIFACTS[key]
    raw=(root/key/name).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=h:raise ValueError("Unexpected source hash "+key)
    return json.loads(raw)

def clean(r,artifact):
    if r["type"]!="result" or r["sign"] not in ("1","X","2") or r["evidence"]!="archive_recorded" or not URL.fullmatch(r["source"]) or not r["record_url"].startswith("https://forecastrecord.com/") or not re.fullmatch(r"n-[a-zA-Z0-9]+",r["record_id"]) or not re.fullmatch(r"/(?:authors|sources)/[a-z0-9-]+/(?:products/[a-z0-9-]+/)?",r["external_id"]) or instant(r["source_at"])>instant(r["observed_at"]):
        raise ValueError("Invalid claim")
    return {**{k:r[k] for k in FIELDS if k in r},"source_artifact_id":artifact}

def index_metadata(meta,archive):
    index={}
    if meta["errors"]:raise ValueError("Incomplete official metadata")
    for d in meta["rounds"]:
        draw=d["draw"]
        a=archive[draw]
        if d["date"]!=a["date"] or len(d["matches"])!=13:raise ValueError("Archive mismatch")
        for m in d["matches"]:
            orig=a["matches"][m["number"]-1]
            if m["archive"]!=[orig["home"],orig["away"]]:raise ValueError("Stored fixture changed")
            if not m["normalized_match"] and list(map(alias,m["official"]))!=list(map(alias,m["archive"])):
                raise ValueError("Unresolved official name")
            index[(draw,m["number"])]=(d["reg_close_time"],m)
    if len(index)!=91:raise ValueError("Incomplete official positions")
    return index

def profile(rows):
    counts=defaultdict(lambda:{"n":0,"hits":0,"leagues":{},"signs":{}})
    seen=set()
    for r in rows:
        fixture=(r.get("draw_number"),r.get("number")) if "draw_number" in r else r["event_id"]
        key=(r["external_id"],fixture)
        if key in seen:raise ValueError("Duplicate identity on fixture")
        seen.add(key)
        c=counts[r["external_id"]];hit=int(r["sign"]==r["actual"]);c["n"]+=1;c["hits"]+=hit
        c["name"]=r["name"];c["kind"]=r["kind"]
        for field,k in (("leagues",r["league"]),("signs",r["sign"])):
            v=c[field].setdefault(k,{"n":0,"hits":0});v["n"]+=1;v["hits"]+=hit
    return [{"external_id":k,**v} for k,v in sorted(counts.items())]

def build(artifacts,data,out):
    docs={k:load(artifacts,k) for k in ARTIFACTS}
    archive={r["draw"]:r for r in read(data/"history/summary.json")["archive"]}
    pools=read(data/"history/official_pools.json")["draws"]
    idx=index_metadata(docs["metadata"],archive)
    historical=[];current=[];external=[];late=[]
    for key in ("initial","incremental","bulk"):
        aid=ARTIFACTS[key][0]
        for raw in docs[key]["rows"]:
            r=clean(raw,aid); draw=r["draw_number"];n=r["number"]
            if type(n)!=int or not 1<=n<=13:raise ValueError("Invalid position")
            if raw.get("cutoff_status")=="kickoff_only":
                close,m=idx[(draw,n)]
                a=archive[draw];match=a["matches"][n-1]
                if [r["home"],r["away"]]!=m["archive"] or not match["played_consistent"] or instant(r["kickoff"])!=instant(m["kickoff"]) or pools[str(draw)]["outcome"]!=a["outcome"]:
                    raise ValueError("Archived fixture/score mismatch")
                r.update({"reg_close_time":close,"metadata_artifact_id":ARTIFACTS["metadata"][0],"actual":a["outcome"][n-1]})
                if instant(r["source_at"])>=min(instant(close),instant(r["kickoff"])):
                    r["cutoff_status"]="excluded_after_cutoff";late.append(r);continue
                r["cutoff_status"]="verified_coupon_reconciled"
            else:
                base=read(data/"analysis"/f"{draw}.json")
                m=base["matches"][n-1];close=base["reg_close_time"]
                if (m["home"],m["away"])!=(r["home"],r["away"]) or instant(r["source_at"])>=instant(close):
                    raise ValueError("Frozen fixture/cutoff mismatch")
                r["reg_close_time"]=close
                if raw.get("cutoff_status")=="prospective_review":
                    if instant(r["observed_at"])>=instant(close):raise ValueError("Late prospective observation")
                    r["cutoff_status"]="prospective_review";current.append(r);continue
                official=read(data/"results"/f"{draw}.json")
                if official["draw_number"]!=draw or len(official["outcome"])!=13:raise ValueError("Official result mismatch")
                r.update({"actual":official["outcome"][n-1],"cutoff_status":"verified_coupon"})
            if r["actual"] not in ("1","X","2"):raise ValueError("Invalid outcome")
            historical.append(r)
    for raw in docs["league"]["rows"]:
        r=clean(raw,ARTIFACTS["league"][0])
        if r["actual"] not in ("1","X","2") or not instant(r["source_at"])<instant(r["kickoff"])<instant(r["result_received_at"])<=instant(r["observed_at"]):raise ValueError("Invalid external timeline")
        r["cutoff_status"]="kickoff_only_external";r["result_source"]="Forecast Record, not independently verified";external.append(r)
    rows=historical+current+external+late
    if len({r["record_id"] for r in rows})!=len(rows):raise ValueError("Duplicate record IDs")
    if (len(historical),len(current),len(external),len(late))!=(909,18,154,9):raise ValueError("Unexpected reviewed batch counts")
    out.mkdir(parents=True,exist_ok=True)
    def save(name,doc):(out/name).write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for name,rs in (("historical_coupon",historical),("prospective_review",current),("external_league",external),("excluded_late",late)):
        save(name+".json",{"schema":"v31-"+name+"-v1","source":"https://forecastrecord.com/api/","rows":rs})
    save("profiles.json",{"schema":"v31-descriptive-profiles-v1","historical_coupon":profile(historical),"external_league_unverified_results":profile(external),"warning":"Separate descriptive counts; no odds adjustment or production weights."})
    summary={"schema":"v31-canonical-review-v1","historical_coupon":len(historical),"historical_positions":len({(r["draw_number"],r["number"]) for r in historical}),"historical_identities":len({r["external_id"] for r in historical}),"historical_human_identities":len({r["external_id"] for r in historical if r["kind"]=="human"}),"by_draw":dict(sorted(Counter(r["draw_number"] for r in historical).items())),"current_review":len(current),"external_league":len(external),"excluded_late":len(late),"sources":{k:{"artifact_id":v[0],"filename":v[1],"sha256":v[2]} for k,v in ARTIFACTS.items()},"warning":"Retrospective data. Older rounds have no verified preclose odds. External league results are from provider. No production or model-training integration."}
    save("manifest.json",summary);print("V31 CANONICAL",json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--artifacts",required=True);p.add_argument("--data",default="data");p.add_argument("--output",default="data/v31");a=p.parse_args();build(Path(a.artifacts),Path(a.data),Path(a.output))
