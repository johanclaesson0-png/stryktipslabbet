#!/usr/bin/env python3
"""Read-only Stryktipset observation/settlement collector.

Snapshots are timestamped when actually fetched, never reconstructed or backdated.
Official results are stored separately, only for draws with a valid pre-close snapshot.
No logins, betting actions, or private data.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen

BASE = "https://api.spela.svenskaspel.se/draw/1/stryktipset"
UA = "Stryktipslabbet/8.0 (research, read-only)"
LIVE_SCHEMA = "stryktipslabbet-live-snapshot-v7"
RESULT_SCHEMA = "stryktipslabbet-result-v7"


def utc(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Tidszon saknas")
    return dt.astimezone(timezone.utc)


def number(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Tal saknas")
    d = Decimal(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
    if not d.is_finite():
        raise ValueError("Ogiltigt tal")
    return float(d)


def triplet(o, kind):
    if not isinstance(o, dict):
        raise ValueError("Ogiltig " + kind)
    p = [number(o.get(k)) for k in ("one", "x", "two")]
    if kind == "odds" and not all(1 < x < 10000 for x in p):
        raise ValueError("Ogiltiga odds")
    if kind == "streck" and (not all(0 <= x <= 100 for x in p) or not 98.9 <= sum(p) <= 101.1):
        raise ValueError("Ogiltiga folkstreck")
    return p


def fetch(path):
    req = Request(BASE + path, headers={"Accept": "application/json", "User-Agent": UA})
    with urlopen(req, timeout=20) as resp:
        if resp.status != 200:
            raise ValueError("HTTP " + str(resp.status))
        raw = resp.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("För stort API-svar")
    return json.loads(raw), raw


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def parse_draw(doc, expected, fetched):
    draw = doc.get("draw")
    if not isinstance(draw, dict):
        raise ValueError("Saknar draw")
    if (str(draw.get("drawNumber")) != str(expected) or
        draw.get("productName") != "Stryktipset" or str(draw.get("productId")) != "1"):
        raise ValueError("Fel produkt eller omgång")
    if draw.get("drawState") not in ("Open", "NotOpened", "Upcoming"):
        raise ValueError("Omgången är inte öppen/kommande")
    close = utc(draw.get("regCloseTime"))
    if fetched >= close:
        raise ValueError("Spelstopp passerat")
    events = draw.get("drawEvents")
    if not isinstance(events, list) or len(events) != 13 or sorted(e.get("eventNumber") for e in events) != list(range(1, 14)):
        raise ValueError("Kupongen ska ha 13 unika matcher")
    matches = []
    for e in sorted(events, key=lambda v: v["eventNumber"]):
        m = e.get("match") or {}
        participants = m.get("participants") or []
        names = {}
        for side in ("home", "away"):
            v = [p.get("name") for p in participants if isinstance(p, dict) and p.get("type") == side]
            if len(v) != 1 or not isinstance(v[0], str) or not v[0].strip():
                raise ValueError("Lagidentitet saknas")
            names[side] = v[0].strip()
        if names["home"] == names["away"]:
            raise ValueError("Samma lag")
        kickoff = m.get("matchStart")
        if kickoff and utc(kickoff) <= fetched:
            raise ValueError("Matchen har börjat")
        if e.get("cancelled") or m.get("sportEventStatus") in ("Started", "InProgress", "Finished", "Cancelled"):
            raise ValueError("Matchen inställd eller påbörjad")
        matches.append({
            "number": e["eventNumber"], "home": names["home"], "away": names["away"],
            "odds": triplet(e.get("odds"), "odds"),
            "streck": triplet(e.get("svenskaFolket"), "streck"),
            "match_start": kickoff,
            "streck_source_updated_at": (e.get("svenskaFolket") or {}).get("date")
        })
    # This is an observed IN-PROGRESS net sale, not the final turnover.
    # Preserve its observation timestamp; never retroactively insert into
    # old preclose snapshots or present it as settled turnover.
    current_sale=None
    if draw.get("currentNetSale") is not None:
        x=number(draw["currentNetSale"])
        if 0<=x<=500_000_000 and x.is_integer():
            current_sale=int(x)
    return {
        "observed_turnover_so_far_kr":current_sale,
        "sales_observed_at_utc":fetched.isoformat() if current_sale is not None else None,
        "schema": LIVE_SCHEMA, "source": "Svenska Spel publikt API",
        "source_url": BASE + "/draws/" + str(expected),
        "draw_number": expected, "observed_at_utc": fetched.isoformat(),
        "reg_close_time": close.isoformat(), "draw_state": draw["drawState"],
        "matches": matches
    }


def choose_draw(doc, now):
    ds = doc.get("draws") if isinstance(doc, dict) else None
    if not isinstance(ds, list):
        raise ValueError("Saknar draws")
    options = []
    for d in ds:
        try:
            if d.get("drawState") in ("Open", "NotOpened", "Upcoming"):
                close = utc(d["regCloseTime"])
                n = int(d["drawNumber"])
                if n > 0 and close > now:
                    options.append((close, n))
        except (KeyError, ValueError, TypeError):
            continue
    if not options:
        raise ValueError("Ingen öppen/kommande Stryktipsomgång")
    return min(options)[1]


def should_collect(latest, now):
    if not isinstance(latest, dict) or latest.get("schema") != LIVE_SCHEMA:
        return True
    try:
        close = utc(latest["reg_close_time"])
        observed = utc(latest["observed_at_utc"])
        if close <= now or observed > now:
            return True
        hours = (close - now).total_seconds() / 3600
        interval_h = 6 if hours > 48 else 2 if hours > 24 else 1 if hours > 6 else .5
        return (now - observed).total_seconds() >= interval_h * 3600
    except (ValueError, KeyError, TypeError):
        return True


def collect_draw(out, now):
    path = out / "latest.json"
    try:
        latest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        latest = None
    if not should_collect(latest, now):
        print("Aktuell observation är tillräckligt ny, hoppar över")
        return
    listing, _ = fetch("/draws")
    n = choose_draw(listing, now)
    time.sleep(1)
    rawdoc, original = fetch("/draws/" + str(n))
    fetched = datetime.now(timezone.utc)
    snap = parse_draw(rawdoc, n, fetched)
    h = sha256(original).hexdigest()
    snap["sha256"] = h
    name = fetched.strftime("%Y%m%dT%H%M%SZ") + "-" + h[:12] + ".json"
    sn = out / "snapshots" / str(n) / name
    orig = out / "raw" / str(n) / name
    sn.parent.mkdir(parents=True, exist_ok=True)
    orig.parent.mkdir(parents=True, exist_ok=True)
    with orig.open("xb") as f:
        f.write(original)
    write_json(sn, snap)
    write_json(path, snap)
    print("Sparade förhandsobservation för", n)


def parse_result(doc, draw, observed):
    raw = doc.get("result")
    if not isinstance(raw, dict) or str(raw.get("drawNumber")) != str(draw) or raw.get("productName") != "Stryktipset":
        raise ValueError("Fel resultat")
    events = raw.get("events")
    if not isinstance(events, list) or len(events) != 13 or sorted(e.get("eventNumber") for e in events) != list(range(1, 14)):
        raise ValueError("Ofullständigt facit")
    outcome = "".join(str(e.get("outcome", "")).upper() for e in sorted(events, key=lambda x: x["eventNumber"]))
    if len(outcome) != 13 or any(s not in "1X2" for s in outcome):
        raise ValueError("Ogiltigt facit")
    payouts = {}
    for e in raw.get("distribution") or []:
        found = re.fullmatch(r"(1[0-3]) r[äa]tt", str(e.get("name", "")).strip(), re.I)
        if found:
            k = found.group(1)
            if k in payouts:
                raise ValueError("Duplicerad utdelningsklass")
            amt = number(e.get("amount"))
            if amt < 0:
                raise ValueError("Negativ utdelning")
            payouts[k] = amt
    if set(payouts) != {"10", "11", "12", "13"}:
        raise ValueError("Utdelningar saknas")
    return {
        "schema": RESULT_SCHEMA, "source": "Svenska Spel publikt resultat-API",
        "source_url": BASE + "/draws/" + str(draw) + "/result",
        "draw_number": draw, "observed_at_utc": observed.isoformat(),
        "outcome": outcome, "payouts": payouts
    }


def collect_results(out, now, limit=3):
    saved = 0
    for folder in sorted((out / "snapshots").glob("*")):
        if not folder.is_dir() or not folder.name.isdigit():
            continue
        n = int(folder.name)
        dest = out / "results" / (str(n) + ".json")
        if dest.exists():
            continue
        files = sorted(folder.glob("*.json"))
        if not files:
            continue
        try:
            snap = json.loads(files[0].read_text(encoding="utf-8"))
            if snap.get("schema") != LIVE_SCHEMA or utc(snap["observed_at_utc"]) >= utc(snap["reg_close_time"]):
                continue
            if utc(snap["reg_close_time"]) >= now:
                continue
            doc, original = fetch("/draws/" + str(n) + "/result")
            fetched = datetime.now(timezone.utc)
            result = parse_result(doc, n, fetched)
            h = sha256(original).hexdigest()
            result["sha256"] = h
            orig = out / "raw_results" / (str(n) + "-" + h[:12] + ".json")
            orig.parent.mkdir(parents=True, exist_ok=True)
            with orig.open("xb") as f:
                f.write(original)
            write_json(dest, result)
            print("Sparade facit för", n)
            saved += 1
            if saved >= limit:
                break
            time.sleep(1)
        except Exception as exc:
            print("Facit ej färdigt/verifierat för", n, ":", str(exc), file=sys.stderr)
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data")
    opts = ap.parse_args()
    out = Path(opts.outdir)
    now = datetime.now(timezone.utc)
    try:
        collect_draw(out, now)
    except Exception as exc:
        print("Ingen ny godkänd kupongobservation:", type(exc).__name__, str(exc), file=sys.stderr)
    try:
        collect_results(out, datetime.now(timezone.utc))
    except Exception as exc:
        print("Ingen ny resultatobservation:", type(exc).__name__, str(exc), file=sys.stderr)


if __name__ == "__main__":
    main()
