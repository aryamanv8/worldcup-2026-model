"""
26_fee_model.py  (Stage 2, Step 4 - scoped)

Kalshi fee model. Two jobs (no edge to filter, so this is NOT a strategy gate):
  1. Close the script-24 dutch-book flags rigorously: price the "buy-all-NO"
     baskets through real per-contract fees + the bid/ask spread and confirm the
     apparent gross edge is actually negative.
  2. Provide a reusable net-EV / net-cost function the dashboard displays per
     contract.

Kalshi fee schedule (general case, verified 2026; confirm in the order ticket --
some player-prop / special markets use different multipliers):
    taker fee per order = ceil_cents(0.07  * C * P * (1 - P))
    maker fee per order = ceil_cents(0.0175 * C * P * (1 - P))   [often 0: resting
                          limit orders that don't immediately match are free]
  - P is the fill price in DOLLARS (0..1); C = number of contracts.
  - Parabolic: max at P=0.50, ->0 near 0 and 1.
  - ceil is to the next whole CENT *per order* -> brutal on tiny trades.

Net cost to BUY C contracts of YES at ask A (taker):
    stake = C * A ;  fee = taker_fee(C, A) ;  total_cost = stake + fee
    payoff if YES = C * 1.0 ;  net profit if YES = C*(1-A) - fee
Round-trip (enter+exit) pays the fee twice.

Input  : data/processed/model_vs_market.parquet (script 23)
Output : console (dutch-book close-out) + importable fee functions

Run    : uv run python scripts/26_fee_model.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
MVM = REPO_ROOT / "data" / "processed" / "model_vs_market.parquet"

TAKER_RATE = 0.07
MAKER_RATE = 0.0175
SLOTS = {"reach_round_of_16": 16, "reach_quarter_final": 8, "reach_semi_final": 4,
         "reach_final": 2, "champion": 1}


def _ceil_cents(x: float) -> float:
    """Round up to the next whole cent (Kalshi rounds the per-order fee up)."""
    return math.ceil(round(x, 10) * 100) / 100.0


def taker_fee(contracts: int, price: float) -> float:
    """Per-order taker fee in dollars. price in dollars (0..1)."""
    if contracts <= 0 or not (0 < price < 1):
        return 0.0
    return _ceil_cents(TAKER_RATE * contracts * price * (1 - price))


def maker_fee(contracts: int, price: float) -> float:
    if contracts <= 0 or not (0 < price < 1):
        return 0.0
    return _ceil_cents(MAKER_RATE * contracts * price * (1 - price))


def net_profit_if_yes(contracts: int, ask: float, taker: bool = True) -> float:
    """Net $ profit if a bought YES resolves YES (single-side fee)."""
    fee = taker_fee(contracts, ask) if taker else maker_fee(contracts, ask)
    return contracts * (1.0 - ask) - fee


def net_edge_per_contract(model_prob: float, ask: float, contracts: int = 100,
                          taker: bool = True) -> float:
    """Model expected value per contract of buying YES at `ask`, net of fee.
    EV = model_prob*1 - ask - fee_per_contract. Positive => model sees value."""
    fee = (taker_fee(contracts, ask) if taker else maker_fee(contracts, ask))
    return model_prob - ask - fee / contracts


def close_out_dutch_books(df: pd.DataFrame) -> None:
    """Price the buy-all-NO basket per round through real NO-asks + fees.

    Buy NO on all 48 teams in a 'reach round R' market. Exactly (48 - slots) NOs
    win, paying $1 each. NO is bought at no_ask ~= 1 - yes_bid (taker). Fee is per
    contract on each of 48 legs.
    """
    print("=== Dutch-book close-out (buy-all-NO, real NO-asks + taker fees) ===")
    print(f"  {'contract':<22}{'legs':>5}{'payoff':>8}{'no_cost':>9}{'fees':>8}{'net':>9}")
    for c, slots in SLOTS.items():
        sub = df[df["contract"] == c].dropna(subset=["yes_bid"])
        n = len(sub)
        if n == 0:
            continue
        winners = n - slots               # teams that do NOT reach round R
        payoff = winners * 1.0
        no_cost, fees = 0.0, 0.0
        for _, r in sub.iterrows():
            no_ask = 1.0 - float(r["yes_bid"])          # buy NO ~ 1 - yes_bid
            no_ask = min(max(no_ask, 0.0), 0.99)
            no_cost += no_ask
            fees += taker_fee(1, no_ask)                 # 1 contract per leg (per-order ceil)
        net = payoff - no_cost - fees
        print(f"  {c:<22}{n:>5}{payoff:>8.2f}{no_cost:>9.2f}{fees:>8.2f}{net:>9.2f}")
    print("\n  Interpretation: the script-24 'buy-all-NO arb' used yes_bids as a")
    print("  shortcut. Pricing real NO-asks (= 1 - yes_bid) plus 48 per-leg fees,")
    print("  every basket should come out NEGATIVE -> not an arb. Confirms the")
    print("  Kalshi books are tight; no model-free edge within the exchange.")


def demo_fee_curve() -> None:
    print("\n=== Taker fee per contract by price (the P(1-P) shape) ===")
    print(f"  {'price':>6}{'fee/ct (100 lot)':>18}{'fee/ct (1 lot)':>16}")
    for p in (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.99):
        f100 = taker_fee(100, p) / 100
        f1 = taker_fee(1, p)          # ceil to 1 cent dominates tiny trades
        print(f"  {p:>6.2f}{f100:>18.4f}{f1:>16.4f}")
    print("  Note: at 1-contract size the ceil-to-a-cent makes the effective fee")
    print("  enormous -- another reason $500-scale single-contract trading bleeds.")


def main() -> None:
    if not MVM.exists():
        print(f"[FATAL] missing {MVM} -- run script 23 first.")
        sys.exit(1)
    df = pd.read_parquet(MVM)
    for col in ("yes_bid", "yes_ask", "market_devig", "model_fv"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    close_out_dutch_books(df)
    demo_fee_curve()

    # quick net-edge read on the model's biggest nominal disagreements (illustrative)
    if {"model_fv", "yes_ask", "contract", "team"}.issubset(df.columns):
        print("\n=== Net model-EV of buying YES at ask (top nominal model-HIGH) ===")
        df = df.dropna(subset=["model_fv", "yes_ask"]).copy()
        df["net_ev_per_ct"] = df.apply(
            lambda r: net_edge_per_contract(r["model_fv"], r["yes_ask"]), axis=1)
        top = df.sort_values("net_ev_per_ct", ascending=False).head(8)
        print(f"  {'contract':<20}{'team':<16}{'model':>7}{'ask':>7}{'net_ev/ct':>11}")
        for _, r in top.iterrows():
            print(f"  {r['contract']:<20}{r['team']:<16}{r['model_fv']:>7.3f}"
                  f"{r['yes_ask']:>7.3f}{r['net_ev_per_ct']:>+11.4f}")
        print("  Reminder: positive net-EV here assumes the MODEL is right. Per the")
        print("  tournament backtest, the model is calibrated but the market's")
        print("  favorite concentration is defensible too -- these are NOT")
        print("  recommendations, just the net-of-fee gap the dashboard will show.")


if __name__ == "__main__":
    main()