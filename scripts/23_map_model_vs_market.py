"""
23_map_model_vs_market.py  (Stage 2, Step 2 - extended to all rounds)

Crosswalk live Kalshi contracts to the model's fair values, de-vig per round, and
join into one model-vs-market table spanning champion + the four "reach round"
markets.

Kalshi contracts mapped (by market_ticker prefix; series_ticker is unreliable
from the event scan):
  KXMENWORLDCUP-26-   -> champion            (1 slot,  de-vig sum -> 1)
  KXWCROUND-26RO16-   -> reach_round_of_16   (16 slots, de-vig sum -> 16)
  KXWCROUND-26QUAR-   -> reach_quarter_final (8 slots,  de-vig sum -> 8)
  KXWCROUND-26SEMI-   -> reach_semi_final    (4 slots,  de-vig sum -> 4)
  KXWCROUND-26FINAL-  -> reach_final         (2 slots,  de-vig sum -> 2)

De-vig: "reach round R" is a multi-winner market -- summed over all teams, the fair
probabilities equal R's slot count (exactly R teams reach round R). Observed mids
sum a bit higher (overround); we scale each round's mids so the sum hits the slot
count. The script PRINTS each round's raw sum so the slot assumption is auditable
(if RO16's raw sum is ~32 not ~16, it's actually an 'advance from group' market and
we remap).

Inputs : data/processed/kalshi_wc_contracts.parquet (script 22, full scan)
         data/processed/fair_values_2026.parquet     (script 21)
Output : data/processed/model_vs_market.parquet + console comparison per round

Run    : uv run python scripts/23_map_model_vs_market.py
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
KALSHI = REPO_ROOT / "data" / "processed" / "kalshi_wc_contracts.parquet"
FAIR = REPO_ROOT / "data" / "processed" / "fair_values_2026.parquet"
OUT = REPO_ROOT / "data" / "processed" / "model_vs_market.parquet"

# market_ticker prefix -> (model contract name, slot count)
PREFIX_MAP = {
    "KXMENWORLDCUP-26-": ("champion", 1),
    "KXWCROUND-26RO16-": ("reach_round_of_16", 16),
    "KXWCROUND-26QUAR-": ("reach_quarter_final", 8),
    "KXWCROUND-26SEMI-": ("reach_semi_final", 4),
    "KXWCROUND-26FINAL-": ("reach_final", 2),
}

# Kalshi name variants -> model team name (only structural mismatches need listing;
# accent differences are handled by strip_accents fallback).
NAME_ALIASES = {
    "Congo DR": "DR Congo", "DR Congo": "DR Congo",
    "Czechia": "Czech Republic",
    "USA": "United States",
    "IR Iran": "Iran",
    "Korea Republic": "South Korea",
    "Cabo Verde": "Cape Verde",
    "Cote d'Ivoire": "Ivory Coast", "Cote d`Ivoire": "Ivory Coast",
    "Turkiye": "Turkey",
}

TEAM_PATTERNS = [
    r"^Will (?:the )?(.+?) win the 2026 Men's World Cup",
    r"^Will (?:the )?(.+?) qualify for",
    r"^Will (?:the )?(.+?) (?:reach|advance)",
]


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def extract_raw_team(title: str) -> str | None:
    t = str(title).strip()
    for pat in TEAM_PATTERNS:
        m = re.match(pat, t)
        if m:
            return m.group(1).strip()
    return None


def main() -> None:
    for p in (KALSHI, FAIR):
        if not p.exists():
            print(f"[FATAL] missing {p}")
            sys.exit(1)

    market = pd.read_parquet(KALSHI)
    market["volume"] = pd.to_numeric(market["volume"], errors="coerce").fillna(0)
    fair = pd.read_parquet(FAIR)
    model_teams = fair["team"].unique().tolist()
    norm_lookup = {strip_accents(t).lower(): t for t in model_teams}

    def normalize_team(raw: str | None) -> str | None:
        if raw is None:
            return None
        if raw in NAME_ALIASES:
            return NAME_ALIASES[raw]
        key = strip_accents(raw).lower()
        return norm_lookup.get(key)

    # --- assign each Kalshi contract to a model contract via ticker prefix ----
    def assign(ticker: str):
        for pref, (contract, slots) in PREFIX_MAP.items():
            if str(ticker).startswith(pref):
                return contract, slots
        return None, None

    market[["contract", "slots"]] = market["market_ticker"].apply(
        lambda t: pd.Series(assign(t)))
    market = market.dropna(subset=["contract"]).copy()
    market["raw_team"] = market["title"].map(extract_raw_team)
    market["team"] = market["raw_team"].map(normalize_team)

    unmapped = market[market["team"].isna()][["contract", "raw_team", "title"]]
    if len(unmapped):
        print(f"[warn] {len(unmapped)} contracts with unmapped team names:")
        for _, r in unmapped.drop_duplicates("raw_team").iterrows():
            print(f"        [{r['contract']}] raw='{r['raw_team']}'  ({r['title'][:50]})")

    market = market.dropna(subset=["team", "mid"]).copy()

    # --- de-vig within each round to its slot count --------------------------
    rows = []
    print("\n=== De-vig audit (raw mid sum should be ~slot count + overround) ===")
    for (contract, slots), grp in market.groupby(["contract", "slots"]):
        raw_sum = grp["mid"].sum()
        scaled = grp.copy()
        scaled["market_devig"] = scaled["mid"] * slots / raw_sum
        scaled["market_raw"] = scaled["mid"]
        rows.append(scaled)
        print(f"  {contract:<22} n={len(grp):>2}  raw_sum={raw_sum:6.3f}  "
              f"slots={int(slots):>2}  overround={100*(raw_sum/slots - 1):+5.1f}%")
    market = pd.concat(rows, ignore_index=True)

    # --- join to model fair values on (team, contract) -----------------------
    j = fair.merge(
        market[["team", "contract", "market_ticker", "yes_bid", "yes_ask",
                "market_raw", "market_devig", "volume"]],
        on=["team", "contract"], how="inner",
    )
    j["edge"] = j["fair_value"] - j["market_devig"]
    j["edge_direction"] = np.where(j["edge"] > 0, "model HIGH", "model LOW")
    j = j.rename(columns={"fair_value": "model_fv"})

    cols = ["contract", "team", "market_ticker", "model_fv", "market_raw",
            "market_devig", "edge", "edge_direction", "yes_bid", "yes_ask", "volume"]
    out = j[cols].sort_values(["contract", "edge"], ascending=[True, False]).reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)

    # --- per-contract summary ------------------------------------------------
    contract_order = ["champion", "reach_final", "reach_semi_final",
                      "reach_quarter_final", "reach_round_of_16"]
    for c in contract_order:
        sub = out[out["contract"] == c]
        if sub.empty:
            continue
        mae = sub["edge"].abs().mean()
        print(f"\n=== {c}  ({len(sub)} teams mapped, mean |edge| = {mae:.3f}) ===")
        print("  biggest model-HIGH (model > market):")
        for _, r in sub.head(4).iterrows():
            print(f"    {r['team']:<20} model={r['model_fv']:.3f} mkt={r['market_devig']:.3f} "
                  f"edge={r['edge']:+.3f}  (bid {r['yes_bid']:.3f}/ask {r['yes_ask']:.3f}, vol {r['volume']:,.0f})")
        print("  biggest model-LOW (model < market):")
        for _, r in sub.tail(4).iloc[::-1].iterrows():
            print(f"    {r['team']:<20} model={r['model_fv']:.3f} mkt={r['market_devig']:.3f} "
                  f"edge={r['edge']:+.3f}  (bid {r['yes_bid']:.3f}/ask {r['yes_ask']:.3f}, vol {r['volume']:,.0f})")

    print(f"\n[save] {OUT}  ({len(out)} contract rows across {out['contract'].nunique()} markets)")


if __name__ == "__main__":
    main()