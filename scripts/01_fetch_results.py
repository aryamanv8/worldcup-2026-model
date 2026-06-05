"""
Day 1, Step 1: Fetch historical international match results.

Run from the project root:
    uv run python scripts/01_fetch_results.py
"""
from pathlib import Path

import pandas as pd

from wc2026.data.results import (
    download_raw_data,
    load_results,
    load_shootouts,
    load_goalscorers,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def main() -> None:
    print(f"Saving raw data to {RAW_DIR}")
    paths = download_raw_data(RAW_DIR)
    print(f"  Downloaded {len(paths)} files.")

    print("\nLoading and inspecting results...")
    results = load_results(RAW_DIR)
    shootouts = load_shootouts(RAW_DIR)
    goalscorers = load_goalscorers(RAW_DIR)

    all_teams = pd.concat([results["home_team"], results["away_team"]]).nunique()

    print(f"\n  Match results: {len(results):,} rows")
    print(f"    Date range: {results['date'].min().date()} → {results['date'].max().date()}")
    print(f"    Unique teams (all-time): {all_teams}")
    print(f"    Unique tournaments: {results['tournament'].nunique()}")
    print(f"  Shootouts: {len(shootouts):,} rows")
    print(f"  Goalscorers: {len(goalscorers):,} rows")

    # Show what kinds of matches we have
    print("\n  Top 10 tournament types by match count:")
    top_tournaments = results["tournament"].value_counts().head(10)
    for tournament, count in top_tournaments.items():
        print(f"    {count:>6,}  {tournament}")

    # Save processed parquet for fast loading later
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    results.to_parquet(PROCESSED_DIR / "results.parquet", index=False)
    shootouts.to_parquet(PROCESSED_DIR / "shootouts.parquet", index=False)
    goalscorers.to_parquet(PROCESSED_DIR / "goalscorers.parquet", index=False)
    print(f"\n  Saved processed parquet files to {PROCESSED_DIR}")


if __name__ == "__main__":
    main()