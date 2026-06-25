"""
22_kalshi_discover.py  (Stage 2, Step 1)

Discover the live Kalshi World Cup contract universe using only PUBLIC market-data
endpoints (no authentication, no credentials, no money). Output is the inventory
Step 2 maps against fair_values_2026.parquet.

Kalshi public API (per docs.kalshi.com): base https://external-api.kalshi.com/trade-api/v2
  GET /series/{ticker}                          series metadata
  GET /markets?series_ticker=...&status=open    markets in a series
  GET /events?status=open&limit=...&cursor=...   paginated events (for broad scan)
  GET /markets?event_ticker=...                  markets in an event
No auth headers required for any of the above.

Two discovery modes (run both; they're complementary):
  - SERIES probe: query known/likely WC series tickers directly (fast, exact).
  - EVENT scan: page open events, keep those whose title mentions 'world cup'
    (catches contract types whose series ticker we don't know yet).

Outputs
-------
  - data/processed/kalshi_wc_contracts.parquet / .csv
  - console summary (counts, top markets by volume)

Run
---
  uv run python scripts/22_kalshi_discover.py
  uv run python scripts/22_kalshi_discover.py --no-event-scan   # series probe only (faster)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

try:
    import requests
except ImportError:
    print("[FATAL] 'requests' not installed. Run: uv add requests")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_PARQUET = REPO_ROOT / "data" / "processed" / "kalshi_wc_contracts.parquet"
OUT_CSV = REPO_ROOT / "data" / "processed" / "kalshi_wc_contracts.csv"

# Primary host: the live Kalshi API host, same one paper_trading/scripts/
# 01_discover_match_markets.py connects to successfully. The older
# external-api/api.kalshi.com hostnames no longer resolve (DNS NameResolutionError),
# which is why this step used to FAIL every morning. Kept as fallbacks just in case.
BASE = "https://api.elections.kalshi.com/trade-api/v2"
# Fallbacks if the above is unreachable on your network:
BASE_ALT = "https://external-api.kalshi.com/trade-api/v2"

# Known/likely World Cup series tickers. KXMENWORLDCUP (winner) is confirmed live;
# the others are educated guesses -- the script reports which actually resolve, and
# the event scan catches anything missed.
CANDIDATE_SERIES = [
    "KXMENWORLDCUP",            # tournament winner (confirmed)
    "KXMENWORLDCUPGROUP",       # group winners (guess)
    "KXWORLDCUPGROUP",          # group winners (guess)
    "KXMENWORLDCUPADVANCE",     # advancement (guess)
    "KXWORLDCUPGOLDENBOOT",     # golden boot (guess)
    "KXMENWORLDCUPGOLDENBOOT",  # golden boot (guess)
]
TITLE_KEYWORDS = ["world cup"]   # event-scan filter (case-insensitive)
REQUEST_PAUSE = 0.25             # be polite to the rate limiter
EVENT_PAGE_LIMIT = 200
MAX_EVENT_PAGES = 25             # safety cap on the broad scan


def _get(session, base, path, params=None):
    r = session.get(f"{base}{path}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def _market_row(m: dict) -> dict:
    """Defensive field extraction (Kalshi returns cents and *_dollars variants)."""
    def dollars(key_dollars, key_cents):
        if m.get(key_dollars) is not None:
            return float(m[key_dollars])
        if m.get(key_cents) is not None:
            return float(m[key_cents]) / 100.0
        return None

    yes_bid = dollars("yes_bid_dollars", "yes_bid")
    yes_ask = dollars("yes_ask_dollars", "yes_ask")
    mid = None
    if yes_bid is not None and yes_ask is not None:
        mid = round((yes_bid + yes_ask) / 2, 4)
    return {
        "series_ticker": m.get("series_ticker"),
        "event_ticker": m.get("event_ticker"),
        "market_ticker": m.get("ticker"),
        "title": m.get("title") or m.get("yes_sub_title") or m.get("subtitle"),
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "mid": mid,
        "last_price": dollars("last_price_dollars", "last_price"),
        "volume": m.get("volume_fp") or m.get("volume"),
        "open_interest": m.get("open_interest_fp") or m.get("open_interest"),
        "status": m.get("status"),
    }


def probe_series(session, base) -> list[dict]:
    rows = []
    for st in CANDIDATE_SERIES:
        try:
            data = _get(session, base, f"/markets", {"series_ticker": st, "status": "open"})
        except requests.HTTPError as e:
            print(f"  [series] {st:<28} -> not found / no open markets ({e.response.status_code})")
            continue
        except requests.RequestException as e:
            print(f"  [series] {st:<28} -> request error: {e}")
            continue
        mkts = data.get("markets", [])
        if mkts:
            print(f"  [series] {st:<28} -> {len(mkts)} open markets")
            for m in mkts:
                row = _market_row(m)
                row["series_ticker"] = row["series_ticker"] or st
                rows.extend([row])
        else:
            print(f"  [series] {st:<28} -> resolved but 0 open markets")
        time.sleep(REQUEST_PAUSE)
    return rows


def scan_events(session, base) -> list[dict]:
    rows, cursor, pages = [], None, 0
    seen_events = set()
    while pages < MAX_EVENT_PAGES:
        params = {"status": "open", "limit": EVENT_PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor
        try:
            data = _get(session, base, "/events", params)
        except requests.RequestException as e:
            print(f"  [events] stopped: {e}")
            break
        events = data.get("events", [])
        for ev in events:
            title = (ev.get("title") or "").lower()
            if any(k in title for k in TITLE_KEYWORDS):
                et = ev.get("event_ticker")
                if et and et not in seen_events:
                    seen_events.add(et)
                    try:
                        md = _get(session, base, "/markets", {"event_ticker": et, "status": "open"})
                        rows.extend(_market_row(m) for m in md.get("markets", []))
                        print(f"  [events] {et:<34} '{ev.get('title')}' -> "
                              f"{len(md.get('markets', []))} markets")
                    except requests.RequestException as e:
                        print(f"  [events] {et}: market fetch failed ({e})")
                    time.sleep(REQUEST_PAUSE)
        cursor = data.get("cursor")
        pages += 1
        if not cursor or not events:
            break
        time.sleep(REQUEST_PAUSE)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-event-scan", action="store_true",
                    help="skip the broad event scan (series probe only)")
    args = ap.parse_args()

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    base = BASE
    # connectivity check with a known public series; fall back if needed
    try:
        _get(session, base, "/series/KXMENWORLDCUP")
        print(f"[ok] connected to {base}")
    except requests.RequestException:
        print(f"[warn] {base} unreachable, trying {BASE_ALT}")
        base = BASE_ALT
        try:
            _get(session, base, "/series/KXMENWORLDCUP")
            print(f"[ok] connected to {base}")
        except requests.RequestException as e:
            print(f"[FATAL] could not reach Kalshi public API: {e}")
            sys.exit(1)

    print("\n=== Series probe ===")
    rows = probe_series(session, base)

    if not args.no_event_scan:
        print("\n=== Event scan (broad, title contains 'world cup') ===")
        rows.extend(scan_events(session, base))

    if not rows:
        print("\n[done] no World Cup markets discovered. The tournament series may have "
              "rolled to a different ticker -- check kalshi.com/markets/kxmenworldcup.")
        return

    df = pd.DataFrame(rows).drop_duplicates(subset=["market_ticker"]).reset_index(drop=True)
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    df.to_csv(OUT_CSV, index=False)

    print(f"\n=== Discovered {len(df)} unique WC contracts ===")
    by_series = df.groupby("series_ticker", dropna=False)["market_ticker"].count().sort_values(ascending=False)
    print("\n  By series:")
    for st, n in by_series.items():
        print(f"    {str(st):<30} {n}")

    top = df.sort_values("volume", ascending=False, na_position="last").head(15)
    print("\n  Top 15 by volume:")
    print(f"  {'market_ticker':<34}{'title':<24}{'mid':>7}{'vol':>10}")
    for _, r in top.iterrows():
        title = (str(r["title"]) or "")[:22]
        mid = f"{r['mid']:.3f}" if pd.notna(r["mid"]) else "  -  "
        vol = f"{float(r['volume']):,.0f}" if pd.notna(r["volume"]) else "-"
        print(f"  {str(r['market_ticker']):<34}{title:<24}{mid:>7}{vol:>10}")

    print(f"\n[save] {OUT_PARQUET}")
    print(f"[save] {OUT_CSV}")
    print("\nNext (Step 2): crosswalk these market_tickers/titles to fair_values_2026.parquet.")


if __name__ == "__main__":
    main()