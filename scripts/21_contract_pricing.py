"""
21_contract_pricing.py

Stage-1 capstone: convert Monte Carlo tournament simulations into the contract
fair-value table Stage 2 consumes -- AND verify the simulator is structurally
correct in the same pass.

The end goal of Stage 1 is this file's output: data/processed/fair_values_2026.parquet,
with a fair value + Monte Carlo CI for every tradeable contract, proven
internally consistent. When the consistency report says PASS, Stage 1 is done.

Why this doubles as simulator validation
----------------------------------------
We already validated the match model (scripts 18-20). A simulation is just
calibrated match outcomes composed through bracket rules, so the only thing left
to check is that the bracket logic is structurally sound. Two checks prove it,
with no historical data required:
  - SLOT SUMS: summed over teams, P(reach round R) must equal the exact number of
    slots in round R (champion=1, final=2, SF=4, QF=8, R16=16, R32/advance=32,
    group winners=12). Each simulated tournament fills every slot exactly once, so
    these sums are exact -- any deviation means the sim mislabels rounds.
  - MONOTONICITY: per team, P(champion) <= P(reach final) <= ... <= P(advance).
    Holds by construction off one sim set; the check confirms the contract
    definitions and round ordinal are coded correctly.

Input schema (what the simulator must emit)
-------------------------------------------
data/processed/simulation_results.parquet, long format, one row per (sim, team):
  - sim_id       : int, 0..N-1
  - team         : str
  - group        : str (group label, e.g. 'A'..'L')
  - group_rank   : int, final position in group (1..4)
  - furthest_round : one of ROUND_ORDER below (deepest stage the team reached;
                     'final' = lost final, 'champion' = won it)

Output
------
  - parquet : data/processed/fair_values_2026.parquet  (long: team, group, contract,
              fair_value, mc_stderr, ci_lo, ci_hi, n_sims)
  - console : consistency report + PASS/FAIL verdict

Run
---
  uv run python scripts/21_contract_pricing.py --selftest        # synthetic demo, runs today
  uv run python scripts/21_contract_pricing.py                   # on real sim output
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT = REPO_ROOT / "data" / "processed" / "simulation_results.parquet"
OUTPUT = REPO_ROOT / "data" / "processed" / "fair_values_2026.parquet"

# 2026 format: 48 teams, 12 groups of 4, top 2 + 8 best thirds -> 32-team knockout.
ROUND_ORDER = ["group", "round_of_32", "round_of_16",
               "quarter_final", "semi_final", "final", "champion"]
ROUND_IDX = {r: i for i, r in enumerate(ROUND_ORDER)}

# Contract -> (round threshold this contract requires). "advance" == reach R32.
REACH_CONTRACTS = {
    "advance_from_group": "round_of_32",
    "reach_round_of_16": "round_of_16",
    "reach_quarter_final": "quarter_final",
    "reach_semi_final": "semi_final",
    "reach_final": "final",
    "champion": "champion",
}
# Expected slot counts (sum of fair values over all teams must equal these exactly).
EXPECTED_SLOTS = {
    "win_group": 12, "advance_from_group": 32, "reach_round_of_16": 16,
    "reach_quarter_final": 8, "reach_semi_final": 4, "reach_final": 2, "champion": 1,
}
SLOT_TOL = 1e-6           # sums are exact up to float noise
MONO_TOL = 1e-9


# --------------------------------------------------------------------------- #
def wilson(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (np.nan, np.nan)
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def price_contracts(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return (long fair-value table, consistency report)."""
    required = {"sim_id", "team", "group", "group_rank", "furthest_round"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"simulation_results missing columns: {missing}")
    bad = set(df["furthest_round"].unique()) - set(ROUND_ORDER)
    if bad:
        raise ValueError(f"unknown furthest_round labels: {bad}")

    n_sims = int(df["sim_id"].nunique())
    df = df.copy()
    df["depth"] = df["furthest_round"].astype(str).map(ROUND_IDX).astype(int)

    # Per-match indicator columns, then mean over sims per team.
    df["win_group"] = (df["group_rank"] == 1).astype(float)
    for contract, rnd in REACH_CONTRACTS.items():
        df[contract] = (df["depth"] >= ROUND_IDX[rnd]).astype(float)

    contracts = ["win_group"] + list(REACH_CONTRACTS)
    agg = df.groupby("team").agg(
        group=("group", "first"),
        **{c: (c, "mean") for c in contracts},
    ).reset_index()

    # Long format with CIs.
    rows = []
    for _, r in agg.iterrows():
        for c in contracts:
            p = float(r[c])
            lo, hi = wilson(p, n_sims)
            rows.append({
                "team": r["team"], "group": r["group"], "contract": c,
                "fair_value": p, "mc_stderr": float(np.sqrt(p * (1 - p) / n_sims)),
                "ci_lo": lo, "ci_hi": hi, "n_sims": n_sims,
            })
    fair = pd.DataFrame(rows)

    # ---- consistency report -------------------------------------------------
    slot_check = {}
    for c, expected in EXPECTED_SLOTS.items():
        observed = float(agg[c].sum())
        slot_check[c] = {"observed": observed, "expected": expected,
                         "ok": abs(observed - expected) <= SLOT_TOL}

    # monotonicity per team across the reach-ladder (deepest -> shallowest)
    ladder = ["champion", "reach_final", "reach_semi_final", "reach_quarter_final",
              "reach_round_of_16", "advance_from_group"]
    max_viol = 0.0
    for _, r in agg.iterrows():
        vals = [r[c] for c in ladder]
        for a, b in zip(vals[:-1], vals[1:]):      # each <= next
            max_viol = max(max_viol, a - b)

    report = {
        "n_sims": n_sims,
        "n_teams": int(agg.shape[0]),
        "slot_sums": slot_check,
        "monotonicity_max_violation": max_viol,
        "passed": all(v["ok"] for v in slot_check.values()) and max_viol <= MONO_TOL,
    }
    return fair, report


