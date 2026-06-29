"""
24_scan_arbitrage.py  (Stage 2, Step 3 - model-free scanners)

Detect riskless arbitrage in the live Kalshi prices that does NOT depend on the
model being right -- the safest edges, immune to the model's compression bias.

Two checks on the data we have (raw bid/ask, NOT de-vigged -- arbitrage is about
real tradeable prices):

1. MONOTONICITY (nested rounds, same team).
   Events are strictly nested: champion => reach_final => reach_SF => reach_QF
   => reach_R16. So for any shallow contract S and deeper contract D (D implies S):
       P(D) <= P(S)   must hold.
   Executable lock when the DEEPER YES bid exceeds the SHALLOWER YES ask:
       buy S-YES at ask_S, buy D-NO at (1 - bid_D).
       Payoff is >= 1 in every outcome (proof below); cost = ask_S + 1 - bid_D.
       Profit/contract = bid_D - ask_S   (>0 == arbitrage).
   Outcome table for (long S-YES, long D-NO):
       D YES (=> S YES): S pays 1, D-NO pays 0  -> 1
       D NO,   S YES   : S pays 1, D-NO pays 1  -> 2
       D NO,   S NO    : S pays 0, D-NO pays 1  -> 1
   We also report SOFT violations (deeper mid > shallower mid) which signal
   mispricing even when the spread eats the executable edge.

2. WITHIN-ROUND DUTCH BOOK.
   Exactly `slots` teams reach round R, so a fair book has sum_i P_i = slots.
   - Buy-all-YES: cost = sum(ask), payoff = slots. Arb if sum(ask) < slots.
   - Buy-all-NO : cost = N - sum(bid), payoff = N - slots. Arb if sum(bid) > slots.

NOTE: all profits here are GROSS (pre-fee). Step 4 applies Kalshi's fee schedule;
many razor-thin "arbs" die there. Also this is a SNAPSHOT -- live arbs are fleeting
and need the live feed (dashboard) to act on. This script validates the logic.

Input  : data/processed/model_vs_market.parquet (script 23)
Output : data/processed/arb_flags.parquet + console report

Run    : uv run python scripts/24_scan_arbitrage.py
"""

from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
MVM = REPO_ROOT / "data" / "processed" / "model_vs_market.parquet"
OUT = REPO_ROOT / "data" / "processed" / "arb_flags.parquet"

# depth: larger = deeper round = lower probability
DEPTH = {
    "reach_round_of_16": 0,
    "reach_quarter_final": 1,
    "reach_semi_final": 2,
    "reach_final": 3,
    "champion": 4,
}
SLOTS = {"reach_round_of_16": 16, "reach_quarter_final": 8, "reach_semi_final": 4,
         "reach_final": 2, "champion": 1}
N_TEAMS = 48


