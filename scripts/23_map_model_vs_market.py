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

Inputs : data/processed/kalshi_wc_contracts.parquet   (script 22, full scan)
         data/processed/tournament_probs_live.parquet (script 32, LIVE bracket sim)
         data/processed/team_features.parquet          (static team-name universe)
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
# MODEL side = the LIVE bracket-rollforward sim (script 32), NOT the frozen Jun-11
# fair_values_2026. That old source went stale after eliminations and fed the advance
# pricer fake edges (F1 in docs/architecture_audit.md). team_features is used ONLY as a
# static team-name universe for normalizing Kalshi titles — never as a prob source.
LIVE_SIM = REPO_ROOT / "data" / "processed" / "tournament_probs_live.parquet"
TEAM_FEATURES = REPO_ROOT / "data" / "processed" / "team_features.parquet"
OUT = REPO_ROOT / "data" / "processed" / "model_vs_market.parquet"
# live-sim wide columns -> model contract names
LIVE_COL = {"reach_round_of_16": "reach_R16", "reach_quarter_final": "reach_QF",
            "reach_semi_final": "reach_SF", "reach_final": "reach_F", "champion": "champion"}

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
    for p in (KALSHI, LIVE_SIM, TEAM_FEATURES):
        if not p.exists():
            print(f"[FATAL] missing {p}  (run script 32 first for the live sim)")
            sys.exit(1)

    market = pd.read_parquet(KALSHI)
    market["volume"] = pd.to_numeric(market["volume"], errors="coerce").fillna(0)

    # MODEL side: melt the LIVE knockout sim (wide: team, reach_R16, ...) into long
    # (team, contract, fair_value). Eliminated teams are simply absent -> dropped by the
    # inner join below, so a knocked-out team can never manufacture a fake edge.
    live = pd.read_parquet(LIVE_SIM)
    recs = []
    for _, lr in live.iterrows():
        for contract, col in LIVE_COL.items():
            if col in live.columns:
                recs.append({"team": lr["team"], "contract": contract,
                             "fair_value": float(lr[col])})
    fair = pd.DataFrame(recs)
    # team-name universe for normalizing Kalshi titles: the static 48-team features file
    # (never stale for names), NOT the model-probability source.
    model_teams = pd.read_parquet(TEAM_FEATURES)["team"].unique().tolist()
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
    # Each "reach round R" contract is an independent binary market whose YES mid is
    # already ~the implied probability. Summed over all teams the fair probs equal R
    # (exactly R teams reach round R), so a genuine OVERROUND (raw_sum > slots) is
    # scaled DOWN to remove it. But we must NEVER scale UP: when coverage is partial
    # (not all teams mapped, so raw_sum < slots) the old `mid*slots/raw_sum` inflated
    # every price — pushing strong teams above 100% (e.g. Argentina reach-R16 -> 1.14),
    # which is an impossible probability and poisons the correction layer downstream.
    # Fix: factor = min(1, slots/raw_sum) (down-scale overround only), then hard-clip
    # to [0, 1). Coverage n is printed so partial-mapping is auditable.
    rows = []
    print("\n=== De-vig audit (down-scale overround only; never inflate) ===")
    for (contract, slots), grp in market.groupby(["contract", "slots"]):
        raw_sum = grp["mid"].sum()
        factor = min(1.0, slots / raw_sum) if raw_sum > 0 else 1.0
        scaled = grp.copy()
        scaled["market_devig"] = (scaled["mid"] * factor).clip(0.0, 0.999)
        scaled["market_raw"] = scaled["mid"]
        rows.append(scaled)
        note = "" if factor < 1.0 else "  [no down-scale: raw_sum<=slots, partial coverage]"
        print(f"  {contract:<22} n={len(grp):>2}  raw_sum={raw_sum:6.3f}  "
              f"slots={int(slots):>2}  factor={factor:.3f}  "
              f"max_devig={scaled['market_devig'].max():.3f}{note}")
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