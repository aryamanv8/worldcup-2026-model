"""
Smoke-test the fitted model by predicting some marquee 2026 WC fixtures.
Outputs win probabilities, expected goals, and most-likely scores.

Run from the project root:
    uv run python scripts/07_sanity_check_predictions.py
"""
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from wc2026.models.poisson import predict_match

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROCESSED_DIR / "models"

# Headline group-stage fixtures from the 2026 WC
FIXTURES = [
    # (home, away, description)
    ("Brazil",        "Morocco",        "Group C — clash of #5 Elo vs the in-form #12"),
    ("Spain",         "Uruguay",        "Group H — top seed vs Uruguay"),
    ("Spain",         "Saudi Arabia",   "Group H — Spain vs the weakest"),
    ("France",        "Norway",         "Group I — France vs in-form Norway"),
    ("England",       "Croatia",        "Group L — England's opener"),
    ("Argentina",     "Algeria",        "Group J — champions vs Algeria"),
    ("Germany",       "Ecuador",        "Group E — Ecuador's higher Elo than Germany"),
    ("Mexico",        "South Korea",    "Group A — host vs strong AFC side"),
    ("United States", "Paraguay",       "Group D — most-competitive group opener"),
    ("Portugal",      "Colombia",       "Group K — two top-7 Elo sides"),
]


def main() -> None:
    print("Loading fitted model and team features...")
    with open(MODELS_DIR / "poisson_v1.pkl", "rb") as f:
        bundle = pickle.load(f)
    model = bundle["model"]
    confederation_levels = bundle["confederation_levels"]

    team_features = pd.read_parquet(PROCESSED_DIR / "team_features.parquet")

    print(f"\nPredicting {len(FIXTURES)} marquee 2026 WC fixtures (neutral venue, competitive):\n")
    print(f"{'Matchup':<32}  {'λ_h':>5}  {'λ_a':>5}  {'P(H)':>6}  {'P(D)':>6}  {'P(A)':>6}  {'ML':>5}")
    print("-" * 90)

    for home, away, _desc in FIXTURES:
        result = predict_match(
            fitted_model=model,
            team_features=team_features,
            home_team=home,
            away_team=away,
            is_neutral=True,
            is_competitive=True,
            confederation_levels=confederation_levels,
        )
        ml = result["most_likely_score"]
        print(
            f"{home + ' vs ' + away:<32}  "
            f"{result['lambda_home']:5.2f}  {result['lambda_away']:5.2f}  "
            f"{result['probs']['home']:5.1%}  "
            f"{result['probs']['draw']:5.1%}  "
            f"{result['probs']['away']:5.1%}  "
            f"{ml[0]}-{ml[1]}"
        )

    # Detailed look at one match — show the score matrix
    print("\n" + "=" * 90)
    print("Detailed view: Brazil vs Morocco (Group C)")
    print("=" * 90)
    result = predict_match(
        fitted_model=model,
        team_features=team_features,
        home_team="Brazil",
        away_team="Morocco",
        is_neutral=True,
        is_competitive=True,
        confederation_levels=confederation_levels,
        max_goals=5,
    )
    print(f"\nExpected goals: Brazil {result['lambda_home']:.2f} -- {result['lambda_away']:.2f} Morocco")
    print(f"Outcome probs: P(Brazil win)={result['probs']['home']:.1%}, "
          f"P(draw)={result['probs']['draw']:.1%}, "
          f"P(Morocco win)={result['probs']['away']:.1%}")

    mtx = result["score_matrix"]
    print("\nScore distribution P(Brazil goals = row, Morocco goals = col):")
    print(f"{'':>8}", end="")
    for j in range(mtx.shape[1]):
        print(f"  Mor:{j:>2}", end="")
    print()
    for i in range(mtx.shape[0]):
        print(f"Bra:{i:>2}  ", end="")
        for j in range(mtx.shape[1]):
            print(f"  {100*mtx[i, j]:5.1f}%", end="")
        print()


if __name__ == "__main__":
    main()