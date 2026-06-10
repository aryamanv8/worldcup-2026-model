"""
Fit the Dixon-Coles rho parameter on the training data and compare
DC-corrected predictions side-by-side with independent Poisson.

Run from the project root:
    uv run python scripts/08_fit_dixon_coles.py
"""
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from wc2026.features.team_features import build_team_features
from wc2026.models.poisson import (
    fit_dixon_coles_rho,
    filter_complete_features,
    predict_match,
    predict_match_dc,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROCESSED_DIR / "models"

TRAIN_CUTOFF = pd.Timestamp("2024-01-01")
# Snapshot date for the marquee fixtures' team-feature lookup.
# Day before the 2026 WC kicks off.
MARQUEE_AS_OF = pd.Timestamp("2026-06-10")


def main() -> None:
    print("Loading fitted model and training data...")
    with open(MODELS_DIR / "poisson_v1.pkl", "rb") as f:
        bundle = pickle.load(f)
    model = bundle["model"]
    confederation_levels = bundle["confederation_levels"]

    # Load the full training matrix, slice to the same training window the
    # Poisson model used (pre-TRAIN_CUTOFF), then drop incomplete rows so
    # the DC fit sees the same N as the Poisson fit.
    wide = pd.read_parquet(PROCESSED_DIR / "training_matrix.parquet")
    train_wide = wide[wide["date"] < TRAIN_CUTOFF].copy()
    train_wide = filter_complete_features(train_wide)
    print(f"  Training matches: {len(train_wide):,}")

    print("\nFitting Dixon-Coles rho parameter...")
    rho = fit_dixon_coles_rho(model, train_wide, confederation_levels)
    print(f"  Fitted rho = {rho:+.4f}")
    print(f"  (Typical for football: -0.10 to -0.20. Negative = more low-score draws,")
    print(f"   fewer 1-0 / 0-1 wins than independent Poisson predicts.)")

    # Save bundle with rho
    bundle["dc_rho"] = rho
    with open(MODELS_DIR / "poisson_v1.pkl", "wb") as f:
        pickle.dump(bundle, f)
    print(f"  Saved rho to model bundle.")

    # ------------------------------------------------------------------
    # Marquee fixture comparison. Build team_features IN MEMORY using
    # the current build_team_features (with squad-value support) so we
    # don't depend on a potentially-stale team_features.parquet file.
    # ------------------------------------------------------------------
    fixtures = [
        ("Brazil",        "Morocco"),
        ("Spain",         "Uruguay"),
        ("Spain",         "Saudi Arabia"),
        ("France",        "Norway"),
        ("England",       "Croatia"),
        ("Argentina",     "Algeria"),
        ("Germany",       "Ecuador"),
        ("Mexico",        "South Korea"),
        ("United States", "Paraguay"),
        ("Portugal",      "Colombia"),
    ]

    print(f"\nBuilding team features in memory for marquee fixtures "
          f"(as_of={MARQUEE_AS_OF.date()})...")
    results = pd.read_parquet(PROCESSED_DIR / "results.parquet")
    elo_history = pd.read_parquet(PROCESSED_DIR / "elo_history.parquet")
    value_history = pd.read_parquet(PROCESSED_DIR / "country_value_history.parquet")
    fixture_teams = sorted({t for pair in fixtures for t in pair})
    team_features = build_team_features(
        teams=fixture_teams,
        results=results,
        elo_history=elo_history,
        value_history=value_history,
        as_of=MARQUEE_AS_OF,
    )

    print(f"\nIndependent Poisson  vs  Dixon-Coles  ({len(fixtures)} fixtures, neutral, competitive):")
    print(f"{'Matchup':<32}  {'P(H)':>5} → {'P(H)':>5}  {'P(D)':>5} → {'P(D)':>5}  {'P(A)':>5} → {'P(A)':>5}")
    print("-" * 88)

    for home, away in fixtures:
        a = predict_match(model, team_features, home, away,
                          confederation_levels=confederation_levels)
        b = predict_match_dc(model, team_features, home, away, rho=rho,
                             confederation_levels=confederation_levels)
        print(
            f"{home + ' vs ' + away:<32}  "
            f"{a['probs']['home']:5.1%} → {b['probs']['home']:5.1%}  "
            f"{a['probs']['draw']:5.1%} → {b['probs']['draw']:5.1%}  "
            f"{a['probs']['away']:5.1%} → {b['probs']['away']:5.1%}"
        )

    # Detailed side-by-side score matrix on one match
    print("\n" + "=" * 88)
    print("Detailed comparison: Brazil vs Morocco")
    print("=" * 88)
    a = predict_match(model, team_features, "Brazil", "Morocco",
                      confederation_levels=confederation_levels, max_goals=4)
    b = predict_match_dc(model, team_features, "Brazil", "Morocco", rho=rho,
                         confederation_levels=confederation_levels, max_goals=4)

    print(f"\nIndependent Poisson (P x 100):")
    for i in range(5):
        for j in range(5):
            print(f"  {100*a['score_matrix'][i, j]:5.1f}", end="")
        print()

    print(f"\nDixon-Coles corrected (P x 100):")
    for i in range(5):
        for j in range(5):
            print(f"  {100*b['score_matrix'][i, j]:5.1f}", end="")
        print()

    print(f"\nDelta (DC - Poisson, P x 100):")
    for i in range(5):
        for j in range(5):
            delta = 100 * (b['score_matrix'][i, j] - a['score_matrix'][i, j])
            print(f"  {delta:+5.1f}", end="")
        print()


if __name__ == "__main__":
    main()