def main() -> None:
    if not MVM.exists():
        print(f"[FATAL] missing {MVM} -- run script 23 first.")
        sys.exit(1)
    df = pd.read_parquet(MVM)
    for c in ("yes_bid", "yes_ask", "market_raw", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # ---- 1. MONOTONICITY ----------------------------------------------------
    hard, soft = [], []
    for team, g in df.groupby("team"):
        rec = {r["contract"]: r for _, r in g.iterrows()}
        for c1, c2 in combinations(rec, 2):
            # order so S = shallower (smaller depth), D = deeper
            (S, D) = (c1, c2) if DEPTH[c1] < DEPTH[c2] else (c2, c1)
            s, d = rec[S], rec[D]
            # executable lock: deeper YES bid > shallower YES ask
            if pd.notna(d["yes_bid"]) and pd.notna(s["yes_ask"]):
                profit = d["yes_bid"] - s["yes_ask"]
                if profit > 0:
                    hard.append({
                        "team": team, "shallow": S, "deep": D,
                        "buy_shallow_yes_ask": s["yes_ask"],
                        "sell_deep_yes_bid": d["yes_bid"],
                        "gross_profit_per_contract": round(profit, 4),
                        "min_volume": min(s.get("volume", 0) or 0, d.get("volume", 0) or 0),
                    })
            # soft mispricing: deeper mid > shallower mid
            if pd.notna(d["market_raw"]) and pd.notna(s["market_raw"]):
                gap = d["market_raw"] - s["market_raw"]
                if gap > 0:
                    soft.append({
                        "team": team, "shallow": S, "deep": D,
                        "shallow_mid": s["market_raw"], "deep_mid": d["market_raw"],
                        "mid_gap": round(gap, 4),
                    })

    print("=== 1. Monotonicity (nested rounds, same team) ===")
    if hard:
        hdf = pd.DataFrame(hard).sort_values("gross_profit_per_contract", ascending=False)
        print(f"  EXECUTABLE locks found: {len(hdf)} (gross, pre-fee)")
        print(f"  {'team':<18}{'shallow':<20}{'deep':<20}{'gross/ct':>9}{'minvol':>10}")
        for _, r in hdf.head(20).iterrows():
            print(f"  {r['team']:<18}{r['shallow']:<20}{r['deep']:<20}"
                  f"{r['gross_profit_per_contract']:>9.4f}{r['min_volume']:>10,.0f}")
    else:
        hdf = pd.DataFrame()
        print("  No executable monotonicity locks (deeper bid never exceeds shallower ask).")
        print("  -> the round books are internally consistent after spread.")

    if soft:
        sdf = pd.DataFrame(soft).sort_values("mid_gap", ascending=False)
        print(f"\n  Soft violations (deeper mid > shallower mid, not executable): {len(sdf)}")
        for _, r in sdf.head(8).iterrows():
            print(f"    {r['team']:<18}{r['deep']:<20} mid {r['deep_mid']:.3f} > "
                  f"{r['shallow']:<20} mid {r['shallow_mid']:.3f}  (gap {r['mid_gap']:.3f})")
    else:
        sdf = pd.DataFrame()
        print("\n  No soft violations either -- mids are monotonic for every team.")

    # ---- 2. WITHIN-ROUND DUTCH BOOK ----------------------------------------
    # Kalshi trading fee per contract = ceil(0.07 * C * P * (1-P)) to the cent.
    # Verified against the live slate (185 GER contracts @ 0.27 -> $2.56). A
    # dutch book only pays if the GROSS lock survives these fees, so we report
    # BOTH gross and net-of-fee here. NOTE: still a SNAPSHOT -- re-run close to
    # kickoff against the freshest discover output for prices near-live.
    def _kalshi_fee(prices: pd.Series) -> float:
        # one contract per slot; sum per-leg ceil-to-cent fees (conservative)
        return float(np.ceil(0.07 * prices * (1.0 - prices) * 100.0).sum() / 100.0)

    print("\n=== 2. Within-round dutch book (buy-all-YES / buy-all-NO) ===")
    print(f"  {'contract':<22}{'slots':>6}{'sum_ask':>9}{'sum_bid':>9}"
          f"{'gross':>9}{'fees':>8}{'NET':>9}   verdict")
    for c, slots in SLOTS.items():
        sub = df[df["contract"] == c]
        if sub.empty:
            continue
        sum_ask = sub["yes_ask"].sum()
        sum_bid = sub["yes_bid"].sum()
        verdict, gross, fees, net = "—", 0.0, 0.0, 0.0
        if sum_ask < slots:                       # buy all YES @ ask
            gross = slots - sum_ask
            fees = _kalshi_fee(sub["yes_ask"])
            net = gross - fees
            verdict = (f"BUY-ALL-YES net +{net:.3f}" if net > 0
                       else f"buy-all-YES gross +{gross:.3f} DIES on fees")
        elif sum_bid > slots:                     # buy all NO @ (1-bid)
            gross = sum_bid - slots
            fees = _kalshi_fee(1.0 - sub["yes_bid"])
            net = gross - fees
            verdict = (f"BUY-ALL-NO net +{net:.3f}" if net > 0
                       else f"buy-all-NO gross +{gross:.3f} DIES on fees")
        print(f"  {c:<22}{slots:>6}{sum_ask:>9.3f}{sum_bid:>9.3f}"
              f"{gross:>9.3f}{fees:>8.3f}{net:>9.3f}   {verdict}")

    # ---- save ---------------------------------------------------------------
    if not hdf.empty:
        hdf.assign(kind="monotonicity").to_parquet(OUT, index=False)
        print(f"\n[save] {OUT} ({len(hdf)} executable flags)")
    else:
        pd.DataFrame(columns=["team", "shallow", "deep", "gross_profit_per_contract"]).to_parquet(OUT, index=False)
        print(f"\n[save] {OUT} (0 executable flags -- empty)")

    print("\nReminders: profits are GROSS (Step 4 applies Kalshi fees); this is a "
          "snapshot (live arbs need the live feed). Cross-platform (Kalshi vs "
          "Polymarket) scanner is deferred until a Polymarket feed is added.")


if __name__ == "__main__":
    main()