#!/usr/bin/env python3
"""
01_discover_match_markets.py  —  Stage 3 paper trading, step (1)   [v1.3]

Discover today's / upcoming per-match Kalshi World Cup 2026 markets and emit a
clean, model-ready inventory. READ-ONLY: Kalshi market data is public.

v1.3 fixes (from a live KXWCGAME raw dump):
  * PRICES: Kalshi now exposes dollar-string fields (yes_ask_dollars="0.0700",
    *_fp size/volume fields). We parse those -> integer cents.
  * KICKOFF/WINDOW: match date comes from the event-ticker token (26JUN27), not
    the market open_time (which is the Feb listing date). status=open already
    excludes finished games, so we filter purely on match date.
  * TOTALS: KXWCTOTAL is the per-fixture goal O/U (KXWCTOTALGOAL / KXWCGAMEGOALS
    are tournament aggregates -> excluded).
  * MONEYLINE SIDE: read from rules_primary ("If <team> wins" / "ends in a tie").

Default (curated) full-match series — the model's home turf:
    KXWCGAME (result) · KXWCSPREAD (handicap) · KXWCTOTAL (goal O/U) · KXWCBTTS

Outputs (../data/): match_markets_<UTCSTAMP>.{json,csv} + latest_match_markets.json
Use --debug for the discovery funnel, --discover for the full KXWC* inventory,
--series to set tickers explicitly.

Deps: requests only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone, date

try:
    import requests
except ImportError:
    sys.exit("Need `requests`:  uv add requests   (or)  pip install requests")

# ----------------------------------------------------------------------------- config
BASE_CANDIDATES = [
    os.environ.get("KALSHI_BASE", "").strip() or "https://api.elections.kalshi.com/trade-api/v2",
    "https://api.kalshi.com/trade-api/v2",
]
BASE_CANDIDATES = [b for i, b in enumerate(BASE_CANDIDATES) if b and b not in BASE_CANDIDATES[:i]]

OUTRIGHT_SERIES = "KXMENWORLDCUP"
MATCH_PREFIX = "KXWC"
CORE_SERIES = ["KXWCGAME", "KXWCSPREAD", "KXWCTOTAL", "KXWCBTTS"]  # verified per-fixture

DISCOVER_EXCLUDE = re.compile(
    r"1H|CORNER|SOG|SHOT|SAVE|HATTRICK|FASTEST|FIRSTGOAL|1STGOAL|PEN|FREEKICK|"
    r"GOALIE|PLAYER|LEADER|SQUAD|LOCATION|HOST|CONTINENT|REGION|ROUND|ADVANC|"
    r"AWARD|3RDPLACE|STAGE|ELIM|FIFATOP10|H2H|TEAM|TOTALGOAL|GAMEGOALS", re.I)

DEAD_STATUS = {"settled", "closed", "finalized", "determined", "expired",
               "inactive", "canceled", "cancelled"}

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def series_type(st: str) -> str:
    s = (st or "").upper()
    if "SPREAD" in s:
        return "spread"
    if "BTTS" in s or "BOTHTEAMS" in s or s.endswith("BTS"):
        return "btts"
    if "TOTAL" in s or "OVERUNDER" in s:
        return "total"
    if "GAME" in s or "MONEY" in s or "WINNER" in s or "RESULT" in s:
        return "moneyline"
    return "other"


WC_TITLE_RE = re.compile(r"world\s*cup", re.I)
VS_RE = re.compile(r"\s+(?:vs\.?|v\.?|at|@|\bversus\b|\u2014|\-)\s+", re.I)
KEY_RE = re.compile(r"(\d{2}[A-Z]{3}\d{2})([A-Z]{3})([A-Z]{3})", re.I)
IFWIN_RE = re.compile(r"\bif\s+(.+?)\s+win", re.I)
TIE_RE = re.compile(r"\b(tie|draw)\b|ends?\s+in\s+a\s+tie", re.I)

REQUEST_TIMEOUT = 20
PAGE_LIMIT = 200
SLEEP_BETWEEN = 0.15
MODEL_TYPES = {"moneyline", "total", "spread", "btts"}


# ----------------------------------------------------------------------------- http
class Kalshi:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/json",
                               "User-Agent": "wc2026-paper-discovery/1.3"})
        self.base = self._pick_base()

    def _pick_base(self) -> str:
        for b in BASE_CANDIDATES:
            try:
                r = self.s.get(f"{b}/exchange/status", timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    print(f"[base] using {b}")
                    return b
            except requests.RequestException:
                continue
        print(f"[base] status probe failed; defaulting to {BASE_CANDIDATES[0]}")
        return BASE_CANDIDATES[0]

    def get(self, path, params=None):
        url = f"{self.base}{path}"
        for attempt in range(4):
            r = self.s.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 502, 503, 504):
                time.sleep(0.5 * (attempt + 1))
                continue
            raise RuntimeError(f"GET {path} -> {r.status_code}: {r.text[:300]}")
        raise RuntimeError(f"GET {path} kept failing (rate limit / upstream).")

    def paginate(self, path, params, key):
        params = dict(params)
        params.setdefault("limit", PAGE_LIMIT)
        cursor = None
        while True:
            if cursor:
                params["cursor"] = cursor
            data = self.get(path, params)
            for item in data.get(key, []) or []:
                yield item
            cursor = data.get("cursor")
            if not cursor:
                break
            time.sleep(SLEEP_BETWEEN)


# ----------------------------------------------------------------------------- discovery
def probe_core(k):
    out = []
    for t in CORE_SERIES:
        try:
            evs = list(k.paginate("/events", {"series_ticker": t, "status": "open",
                                              "with_nested_markets": "false"}, "events"))
            print(f"[probe] {t:<14} open events: {len(evs)}")
            if evs:
                out.append(t)
        except RuntimeError as e:
            print(f"[probe] {t:<14} error: {e}")
    return out


def discover_all_kxwc(k):
    catalog = []
    for params in ({"category": "Sports"}, {"category": "Soccer"}, {}):
        try:
            catalog = list(k.paginate("/series", params, "series"))
            if catalog:
                break
        except RuntimeError:
            continue
    found = []
    for s in catalog:
        tk = (s.get("ticker") or "").upper()
        if not tk.startswith(MATCH_PREFIX) or tk == OUTRIGHT_SERIES:
            continue
        if DISCOVER_EXCLUDE.search(tk):
            continue
        if series_type(tk) in MODEL_TYPES:
            found.append(tk)
    return found


# ----------------------------------------------------------------------------- parsing
def parse_event_key(et):
    m = KEY_RE.search(et or "")
    if not m:
        return None, None, None, None
    return (f"{m.group(1).upper()}{m.group(2).upper()}{m.group(3).upper()}",
            m.group(1).upper(), m.group(2).upper(), m.group(3).upper())


def date_from_token(tok):
    if not tok or len(tok) < 7:
        return None
    mo = MONTHS.get(tok[2:5].upper())
    if not mo:
        return None
    try:
        return date(2000 + int(tok[0:2]), mo, int(tok[5:7]))
    except ValueError:
        return None


def parse_teams(title):
    title = re.sub(r"\s*\(.*?\)\s*", " ", title or "").strip()
    parts = VS_RE.split(title, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip() or None, parts[1].strip() or None
    return None, None


def ts(v):
    if v in (None, "", 0):
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
    s = str(v).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def price_c(m, base):
    """Return integer cents for a price field, handling *_dollars strings and legacy ints."""
    d = m.get(base + "_dollars")
    if d not in (None, ""):
        try:
            return round(float(d) * 100)
        except (TypeError, ValueError):
            pass
    v = m.get(base)
    if isinstance(v, (int, float)):
        return int(v)
    return None


def num(m, *keys):
    for kk in keys:
        v = m.get(kk)
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def implied(c):
    return None if c in (None, 0) else round(c / 100.0, 4)


def fee_estimate(price_cents, contracts=1):
    if not price_cents:
        return None
    p = price_cents / 100.0
    return math.ceil(0.07 * contracts * p * (1 - p) * 100) / 100


def classify(market, stype, team_a, team_b):
    blob = " ".join(str(market.get(f, "")) for f in
                    ("title", "subtitle", "yes_sub_title", "no_sub_title")).lower()
    rp = market.get("rules_primary") or ""
    n = re.search(r"(\d+(?:\.\d+)?)", blob)
    line = float(n.group(1)) if n else None

    if stype == "moneyline":
        if TIE_RE.search(rp) or TIE_RE.search(blob):
            return {"market_type": "moneyline", "side": "draw", "line": None}
        mw = IFWIN_RE.search(rp)
        name = (mw.group(1) if mw else blob).lower()
        if team_a and team_a.lower() in name:
            side = "team_a"
        elif team_b and team_b.lower() in name:
            side = "team_b"
        else:
            side = None
        return {"market_type": "moneyline", "side": side, "line": None}
    if stype == "total":
        side = "over" if re.search(r"\bover\b|or more|at least", blob + " " + rp.lower()) else \
               ("under" if re.search(r"\bunder\b|or fewer|less than", blob + " " + rp.lower()) else None)
        return {"market_type": "total", "side": side, "line": line}
    if stype == "spread":
        name = (rp + " " + blob).lower()
        if team_a and team_a.lower() in name:
            side = "team_a"
        elif team_b and team_b.lower() in name:
            side = "team_b"
        else:
            side = None
        return {"market_type": "spread", "side": side, "line": line}
    if stype == "btts":
        side = "no" if re.search(r"\bno\b|not", blob) and "yes" not in blob else "yes"
        return {"market_type": "btts", "side": side, "line": None}
    return {"market_type": "other", "side": None, "line": line}


# ----------------------------------------------------------------------------- build
def collect(k, series, days, want_orderbook, all_markets, include_live, debug):
    try:
        from zoneinfo import ZoneInfo
        today_et = datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        today_et = (datetime.now(timezone.utc) - timedelta(hours=4)).date()
    win_end = today_et + timedelta(days=int(round(days)))
    keep = None if all_markets else MODEL_TYPES
    records, meta = [], {}
    funnel = defaultdict(lambda: defaultdict(int))

    for st in series:
        stype = series_type(st)
        try:
            events = list(k.paginate("/events", {"series_ticker": st, "status": "open",
                                                 "with_nested_markets": "true"}, "events"))
        except RuntimeError as e:
            print(f"[warn] {st}: {e}")
            continue
        f = funnel[st]
        f["events"] = len(events)
        for ev in events:
            et = ev.get("event_ticker") or ev.get("ticker") or ""
            key, date_tok, ca, cb = parse_event_key(et)
            if not key:
                continue
            f["key_ok"] += 1
            md = date_from_token(date_tok)
            mkts = ev.get("markets", []) or []
            f["markets_raw"] += len(mkts)

            if md:
                if md > win_end:
                    f["dropped_future"] += len(mkts)
                    continue
                if md < today_et and not include_live:
                    f["dropped_past"] += len(mkts)
                    continue

            a, b = parse_teams(ev.get("title") or ev.get("sub_title") or "")
            if not (a and b):
                a, b = a or ca, b or cb
            m_ = meta.setdefault(key, {"team_a": a, "team_b": b, "match_date": md})
            for fld, val in (("team_a", a), ("team_b", b)):
                if val and not m_[fld]:
                    m_[fld] = val

            for m in mkts:
                if (m.get("status") or "").lower() in DEAD_STATUS:
                    continue
                f["after_status"] += 1
                cls = classify(m, stype, m_["team_a"], m_["team_b"])
                if keep and cls["market_type"] not in keep:
                    continue
                f["after_type"] += 1
                ya, yb = price_c(m, "yes_ask"), price_c(m, "yes_bid")
                na, nb = price_c(m, "no_ask"), price_c(m, "no_bid")
                row = {
                    "fixture_key": key, "series_ticker": st, "event_ticker": et,
                    "fixture": f"{m_['team_a']} vs {m_['team_b']}",
                    "team_a": m_["team_a"], "team_b": m_["team_b"],
                    "match_date": md.isoformat() if md else None,
                    "market_ticker": m.get("ticker"), "market_type": cls["market_type"],
                    "side": cls["side"], "line": cls["line"],
                    "title": m.get("title"),
                    "subtitle": m.get("subtitle") or m.get("yes_sub_title"),
                    "yes_bid_c": yb, "yes_ask_c": ya, "no_bid_c": nb, "no_ask_c": na,
                    "last_c": price_c(m, "last_price"),
                    "implied_yes": implied(ya), "implied_no": implied(na),
                    "yes_fee_est_$": fee_estimate(ya),
                    "volume": num(m, "volume_fp", "volume"),
                    "volume_24h": num(m, "volume_24h_fp", "volume_24h"),
                    "open_interest": num(m, "open_interest_fp", "open_interest"),
                    "liquidity_$": num(m, "liquidity_dollars"),
                    "status": m.get("status"),
                    "expected_expiration_utc": ts(m.get("expected_expiration_time")),
                }
                if want_orderbook and cls["market_type"] == "moneyline":
                    try:
                        ob = k.get(f"/markets/{m.get('ticker')}/orderbook").get("orderbook", {})
                        row["orderbook"] = {"yes": ob.get("yes"), "no": ob.get("no")}
                        time.sleep(SLEEP_BETWEEN)
                    except RuntimeError:
                        row["orderbook"] = None
                records.append(row)
                f["records"] += 1

    if debug or not records:
        print("\n[funnel] events → key_ok → markets_raw → after_status → after_type → records:")
        for st in series:
            f = funnel[st]
            print(f"   {st:<14} ev={f['events']:>3} key={f['key_ok']:>3} "
                  f"mk_raw={f['markets_raw']:>4} status={f['after_status']:>4} "
                  f"type={f['after_type']:>4} rec={f['records']:>4} "
                  f"(future={f['dropped_future']}, past={f['dropped_past']})")

    records.sort(key=lambda r: (r["match_date"] or "", r["fixture"],
                                r["market_type"], str(r["side"])))
    return records


# ----------------------------------------------------------------------------- output
def fmt_date(iso_d):
    if not iso_d:
        return "  ?  "
    try:
        return date.fromisoformat(iso_d).strftime("%a %b %d")
    except ValueError:
        return iso_d


def print_board(records):
    if not records:
        print("\n(no full-match markets in window)\n")
        return
    by_fix = defaultdict(list)
    for r in records:
        by_fix[r["fixture"]].append(r)
    print(f"\n{'='*78}\n  WC MATCH MARKETS — {len(by_fix)} fixtures, {len(records)} markets\n{'='*78}")
    for fix, rows in by_fix.items():
        print(f"\n▶ {fix}    [{fmt_date(rows[0]['match_date'])}]")
        for typ in ("moneyline", "total", "spread", "btts"):
            grp = [r for r in rows if r["market_type"] == typ]
            if not grp:
                continue
            print(f"    {typ}:")
            for r in grp:
                if typ == "moneyline":
                    sd = {"team_a": r["team_a"], "team_b": r["team_b"],
                          "draw": "Draw"}.get(r["side"], r["side"] or "?")
                else:
                    sd = (r["subtitle"] or r["title"] or f"{r['side']} {r['line']}")[:30]
                yp = f"{r['yes_ask_c']}c" if r["yes_ask_c"] is not None else "  -"
                print(f"        {str(sd):<26} yes ask {yp:>5}  (impl {r['implied_yes']})  vol {r['volume']}")


def write_outputs(records, outdir):
    os.makedirs(outdir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    jpath = os.path.join(outdir, f"match_markets_{stamp}.json")
    cpath = os.path.join(outdir, f"match_markets_{stamp}.csv")
    latest = os.path.join(outdir, "latest_match_markets.json")
    payload = {"generated_utc": datetime.now(timezone.utc).isoformat(),
               "n_markets": len(records), "records": records}
    for p in (jpath, latest):
        with open(p, "w") as fh:
            json.dump(payload, fh, indent=2)
    if records:
        cols = [c for c in records[0].keys() if c != "orderbook"]
        with open(cpath, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(records)
        print(f"\n[out] {jpath}\n[out] {cpath}\n[out] {latest}")
    else:
        print(f"\n[out] {jpath} (empty)\n[out] {latest} (empty)")


def raw_dump(k, series):
    for st in series:
        try:
            data = k.get("/events", {"series_ticker": st, "status": "open",
                                     "with_nested_markets": "true", "limit": 1})
            evs = data.get("events") or []
            if not evs:
                continue
            ev = evs[0]
            print(f"\n[raw-dump] one event from {st}:")
            print(f"   event keys: {sorted(ev.keys())}")
            mk = ev.get("markets") or []
            if mk:
                print(f"   market[0] keys: {sorted(mk[0].keys())}")
            print(json.dumps(ev, indent=2)[:2500])
            return
        except RuntimeError as e:
            print(f"[raw-dump] {st}: {e}")


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Discover Kalshi WC full-match markets.")
    ap.add_argument("--series", nargs="+", help="explicit series tickers; skips discovery")
    ap.add_argument("--discover", action="store_true", help="scan full KXWC* inventory")
    ap.add_argument("--days", type=float, default=2.0, help="match-date window in days (default 2)")
    ap.add_argument("--orderbook", action="store_true", help="fetch depth for moneylines")
    ap.add_argument("--all-markets", action="store_true", help="keep non-core market types")
    ap.add_argument("--include-live", action="store_true", help="keep past-dated fixtures still open")
    ap.add_argument("--debug", action="store_true", help="always print the funnel")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "data"))
    args = ap.parse_args()

    k = Kalshi()
    if args.series:
        series = args.series
        print(f"[series] override: {series}")
    elif args.discover:
        series = discover_all_kxwc(k)
        print(f"[series] full KXWC* scan -> {series}")
    else:
        print("[series] probing curated full-match core ...")
        series = probe_core(k)
        print(f"[series] using: {series}")

    if not series:
        print("\n!! No series with open events. Try --discover or --series KXWCGAME.")
        sys.exit(2)

    records = collect(k, series, args.days, args.orderbook,
                      args.all_markets, args.include_live, args.debug)
    print_board(records)
    write_outputs(records, os.path.abspath(args.out))
    if not records:
        raw_dump(k, series)

    nfix = len({r["fixture_key"] for r in records})
    ml = sum(1 for r in records if r["market_type"] == "moneyline")
    print(f"\n[summary] {nfix} fixtures, {ml} moneyline legs, {len(records)} markets.")


if __name__ == "__main__":
    main()