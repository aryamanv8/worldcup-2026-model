#!/usr/bin/env python3
"""
34_market_inventory.py  —  Unified Kalshi World Cup market inventory  (F2)

WHY THIS EXISTS
    The two older discoverers each saw only a slice of the board:
      * scripts/22_kalshi_discover.py      -> probed a GUESSED series list (DEPRECATED).
      * paper_trading/01_discover_*.py     -> enumerated the catalog but then dropped
        everything that isn't a model-priceable per-match type.
    Neither could answer "are we seeing ALL the markets?".

    This is the single source of truth for the live Kalshi WC universe. It discovers
    exhaustively, then classifies every series by a HAND-VERIFIED map
    (data/reference/wc_market_map.csv) into a priceability tier:
        A = priced now            B = priceable, clean fit, NOT yet priced (edge candidate)
        C = priceable w/ extra modeling   D = out of scope (no model surface)
        X = exclude (not men's soccer WC, e.g. cricket)
    Anything discovered but NOT in the map is flagged 'UNKNOWN — review' so a new
    market family can never be silently misclassified again.

    READ-ONLY. Public market-data endpoints only. No auth, no credentials, no orders.

DISCOVERY  = union of three passes:
    (A) /series catalog, paged across sport categories -> WC-pattern tickers.
    (B) /events open scan -> title ~ 'world cup' -> harvest series_tickers.
    (C) explicit known-good seeds.
    Then page ALL markets per series (status open + unopened), unfiltered.

OUTPUTS
    data/processed/kalshi_full_inventory.parquet / .csv   (every market, tagged w/ tier)
    reports/market_inventory.md                           (coverage summary — SEND BACK)
    console COVERAGE block (loudly lists any UNKNOWN series)

RUN (on the Mac, has internet + uv)
    uv run python scripts/34_market_inventory.py
    uv run python scripts/34_market_inventory.py --status open   # open only (faster)

Deps: requests, pandas.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Need `requests`:  uv add requests")

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
MAP_CSV = REPO_ROOT / "data" / "reference" / "wc_market_map.csv"
OUT_PARQUET = REPO_ROOT / "data" / "processed" / "kalshi_full_inventory.parquet"
OUT_CSV = REPO_ROOT / "data" / "processed" / "kalshi_full_inventory.csv"
OUT_MD = REPO_ROOT / "reports" / "market_inventory.md"

BASE_CANDIDATES = [
    "https://api.elections.kalshi.com/trade-api/v2",
    "https://api.kalshi.com/trade-api/v2",
    "https://external-api.kalshi.com/trade-api/v2",
]
SERIES_CATEGORIES = [{"category": "Sports"}, {"category": "Soccer"}, {}]
WC_TICKER_RE = re.compile(r"WORLDCUP|^KXWC", re.I)
WC_TITLE_RE = re.compile(r"world\s*cup", re.I)
SEED_SERIES = ["KXMENWORLDCUP", "KXWCGAME", "KXWCSPREAD", "KXWCTOTAL", "KXWCBTTS"]
STATUSES_DEFAULT = ["open", "unopened"]
PAGE_LIMIT = 200
MAX_EVENT_PAGES = 40
SLEEP = 0.15

TIER_LABEL = {
    "A": "priced now",
    "B": "priceable — clean fit, uncovered (EDGE CANDIDATE)",
    "C": "priceable — needs extra modeling",
    "D": "out of scope (no model surface)",
    "X": "excluded — not men's soccer WC",
    "UNKNOWN": "UNKNOWN — REVIEW (new series, not in map)",
}


def load_map() -> dict[str, dict]:
    if not MAP_CSV.exists():
        sys.exit(f"[FATAL] market map not found: {MAP_CSV}\n"
                 f"        This script classifies by the hand-verified map; build it first.")
    m = pd.read_csv(MAP_CSV).fillna("")
    return {str(r["series_ticker"]).upper(): r.to_dict() for _, r in m.iterrows()}


def classify(series_ticker: str, mp: dict[str, dict]) -> dict:
    row = mp.get((series_ticker or "").upper())
    if row is None:
        return {"tier": "UNKNOWN", "engine": "", "family": "unknown_review",
                "model_output": "", "priced_by": "", "notes": "NOT IN MAP — review + add"}
    return {"tier": row.get("tier", "UNKNOWN"), "engine": row.get("engine", ""),
            "family": row.get("family", ""), "model_output": row.get("model_output", ""),
            "priced_by": row.get("current_pricer", ""), "notes": row.get("notes", "")}


class Kalshi:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/json", "User-Agent": "wc2026-inventory/1.1"})
        self.base = self._pick_base()

    def _pick_base(self) -> str:
        for b in BASE_CANDIDATES:
            try:
                if self.s.get(f"{b}/exchange/status", timeout=20).status_code == 200:
                    print(f"[base] {b}")
                    return b
            except requests.RequestException:
                continue
        print(f"[base] status probe failed; defaulting to {BASE_CANDIDATES[0]} "
              f"(if this run dies on DNS, flush cache: "
              f"sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder)")
        return BASE_CANDIDATES[0]

    def get(self, path, params=None):
        url = f"{self.base}{path}"
        for attempt in range(4):
            r = self.s.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 502, 503, 504):
                time.sleep(0.5 * (attempt + 1))
                continue
            raise RuntimeError(f"GET {path} -> {r.status_code}: {r.text[:200]}")
        raise RuntimeError(f"GET {path} kept failing.")

    def paginate(self, path, params, key):
        params = dict(params)
        params.setdefault("limit", PAGE_LIMIT)
        cursor, pages = None, 0
        while pages < MAX_EVENT_PAGES:
            if cursor:
                params["cursor"] = cursor
            data = self.get(path, params)
            for item in data.get(key, []) or []:
                yield item
            cursor = data.get("cursor")
            pages += 1
            if not cursor:
                break
            time.sleep(SLEEP)


def discover_series(k: Kalshi) -> dict[str, str]:
    found: dict[str, str] = {}
    catalog = []
    for params in SERIES_CATEGORIES:
        try:
            catalog = list(k.paginate("/series", params, "series"))
            if catalog:
                print(f"[catalog] {len(catalog)} series via {params or 'full scan'}")
                break
        except RuntimeError as e:
            print(f"[catalog] {params} failed: {e}")
    for s in catalog:
        tk = (s.get("ticker") or "").upper()
        if WC_TICKER_RE.search(tk):
            found.setdefault(tk, "catalog")
    try:
        n_ev = 0
        for ev in k.paginate("/events", {"status": "open"}, "events"):
            n_ev += 1
            if WC_TITLE_RE.search(ev.get("title") or ""):
                st = (ev.get("series_ticker") or "").upper()
                if st:
                    found.setdefault(st, "event_scan")
        print(f"[events] scanned {n_ev} open events")
    except RuntimeError as e:
        print(f"[events] scan stopped: {e}")
    for st in SEED_SERIES:
        found.setdefault(st.upper(), "seed")
    print(f"[series] {len(found)} WC-pattern series discovered")
    return found


def _price_dollars(m: dict, base: str):
    d = m.get(base + "_dollars")
    if d not in (None, ""):
        try:
            return round(float(d), 4)
        except (TypeError, ValueError):
            pass
    v = m.get(base)
    if isinstance(v, (int, float)):
        return round(v / 100.0, 4)
    return None


def collect_markets(k: Kalshi, series_map: dict[str, str], statuses: list[str], mp: dict) -> list[dict]:
    rows = []
    for st, how in sorted(series_map.items()):
        cls = classify(st, mp)
        got = 0
        for status in statuses:
            try:
                for m in k.paginate("/markets", {"series_ticker": st, "status": status}, "markets"):
                    title = m.get("title") or m.get("yes_sub_title") or m.get("subtitle")
                    sub = m.get("subtitle") or m.get("yes_sub_title")
                    yb, ya = _price_dollars(m, "yes_bid"), _price_dollars(m, "yes_ask")
                    rows.append({
                        "series_ticker": st, "discovered_via": how,
                        "tier": cls["tier"], "engine": cls["engine"], "family": cls["family"],
                        "model_output": cls["model_output"], "priced_by": cls["priced_by"],
                        "map_notes": cls["notes"],
                        "event_ticker": m.get("event_ticker"), "market_ticker": m.get("ticker"),
                        "title": title, "subtitle": sub, "market_status": m.get("status"),
                        "yes_bid": yb, "yes_ask": ya,
                        "mid": round((yb + ya) / 2, 4) if (yb is not None and ya is not None) else None,
                        "last_price": _price_dollars(m, "last_price"),
                        "volume": m.get("volume_fp") or m.get("volume"),
                        "open_interest": m.get("open_interest_fp") or m.get("open_interest"),
                        "liquidity_$": m.get("liquidity_dollars"),
                    })
                    got += 1
            except RuntimeError as e:
                print(f"  [{st}] status={status} error: {e}")
        flag = "  <-- UNKNOWN, REVIEW" if cls["tier"] == "UNKNOWN" else ""
        print(f"  [{st:<24}] {got:>4} markets  tier={cls['tier']:<7}{flag}")
    return rows


def write_report(df: pd.DataFrame) -> str:
    L = []
    L.append(f"# Kalshi WC market inventory — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
    L.append("")
    unknown = df[df["tier"] == "UNKNOWN"]
    if len(unknown):
        L.append(f"> ⚠️ **{unknown['series_ticker'].nunique()} UNMAPPED series "
                 f"({len(unknown)} markets)** — add to wc_market_map.csv: "
                 + ", ".join(f"`{s}`" for s in sorted(unknown['series_ticker'].unique())))
        L.append("")
    scoped = df[~df["tier"].isin(["X", "UNKNOWN"])]
    L.append(f"**{len(df)} markets / {df['series_ticker'].nunique()} series discovered**; "
             f"**{len(scoped)} markets / {scoped['series_ticker'].nunique()} series** are "
             f"men's-soccer-WC in scope (tiers A–D).")
    L.append("")

    L.append("## By tier")
    L.append("")
    L.append("| tier | meaning | series | markets |")
    L.append("|---|---|---:|---:|")
    for t in ["A", "B", "C", "D", "X", "UNKNOWN"]:
        sub = df[df["tier"] == t]
        if len(sub):
            L.append(f"| {t} | {TIER_LABEL[t]} | {sub['series_ticker'].nunique()} | {len(sub)} |")
    L.append("")

    for t, head in [("B", "Tier B — edge candidates (priceable now, not yet covered)"),
                    ("C", "Tier C — priceable with extra modeling")]:
        sub = df[df["tier"] == t]
        if not len(sub):
            continue
        L.append(f"## {head}")
        L.append("")
        L.append("| series | engine | model output | ~volume | example |")
        L.append("|---|---|---|---:|---|")
        for st, g in sub.groupby("series_ticker"):
            vol = pd.to_numeric(g["volume"], errors="coerce").fillna(0).sum()
            L.append(f"| `{st}` | {g['engine'].iloc[0]} | {g['model_output'].iloc[0]} | "
                     f"{vol:,.0f} | {str(g['title'].iloc[0])[:44]} |")
        L.append("")

    L.append("## Tier A — priced now")
    L.append("")
    for st, g in df[df["tier"] == "A"].groupby("series_ticker"):
        L.append(f"- `{st}` — {g['priced_by'].iloc[0]}")
    L.append("")

    md = "\n".join(L)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md)
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", nargs="+", default=STATUSES_DEFAULT)
    args = ap.parse_args()

    mp = load_map()
    print(f"[map] {len(mp)} series in wc_market_map.csv")

    k = Kalshi()
    print("\n=== Discovering WC series ===")
    series_map = discover_series(k)

    print("\n=== Enumerating markets (unfiltered; tagged by map) ===")
    rows = collect_markets(k, series_map, args.status, mp)
    if not rows:
        print("\n[done] no markets found. Check kalshi.com/markets/kxmenworldcup.")
        return

    df = pd.DataFrame(rows).drop_duplicates(subset=["market_ticker"]).reset_index(drop=True)
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    df.to_csv(OUT_CSV, index=False)
    md = write_report(df)

    print("\n" + "=" * 70 + "\nCOVERAGE\n" + "=" * 70)
    print(md)
    print("=" * 70)
    unknown = df[df["tier"] == "UNKNOWN"]["series_ticker"].nunique()
    if unknown:
        print(f"[!] {unknown} UNMAPPED series — add them to {MAP_CSV.name} and re-run.")
    print(f"[save] {OUT_PARQUET}")
    print(f"[save] {OUT_CSV}")
    print(f"[save] {OUT_MD}   <-- send this file back to Claude")


if __name__ == "__main__":
    main()