def print_report(report: dict) -> None:
    print(f"\n=== Consistency report ({report['n_sims']} sims, {report['n_teams']} teams) ===")
    print(f"  {'contract':<22}{'observed':>10}{'expected':>10}   ok")
    for c, v in report["slot_sums"].items():
        print(f"  {c:<22}{v['observed']:>10.4f}{v['expected']:>10}   {'YES' if v['ok'] else 'NO'}")
    print(f"\n  monotonicity max violation: {report['monotonicity_max_violation']:.2e} "
          f"({'ok' if report['monotonicity_max_violation'] <= MONO_TOL else 'VIOLATION'})")
    print(f"\n  VERDICT: {'PASS -- simulator structurally sound, fair values ready for Stage 2' if report['passed'] else 'FAIL -- see above'}")


def make_selftest(n_sims: int = 20000, seed: int = 0) -> pd.DataFrame:
    """Synthetic but structurally valid sim output: exact slot counts per sim."""
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(48)]
    group_of = {t: "ABCDEFGHIJKL"[i // 4] for i, t in enumerate(teams)}
    # furthest-round bucket sizes per sim (sum to 48; produce exact slot counts)
    buckets = [("champion", 1), ("final", 1), ("semi_final", 2), ("quarter_final", 4),
               ("round_of_16", 8), ("round_of_32", 16), ("group", 16)]
    rows = []
    for s in range(n_sims):
        perm = rng.permutation(teams)
        furthest, i = {}, 0
        for rnd, k in buckets:
            for t in perm[i:i + k]:
                furthest[t] = rnd
            i += k
        # group ranks: deepest run in each group = rank 1 (bracket-plausible)
        for g in set(group_of.values()):
            gt = [t for t in teams if group_of[t] == g]
            gt.sort(key=lambda t: -ROUND_IDX[furthest[t]])
            for rank, t in enumerate(gt, 1):
                rows.append({"sim_id": s, "team": t, "group": g,
                             "group_rank": rank, "furthest_round": furthest[t]})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true",
                    help="run on synthetic structurally-valid data instead of real sim output")
    ap.add_argument("--input", type=str, default=str(INPUT))
    args = ap.parse_args()

    if args.selftest:
        print("[selftest] generating synthetic structurally-valid simulations...")
        df = make_selftest()
    else:
        path = Path(args.input)
        if not path.exists():
            print(f"[FATAL] {path} not found.")
            print("        Run the simulator to emit it, or use --selftest to see the format.")
            sys.exit(1)
        df = pd.read_parquet(path)
        print(f"[load] {len(df):,} rows, {df['sim_id'].nunique()} sims")

    fair, report = price_contracts(df)
    print_report(report)

    # show a few headline contracts
    champ = fair[fair["contract"] == "champion"].sort_values("fair_value", ascending=False).head(5)
    print("\n  Top-5 champion fair values:")
    for _, r in champ.iterrows():
        print(f"    {r['team']:<8} {r['fair_value']:.4f}  "
              f"[{r['ci_lo']:.4f}, {r['ci_hi']:.4f}]")

    if not args.selftest:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        fair.to_parquet(OUTPUT, index=False)
        print(f"\n[save] {OUTPUT}")
    else:
        print("\n[selftest] not saving output. With real sim data, this writes "
              "fair_values_2026.parquet.")


if __name__ == "__main__":
    main()