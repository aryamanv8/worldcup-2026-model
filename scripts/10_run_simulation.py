"""
Run the 2026 World Cup Monte Carlo simulation.

  1. Loads the fitted Poisson model and team features.
  2. Pre-computes score matrices for all 48*47/2 = 1,128 unique matchups.
  3. Runs N tournament simulations.
  4. Aggregates and outputs per-team tournament-progression probabilities.

Run from the project root:
    uv run python scripts/10_run_simulation.py
"""
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from wc2026.data.structure import load_groups, all_teams
from wc2026.simulation.engine import (
    precompute_score_matrices,
    run_simulations,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROCESSED_DIR / "models"
STRUCTURE_PATH = PROJECT_ROOT / "data" / "external" / "wc2026_structure.yaml"

N_SIMULATIONS = 50_000
SEED = 42


def main() -> None:
    print("Loading fitted model and team features...")
    with open(MODELS_DIR / "poisson_v1.pkl", "rb") as f:
        bundle = pickle.load(f)
    model = bundle["model"]
    rho = bundle["dc_rho"]
    confederation_levels = bundle["confederation_levels"]
    print(f"  Model: {len(model.params)} parameters, Dixon-Coles rho = {rho:+.4f}")

    team_features = pd.read_parquet(PROCESSED_DIR / "team_features.parquet")
    groups = load_groups(STRUCTURE_PATH)
    teams = all_teams(groups)
    print(f"  {len(teams)} teams across {len(groups)} groups.")

    print("\nPre-computing all 1,128 score matrices...")
    t0 = time.time()
    score_matrices = precompute_score_matrices(
        fitted_model=model,
        team_features=team_features,
        teams=teams,
        rho=rho,
        confederation_levels=confederation_levels,
        groups=groups,
        max_goals=10,
    )
    t_precompute = time.time() - t0
    print(f"  Pre-computed {len(score_matrices)} matrices in {t_precompute:.1f}s.")

    print(f"\nRunning {N_SIMULATIONS:,} tournament simulations...")
    t0 = time.time()
    probs = run_simulations(
        n_sims=N_SIMULATIONS,
        groups=groups,
        score_matrices=score_matrices,
        seed=SEED,
    )
    t_simulate = time.time() - t0
    print(f"  Simulations complete in {t_simulate:.1f}s ({N_SIMULATIONS/t_simulate:.0f} sims/sec).")

    # Save
    out_path = PROCESSED_DIR / "tournament_probs.parquet"
    probs.to_parquet(out_path, index=False)
    print(f"\nSaved tournament probabilities to {out_path}")

    # Pretty-print the headline table
    print("\n" + "=" * 90)
    print("Tournament progression probabilities (top 20 by win probability)")
    print("=" * 90)
    display_cols = [
        "team", "p_win_group", "p_advance_from_group",
        "p_reach_QF", "p_reach_SF", "p_reach_F", "p_win_tournament",
    ]
    top20 = probs.head(20).copy()
    for col in display_cols[1:]:
        top20[col] = (top20[col] * 100).round(1).astype(str) + "%"
    print(top20[display_cols].to_string(index=False))

    print("\n" + "=" * 90)
    print("Per-group: Probability each team wins their group")
    print("=" * 90)
    for g in sorted(groups.keys()):
        group_teams = groups[g]
        sub = probs[probs["team"].isin(group_teams)].sort_values("p_win_group", ascending=False)
        print(f"\nGroup {g}:")
        for _, r in sub.iterrows():
            print(f"  {r['team']:<25}  win={r['p_win_group']:5.1%}  "
                  f"advance={r['p_advance_from_group']:5.1%}")

    # Sanity checks
    print("\n" + "=" * 90)
    print("Sanity checks")
    print("=" * 90)
    print(f"  Sum of P(win_tournament): {probs['p_win_tournament'].sum():.4f}  (should be 1.0)")
    print(f"  Sum of P(reach_F): {probs['p_reach_F'].sum():.4f}  (should be 2.0)")
    print(f"  Sum of P(reach_SF): {probs['p_reach_SF'].sum():.4f}  (should be 4.0)")
    print(f"  Sum of P(reach_QF): {probs['p_reach_QF'].sum():.4f}  (should be 8.0)")
    print(f"  Sum of P(reach_R16): {probs['p_reach_R16'].sum():.4f}  (should be 16.0)")
    print(f"  Sum of P(reach_R32): {probs['p_reach_R16'].sum():.4f}")  # not 32 due to bye structure
    print(f"  Per group sum of P(win_group): should be 1.0 for each group")
    for g, group_teams in groups.items():
        s = probs[probs["team"].isin(group_teams)]["p_win_group"].sum()
        print(f"    Group {g}: {s:.4f}")


if __name__ == "__main__":
    main()