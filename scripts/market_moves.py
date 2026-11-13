#!/usr/bin/env python3
"""Version 13: observable odds and crowd movements from *actual* frozen archives.

Nothing uses results, and no historical pre-close observations are invented.
Reports are created before close and retain source timestamps and hashes.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from scripts.analyze import valid_analysis
from scripts.collect import write_json
from scripts.publish import instant

SCHEMA = "stryktipslabbet-market-moves-v1"
VERSION = "movement-observed-v13-20261113"
MAX_POINTS = 48


def history_for(data, current, now):
    """Return trustworthy immutable observations of the SAME fixture list."""
    results = []
    source = (data / "analysis_history" / str(current["draw_number"]))
    keys = [(m["number"], m["home"], m["away"]) for m in current["matches"]]
    for file in sorted(source.glob("*.json")):
        try:
            entry = json.loads(file.read_text(encoding="utf-8"))
            if (not valid_analysis(entry, now)
                or entry["draw_number"] != current["draw_number"]
                or entry["reg_close_time"] != current["reg_close_time"]
                or [(m["number"], m["home"], m["away"]) for m in entry["matches"]] != keys
                or not entry.get("source_snapshot_sha256")):
                continue
            results.append(entry)
        except (KeyError, ValueError, TypeError, OSError, json.JSONDecodeError):
            continue
    results.append(current)
    by_time = {e["observed_at_utc"]: e for e in results}
    results = sorted(by_time.values(), key=lambda e: instant(e["observed_at_utc"]))
    # retain earliest + recent, avoiding unbounded chart payloads
    if len(results) > MAX_POINTS:
        results = [results[0], *results[-(MAX_POINTS-1):]]
    return results


def build(current, history, created=None):
    now = created or datetime.now(timezone.utc)
    if not valid_analysis(current, now):
        raise ValueError("Ogiltig förhandsanalys")
    if not instant(current["observed_at_utc"]) <= now < instant(current["reg_close_time"]):
        raise ValueError("Rörelser måste frysas före spelstopp")
    if len(history) < 2:
        raise ValueError("Minst två verkliga observationer krävs")
    history = sorted(history, key=lambda a: instant(a["observed_at_utc"]))
    if history[-1]["observed_at_utc"] != current["observed_at_utc"]:
        raise ValueError("Senaste observationen är inte basprognosen")
    times = [instant(x["observed_at_utc"]) for x in history]
    if len(set(times)) != len(times):
        raise ValueError("Duplicerad observation")
    expected_keys = [(m["number"], m["home"], m["away"]) for m in current["matches"]]
    for x in history:
        if (not valid_analysis(x, now)
            or x["draw_number"] != current["draw_number"]
            or x["reg_close_time"] != current["reg_close_time"]
            or [(m["number"],m["home"],m["away"]) for m in x["matches"]] != expected_keys):
            raise ValueError("En observation gäller fel kupong")
    matches = []
    for i in range(13):
        points = []
        for x in history:
            m = x["matches"][i]
            points.append({
                "at_utc": x["observed_at_utc"],
                "p": m["p"][:],
                "streck": m["streck"][:],
                "odds": m["odds"][:],
            })
        start, end = points[0], points[-1]
        market_delta = [round(100*(end["p"][j] - start["p"][j]), 2) for j in range(3)]
        crowd_delta = [round(end["streck"][j] - start["streck"][j], 2) for j in range(3)]
        widest = max(range(3), key=lambda j: abs(market_delta[j]))
        matches.append({
            "number": i+1, "home": current["matches"][i]["home"],
            "away": current["matches"][i]["away"],
            "observations": points,
            "market_delta_pp": market_delta,
            "streck_delta_pp": crowd_delta,
            "largest_movement_sign": "1X2"[widest],
            "largest_abs_market_movement_pp": round(abs(market_delta[widest]), 2),
            "notable_market_movement": max(abs(x) for x in market_delta) >= 3.0,
            "notable_crowd_movement": max(abs(x) for x in crowd_delta) >= 5.0,
        })
    return {
        "schema": SCHEMA, "version": VERSION,
        "draw_number": current["draw_number"],
        "observed_at_utc": current["observed_at_utc"],
        "reg_close_time": current["reg_close_time"],
        "source_snapshot_sha256": current.get("source_snapshot_sha256"),
        "created_at_utc": now.isoformat(),
        "first_observation_at_utc": history[0]["observed_at_utc"],
        "observation_count": len(history),
        "source_observations": [{"at_utc": x["observed_at_utc"],
                                 "snapshot_sha256": x.get("source_snapshot_sha256")}
                                for x in history],
        "matches": matches,
        "description": ("Sannolikhetsförändringar beräknade endast från lagrade "
                        "förhandsodds. Förändringen är inte ett värdebevis."),
    }


def validate(report, current, history):
    try:
        if report.get("schema") != SCHEMA or report.get("version") != VERSION:
            return False
        when = instant(report["created_at_utc"])
        if report["draw_number"] != current["draw_number"]:
            return False
        if report["observed_at_utc"] != current["observed_at_utc"]:
            return False
        if report["reg_close_time"] != current["reg_close_time"]:
            return False
        if report.get("source_snapshot_sha256") != current.get("source_snapshot_sha256"):
            return False
        return report == build(current, history, created=when)
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return False


def main():
    arg = argparse.ArgumentParser()
    arg.add_argument("--outdir", default="data")
    args = arg.parse_args()
    root = Path(args.outdir)
    now = datetime.now(timezone.utc)
    created = 0
    for file in sorted((root / "analysis").glob("*.json")):
        try:
            current = json.loads(file.read_text(encoding="utf-8"))
            if now >= instant(current["reg_close_time"]):
                continue
            all_prior = history_for(root, current, now)
            if len(all_prior) < 2:
                continue
            dest = root / "market_moves" / file.name
            if dest.exists():
                old = json.loads(dest.read_text(encoding="utf-8"))
                if old.get("observed_at_utc") == current["observed_at_utc"] and validate(old, current, all_prior):
                    continue
                hist = root / "market_moves_history" / str(current["draw_number"]) / (
                    old["observed_at_utc"].replace(":", "_")+".json")
                if not hist.exists():
                    write_json(hist, old)
            report = build(current, all_prior, created=now)
            if not validate(report, current, all_prior):
                raise ValueError("Inkonsekvent rörelserapport")
            write_json(dest, report)
            created += 1
        except (KeyError, ValueError, TypeError, OSError, json.JSONDecodeError) as exc:
            print("Marknadsrörelse hoppades över:", file, str(exc), file=sys.stderr)
    print("Nya frysta marknadsrörelser:", created)


if __name__ == "__main__":
    main()
