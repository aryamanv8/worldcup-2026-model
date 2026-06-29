#!/usr/bin/env python3
"""
33_cross_market_consistency.py  —  knockout cross-market checks (analysis only)

The knockout markets (per-match, reach-round, champion) are priced by Kalshi in
separate silos, but they are all linked by one bracket. Our LIVE joint model
(scripts/32) gives a single coherent distribution, so we can flag two things:

  A. MARKET-INTERNAL inconsistency (near-arb, model-free): for one team the de-vigged
     market prices must be monotone across nested rounds —
        P(reach R16) >= P(reach QF) >= P(reach SF) >= P(reach final) >= P(champion).
     A violation means the market itself is mispriced (script 24 checks the
     executable bid/ask version; this is the softer de-vig view across the board).

  B. MODEL-vs-MARKET divergence on the same nested ladder, using the LIVE sim (not
     the stale pre-tournament one). Big gaps are candidate signals — to be treated
     with the usual correction/skepticism, NOT as free money.

Inputs (Mac): data/processed/tournament_probs_live.parquet (from script 32) and
data/processed/model_vs_market.parquet (from script 23). Skips gracefully if either
is missing. Output: reports/cross_market_check.md + console.

Run (Mac): uv run python scripts/33_cross_market_consistency.py
Test     : python scripts/33_cross_market_consistency.py --selftest
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = REPO_ROOT / "data" / "processed"
LIVE = PROCESSED / "tournament_probs_live.parquet"
MVM = PROCESSED / "model_vs_market.parquet"
OUT_MD = REPO_ROOT / "reports" / "cross_market_check.md"

# nested ladder, shallow -> deep (prob must be non-increasing)
LADDER = ["reach_round_of_16", "reach_quarter_final", "reach_semi_final",
          "reach_final", "champion"]
LIVE_COL = {"reach_round_of_16": "reach_R16", "reach_quarter_final": "reach_QF",
            "reach_semi_final": "reach_SF", "reach_final": "reach_F", "champion": "champion"}


def monotonicity_violations(price_by_contract: dict, tol: float = 0.01) -> list:
    """Given {contract: price} for one team, return list of (shallow, deep, gap) where
    a deeper round is priced ABOVE a shallower one by more than tol (a violation)."""
    out = []
    present = [c for c in LADDER if c in price_by_contract and price_by_contract[c] is not None]
    for i in range(len(present) - 1):
        s, d = present[i], present[i + 1]
        gap = price_by_contract[d] - price_by_contract[s]   # should be <= 0
        if gap > tol:
            out.append((s, d, round(gap, 4)))
    return out


def run() -> int:
    if not MVM.exists():
        print(f"[skip] {MVM.name} missing — run scripts 22/23 first.")
        return 0
    mvm = pd.read_parquet(MVM)
    live = pd.read_parquet(LIVE) if LIVE.exists() else None
    if live is None:
        print(f"[note] {LIVE.name} not found — running MARKET-internal checks only "
              f"(complete the bracket + run script 32 for the model-vs-market view).")

    lines = ["# Cross-market consistency check", ""]

    # ---- A. market-internal monotonicity ----
    lines += ["## A. Market-internal violations (deeper round priced above shallower)", ""]
    viol_rows = []
    for team, g in mvm.groupby("team"):
        price = {r["contract"]: r["market_devig"] for _, r in g.iterrows()}
        for s, d, gap in monotonicity_violations(price):
            viol_rows.append((team, s, d, gap))
    if viol_rows:
        lines += ["| team | shallow | deeper | gap (deeper−shallow) |", "|---|---|---|---|"]
        for team, s, d, gap in sorted(viol_rows, key=lambda x: -x[3]):
            lines.append(f"| {team} | {s} | {d} | +{gap:.3f} |")
        lines += ["", "_These violate nesting — the market is internally inconsistent. "
                  "Cross-check against script 24 for an executable (bid/ask) lock._"]
    else:
        lines.append("_None — market prices are internally monotone (expected on a liquid board)._")

    # ---- B. live model vs market ----
    if live is not None:
        lines += ["", "## B. Live model vs market (biggest divergences)", "",
                  "| team | contract | live model | market | model−market |",
                  "|---|---|---|---|---|"]
        lp = live.set_index("team")
        rows = []
        for _, r in mvm.iterrows():
            t, c = r["team"], r["contract"]
            col = LIVE_COL.get(c)
            if col and t in lp.index and col in lp.columns:
                m = float(lp.loc[t, col])
                rows.append((t, c, m, float(r["market_devig"]), m - float(r["market_devig"])))
        for t, c, m, mk, d in sorted(rows, key=lambda x: -abs(x[4]))[:20]:
            lines.append(f"| {t} | {c} | {m:.1%} | {mk:.1%} | {d*100:+.1f} pts |")
        lines += ["", "_Divergence is a candidate signal, not free money — apply the "
                  "market-blend correction and skepticism (the model can still be wrong)._"]

    OUT_MD.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nWrote {OUT_MD}")
    return 0


def _selftest() -> int:
    # a clean nested ladder -> no violations
    ok = {"reach_round_of_16": 0.60, "reach_quarter_final": 0.40,
          "reach_semi_final": 0.25, "reach_final": 0.12, "champion": 0.06}
    assert monotonicity_violations(ok) == [], monotonicity_violations(ok)
    # champion priced above reach_final -> one violation
    bad = dict(ok); bad["champion"] = 0.20
    v = monotonicity_violations(bad)
    assert len(v) == 1 and v[0][0] == "reach_final" and v[0][1] == "champion", v
    print(f"[selftest] monotonicity: clean ladder OK; injected violation caught {v[0]}")
    print("[selftest] passed.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    raise SystemExit(_selftest() if a.selftest else run())
