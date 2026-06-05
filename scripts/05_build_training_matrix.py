"""
Build the training matrix for the match-level Poisson model.

We use the date range 2000-01-01 to 2026-06-10 (the day before the WC kicks
off) — gives ~25 years of recent football, excluding ancient data that
reflects a fundamentally different game and any leakage from the 2026 WC
itself.

Run from the project root:
    uv run python scripts/05_build_training_matrix.py
"""
from pathlib import Path

import pandas as pd

from wc2026.features.training_matrix import build_training_matrix

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

MIN_DATE = pd.Timestamp("2000-01-01")
MAX_DATE = pd.Timestamp("2026-06-10")  # day before WC kickoff


def main() -> None:
    print(f"Loading inputs...")
    results = pd.read_parquet(PROCESSED_DIR / "results.parquet")
    elo_history = pd.read_parquet(PROCESSED_DIR / "elo_history.parquet")
    print(f"  Results: {len(results):,} rows")
    print(f"  Elo history: {len(elo_history):,} rows")

    print(f"\nBuilding training matrix [{MIN_DATE.date()} → {MAX_DATE.date()}]...")
    tm = build_training_matrix(
        results=results,
        elo_history=elo_history,
        min_date=MIN_DATE,
        max_date=MAX_DATE,
    )

    out_path = PROCESSED_DIR / "training_matrix.parquet"
    tm.to_parquet(out_path, index=False)
    print(f"\n  Saved: {out_path}")
    print(f"  Shape: {tm.shape}")

    # Diagnostics
    print(f"\n  Target distribution:")
    print(f"    Home goals: mean={tm['home_score'].mean():.2f}, "
          f"max={tm['home_score'].max()}, var={tm['home_score'].var():.2f}")
    print(f"    Away goals: mean={tm['away_score'].mean():.2f}, "
          f"max={tm['away_score'].max()}, var={tm['away_score'].var():.2f}")
    print(f"    (For pure Poisson, mean == variance. Deviation tells us about "
          f"over/underdispersion.)")

    print(f"\n  Outcome breakdown:")
    home_wins = (tm["home_score"] > tm["away_score"]).sum()
    away_wins = (tm["home_score"] < tm["away_score"]).sum()
    draws = (tm["home_score"] == tm["away_score"]).sum()
    n = len(tm)
    print(f"    Home wins: {home_wins:>6,} ({100*home_wins/n:5.1f}%)")
    print(f"    Draws:     {draws:>6,} ({100*draws/n:5.1f}%)")
    print(f"    Away wins: {away_wins:>6,} ({100*away_wins/n:5.1f}%)")

    print(f"\n  Sample size of form features (home_n_matches):")
    print(f"    min={tm['home_n_matches'].min()}, "
          f"median={tm['home_n_matches'].median():.0f}, "
          f"max={tm['home_n_matches'].max()}")

    print(f"\n  Missing-feature counts (matches with insufficient history):")
    for col in ["home_gf_per_match", "away_gf_per_match", "home_win_rate", "away_win_rate"]:
        n_missing = tm[col].isna().sum()
        print(f"    {col}: {n_missing:,} missing ({100*n_missing/n:.1f}%)")

    print(f"\n  Competitive vs friendly split:")
    print(f"    Competitive: {tm['is_competitive'].sum():,} matches")
    print(f"    Friendly:    {(~tm['is_competitive']).sum():,} matches")


if __name__ == "__main__":
    main()