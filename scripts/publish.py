#!/usr/bin/env python3
"""Generate a minimal public GitHub Pages site from validated, time-stamped data.

The Pages artifact excludes raw API responses, Python sources, private exports,
test fixtures, and internal snapshots. This script never invents live data.
"""
from datetime import datetime, timezone
from pathlib import Path
import csv
import json
import math
import shutil

LIVE = "stryktipslabbet-live-snapshot-v7"
RESULT = "stryktipslabbet-result-v7"


def instant(value):
    v = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if v.tzinfo is None:
        raise ValueError("Tidszon saknas")
    return v.astimezone(timezone.utc)


def valid_snapshot(d, now):
    if not isinstance(d, dict) or d.get("schema") != LIVE:
        return False
    try:
        ts, close = instant(d["observed_at_utc"]), instant(d["reg_close_time"])
        if ts >= close or ts > now:
            return False
        n = d["draw_number"]
        if type(n) is not int or n <= 0:
            return False
        ms = d["matches"]
        if len(ms) != 13 or sorted(m["number"] for m in ms) != list(range(1, 14)):
            return False
        for m in ms:
            if not all(isinstance(m.get(k), str) and m[k].strip() for k in ("home", "away")):
                return False
            for typ in ("odds", "streck"):
                v = m.get(typ)
                if not isinstance(v, list) or len(v) != 3:
                    return False
                if not all(type(x) in (int, float) and math.isfinite(x) for x in v):
                    return False
                if typ == "odds" and not all(1 < x < 10000 for x in v):
                    return False
                if typ == "streck" and (not all(0 <= x <= 100 for x in v) or not 98.9 <= sum(v) <= 101.1):
                    return False
        return True
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def valid_result(d, closes, now):
    if not isinstance(d, dict) or d.get("schema") != RESULT:
        return False
    try:
        n, when = d["draw_number"], instant(d["observed_at_utc"])
        if type(n) is not int or n not in closes or when < closes[n] or when > now:
            return False
        out = d["outcome"]
        if len(out) != 13 or any(c not in "1X2" for c in out):
            return False
        p = d["payouts"]
        return all(type(p.get(str(i))) in (int, float) and math.isfinite(p[str(i)])
                   and 0 <= p[str(i)] < 1e10 for i in (10, 11, 12, 13))
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def main():
    root = Path(".")
    dest = Path(".site")
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "data").mkdir(parents=True)
    shutil.copy2(root / "index.html", dest / "index.html")
    shutil.copy2(root / "status.html", dest / "status.html")
    shutil.copy2(root / "veckans-analys.html", dest / "veckans-analys.html")
    shutil.copy2(root / "fordjupning.html", dest / "fordjupning.html")
    shutil.copy2(root / "spela-sjalv.html", dest / "spela-sjalv.html")

    now = datetime.now(timezone.utc)
    status = {
        "schema": "stryktipslabbet-public-status-v8",
        "generated_at_utc": now.isoformat(),
        "snapshot_available": False,
        "snapshot_usable_now": False,
        "latest_observed_at_utc": None,
        "latest_draw_number": None,
        "reg_close_time": None,
        "results_published": 0,
        "note": "Inga garanterade liveuppgifter; kontrollera tidsstämplarna."
    }

    latest = root / "data" / "latest.json"
    if latest.exists():
        try:
            snap = json.loads(latest.read_text(encoding="utf-8"))
            if valid_snapshot(snap, now):
                shutil.copy2(latest, dest / "data" / "latest.json")
                status.update({
                    "snapshot_available": True,
                    "latest_observed_at_utc": snap["observed_at_utc"],
                    "latest_draw_number": snap["draw_number"],
                    "reg_close_time": snap["reg_close_time"],
                    "snapshot_usable_now": instant(snap["reg_close_time"]) > now
                })
        except (OSError, json.JSONDecodeError):
            pass

    closes = {}
    source_snapshots = {}
    for p in (root / "data" / "snapshots").glob("*/*.json"):
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
            if valid_snapshot(snap, now):
                closes[snap["draw_number"]] = instant(snap["reg_close_time"])
                prior = source_snapshots.get(snap["draw_number"])
                if prior is None or instant(snap["observed_at_utc"]) > instant(prior["observed_at_utc"]):
                    source_snapshots[snap["draw_number"]] = snap
        except (OSError, json.JSONDecodeError):
            pass
    good = []
    for p in (root / "data" / "results").glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if valid_result(data, closes, now):
                good.append((data["draw_number"], p))
        except (OSError, json.JSONDecodeError):
            pass
    for n, p in sorted(good)[-30:]:
        folder = dest / "data" / "results"
        folder.mkdir(exist_ok=True)
        shutil.copy2(p, folder / (str(n) + ".json"))
    status["results_published"] = min(len(good), 30)

    # Publicera bara analyser som bevisligen byggts från exakt de arkiverade
    # uppgifterna före spelstopp. Tillåt inte importerade efterhandsodds.
    def approved_analysis(a):
        try:
            if not isinstance(a, dict) or a.get("schema") != "stryktipslabbet-frozen-analysis-v1":
                return False
            if a.get("model_version") != "market-no-vig-v1" or a.get("budget_limit") != 1800:
                return False
            n = a["draw_number"]
            src = source_snapshots.get(n)
            if not src or a["observed_at_utc"] != src["observed_at_utc"]:
                return False
            if a["reg_close_time"] != src["reg_close_time"] or a.get("source_snapshot_sha256") != src.get("sha256"):
                return False
            if len(a["matches"]) != 13 or len(a["systems"]) != 3:
                return False
            for m, orig in zip(a["matches"], sorted(src["matches"], key=lambda row: row["number"])):
                if (m["number"] != orig["number"] or m["home"] != orig["home"] or m["away"] != orig["away"] or
                    m["odds"] != orig["odds"] or m["streck"] != orig["streck"]):
                    return False
                p = [1.0/x for x in orig["odds"]]
                total = sum(p)
                if len(m["p"]) != 3 or any(abs(m["p"][i] - p[i]/total) > .000001 for i in range(3)):
                    return False
            for system in a["systems"]:
                c = system["choices"]
                if len(c) != 13 or any(not isinstance(s, str) or not s or
                                       "".join(t for t in "1X2" if t in s) != s for s in c):
                    return False
                if system["cost"] != math.prod(len(s) for s in c) or not 1 <= system["cost"] <= 1800:
                    return False
                if not 0 < system["p13_estimate"] <= 1:
                    return False
            return True
        except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
            return False

    report_index = []
    verified_result_draws = {n for n, _ in good}
    for p in (root / "data" / "analysis").glob("*.json"):
        try:
            item = json.loads(p.read_text(encoding="utf-8"))
            if approved_analysis(item):
                report_index.append(item)
        except (OSError, json.JSONDecodeError):
            pass
    report_index.sort(key=lambda a: a["draw_number"], reverse=True)
    for item in report_index[:52]:
        n = item["draw_number"]
        source = root / "data" / "analysis" / (str(n) + ".json")
        destination = dest / "data" / "analysis" / (str(n) + ".json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    public_rounds = []
    for item in report_index[:52]:
        n = item["draw_number"]
        settlement_file = root / "data" / "settlements" / (str(n) + ".json")
        paid = False
        if n in verified_result_draws and settlement_file.exists():
            try:
                settled = json.loads(settlement_file.read_text(encoding="utf-8"))
                official = json.loads((root / "data" / "results" / (str(n) + ".json")).read_text(encoding="utf-8"))
                if (settled.get("schema") == "stryktipslabbet-settlement-v1" and
                    settled.get("draw_number") == n and
                    settled.get("forecast_observed_at_utc") == item["observed_at_utc"] and
                    settled.get("outcome") == official.get("outcome") and
                    settled.get("payouts") == official.get("payouts") and
                    settled.get("source_snapshot_sha256") == item.get("source_snapshot_sha256") and
                    len(settled.get("systems", [])) == 3):
                    target = dest / "data" / "settlements" / (str(n) + ".json")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(settlement_file, target)
                    paid = True
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                pass
        public_rounds.append({
            "draw_number": n,
            "observed_at_utc": item["observed_at_utc"],
            "reg_close_time": item["reg_close_time"],
            "settled": paid,
            "current": instant(item["reg_close_time"]) > now,
        })

    # 100-kronorssystem publiceras bara när de kan jämföras med en redan
    # godkänd förhandsanalys. Ingen utbetalning gissas eller rekonstrueras.
    base_by_draw = {a["draw_number"]: a for a in report_index}
    for row in public_rounds:
        n = row["draw_number"]
        solo_source = root / "data" / "personal" / (str(n) + ".json")
        solo_valid = False
        solo_settled = False
        try:
            original = base_by_draw[n]
            solo = json.loads(solo_source.read_text(encoding="utf-8"))
            if (solo.get("schema") == "stryktipslabbet-personal-100-v1" and
                solo.get("model_version") == original["model_version"] and
                solo.get("draw_number") == n and
                solo.get("original_observed_at_utc") == original["observed_at_utc"] and
                solo.get("source_snapshot_sha256") == original.get("source_snapshot_sha256") and
                solo.get("reg_close_time") == original["reg_close_time"] and
                solo.get("max_budget") == 100 and
                len(solo["systems"]) == 3):
                solo_valid = True
                for s in solo["systems"]:
                    selections = s["choices"]
                    if (len(selections) != 13 or
                        any(not c or any(x not in "1X2" for x in c) or len(set(c)) != len(c) for c in selections)):
                        solo_valid = False
                        break
                    costs = math.prod(len(c) for c in selections)
                    if costs != s["cost"] or not 1 <= costs <= 100:
                        solo_valid = False
                        break
                    p13 = math.prod(
                        sum(m["p"]["1X2".index(x)] for x in c)
                        for m, c in zip(original["matches"], selections)
                    )
                    if abs(p13 - s["probability_all_13"]) > 0.000001:
                        solo_valid = False
                        break
            if solo_valid:
                path = dest / "data" / "personal" / (str(n) + ".json")
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(solo_source, path)
                if n in verified_result_draws:
                    original_result = json.loads(
                        (root / "data" / "results" / (str(n) + ".json")).read_text(encoding="utf-8"))
                    payout_file = root / "data" / "personal_settlements" / (str(n) + ".json")
                    if payout_file.exists():
                        record = json.loads(payout_file.read_text(encoding="utf-8"))
                        if (record.get("schema") == "stryktipslabbet-personal-settlement-v1" and
                            record.get("draw_number") == n and
                            record.get("source_snapshot_sha256") == original.get("source_snapshot_sha256") and
                            record.get("source_observed_at_utc") == original["observed_at_utc"] and
                            record.get("outcome") == original_result["outcome"] and
                            record.get("payouts") == original_result["payouts"] and
                            len(record.get("systems", [])) == 3):
                            target = dest / "data" / "personal_settlements" / (str(n) + ".json")
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(payout_file, target)
                            solo_settled = True
        except (OSError, ValueError, TypeError, KeyError, ZeroDivisionError, json.JSONDecodeError):
            pass
        row["personal_available"] = solo_valid
        row["personal_settled"] = solo_settled

    # Enbart offentlig sammanfattning av den kronologiska äldre Elo-modellen.
    # Den nya oddsmodellen får inte ärva det äldre testets resultat.
    path = root / "data" / "2024-2026-elo-100kr-jamforelse.csv"
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as f:
            history = list(csv.DictReader(f, delimiter=";"))
        if len(history) >= 100:
            budgets = {}
            for budget in (100, 1800):
                suffix = str(budget)
                budgets[suffix] = {
                    "spent": sum(int(r["cost"+suffix]) for r in history),
                    "rounds_with_10_or_more": sum(
                        any(int(r["n"+str(k)+"_"+suffix]) > 0 for k in (10, 11, 12, 13))
                        for r in history
                    ),
                    "rows_13": sum(int(r["n13_"+suffix]) for r in history),
                    "rows_12": sum(int(r["n12_"+suffix]) for r in history),
                    "rows_11": sum(int(r["n11_"+suffix]) for r in history),
                    "rows_10": sum(int(r["n10_"+suffix]) for r in history),
                    "expected_13": round(sum(float(r["p13_"+suffix]) for r in history), 6),
                }
            public_history = {
                "schema": "stryktipslabbet-solo-elo-history-v1",
                "model": "experimentell historisk Elo, inte dagens oddsmodell",
                "n_rounds": len(history),
                "from": history[0]["date"], "to": history[-1]["date"],
                "budgets": budgets,
                "note": "Utdelningar för alla 105 omgångar är inte fullständigt verifierade; tabellen visar träffar, inte avkastning."
            }
            (dest / "data" / "solo-history.json").write_text(
                json.dumps(public_history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status["personal_100_analyses_published"] = sum(bool(r["personal_available"]) for r in public_rounds)
    status["personal_100_settlements_published"] = sum(bool(r["personal_settled"]) for r in public_rounds)

    manifest = {
        "schema": "stryktipslabbet-public-analysis-index-v1",
        "generated_at_utc": now.isoformat(),
        "draws": public_rounds,
        "model_version": "market-no-vig-v1",
    }
    (dest / "data" / "analysis-index.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status["automatic_analyses_published"] = len(public_rounds)
    status["automatic_settlements_published"] = sum(d["settled"] for d in public_rounds)

    (dest / "data" / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Publika filer:", [str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()])


if __name__ == "__main__":
    main()
