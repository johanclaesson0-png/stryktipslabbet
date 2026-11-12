#!/usr/bin/env python3
"""Generate a minimal public GitHub Pages site from validated, time-stamped data.

The Pages artifact excludes raw API responses, Python sources, private exports,
test fixtures, and internal snapshots. This script never invents live data.
"""
from datetime import datetime, timezone
from pathlib import Path
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
    for p in (root / "data" / "snapshots").glob("*/*.json"):
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
            if valid_snapshot(snap, now):
                closes[snap["draw_number"]] = instant(snap["reg_close_time"])
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
    (dest / "data" / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Publika filer:", [str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()])


if __name__ == "__main__":
    main()
