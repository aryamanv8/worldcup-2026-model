"""
Day 1, Step 4: Build the team-level feature table for all 48 WC teams.

Snapshot is taken as of "today" (the script's run date) — but we constrain
to data on or before the day the World Cup starts (2026-06-11) so that
backtesting later doesn't accidentally peek at in-tournament results.

Run from the project root:
    uv run python scripts/04_build_team_features.py
"""
from pathlib import Path

import pandas as pd

from wc2026.data.structure import load_groups, all_teams
from wc2026.features.team_features import build_team_features

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STRUCTURE_PATH = PROJECT_ROOT / "data" / "external" / "wc2026_structure.yaml"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# We "freeze" features as of the day before the tournament starts. This is
# the right snapshot date for forecasting the WC — anything after this would
# leak in-tournament information.
SNAPSHOT_DATE = pd.Timestamp("2026-06-10")


def main() -> None:
    print(f"Snapshot date: {SNAPSHOT_DATE.date()}")
    groups = load_groups(STRUCTURE_PATH)
    teams = all_teams(groups)
    print(f"Building features for {len(teams)} teams...")

    results = pd.read_parquet(PROCESSED_DIR / "results.parquet")
    elo_history = pd.read_parquet(PROCESSED_DIR / "elo_history.parquet")

    features = build_team_features(
        teams=teams,
        results=results,
        elo_history=elo_history,
        as_of=SNAPSHOT_DATE,
    )

    out_path = PROCESSED_DIR / "team_features.parquet"
    features.to_parquet(out_path, index=False)
    print(f"  Saved: {out_path}")
    print(f"  Shape: {features.shape}")

    # Diagnostics
    print("\n  Sample size summary (matches in last 12 months):")
    print(f"    All matches: min={features['n_matches_12mo'].min()}, "
          f"max={features['n_matches_12mo'].max()}, "
          f"median={features['n_matches_12mo'].median():.0f}")
    print(f"    Competitive only: min={features['n_competitive_12mo'].min()}, "
          f"max={features['n_competitive_12mo'].max()}, "
          f"median={features['n_competitive_12mo'].median():.0f}")

    print("\n  Confederation breakdown:")
    print(features["confederation"].value_counts().to_string())

    print("\n  Top 10 teams by 12-month Elo trend (improving):")
    print(
        features.nlargest(10, "elo_trend_12mo")[
            ["team", "elo_current", "elo_trend_12mo", "win_rate_12mo"]
        ].to_string(index=False)
    )

    print("\n  Bottom 10 teams by 12-month Elo trend (declining):")
    print(
        features.nsmallest(10, "elo_trend_12mo")[
            ["team", "elo_current", "elo_trend_12mo", "win_rate_12mo"]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()