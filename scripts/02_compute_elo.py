"""
Day 1, Step 2: Compute historical Elo ratings from match results.

Uses the standard 'World Football Elo' formulation. Walks through every
international match in chronological order and produces a rating history
that we can later query at any date.

Run from the project root:
    uv run python scripts/02_compute_elo.py
"""
from pathlib import Path

import pandas as pd

from wc2026.features.elo import compute_elo_history, latest_ratings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def main() -> None:
    print("Loading match results...")
    results = pd.read_parquet(PROCESSED_DIR / "results.parquet")
    print(f"  {len(results):,} matches loaded.")

    print("\nComputing Elo history (~30 seconds)...")
    elo_hist = compute_elo_history(results)

    hist_path = PROCESSED_DIR / "elo_history.parquet"
    elo_hist.to_parquet(hist_path, index=False)
    print(f"\n  Saved Elo history: {hist_path}")
    print(f"  Total team-match observations: {len(elo_hist):,}")

    latest = latest_ratings(elo_hist)
    latest_path = PROCESSED_DIR / "elo_latest.parquet"
    latest.to_parquet(latest_path, index=False)
    print(f"  Saved latest ratings: {latest_path}")

    print("\n  Top 25 teams by current Elo rating:")
    print(latest.head(25).to_string(index=False))


if __name__ == "__main__":
    main()