"""
Rebuild data/processed/team_features.parquet using the new build_team_features
(which now includes squad-value columns). Run this once after updating
team_features.py so any script that loads the parquet (e.g., script 11, the
simulator) gets the new columns.

Team list is taken from the CONFEDERATIONS dict — the 48 WC 2026 qualified
teams. Snapshot date is the day before the tournament kicks off.

Run from the project root:
    uv run python scripts/17_rebuild_team_features_parquet.py
"""
from pathlib import Path

import pandas as pd

from wc2026.data.confederations import CONFEDERATIONS
from wc2026.features.team_features import build_team_features

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

AS_OF = pd.Timestamp("2026-06-10")  # day before WC kickoff


def main() -> None:
    print("Loading inputs...")
    results = pd.read_parquet(PROCESSED_DIR / "results.parquet")
    elo_history = pd.read_parquet(PROCESSED_DIR / "elo_history.parquet")
    value_history = pd.read_parquet(PROCESSED_DIR / "country_value_history.parquet")
    print(f"  Results: {len(results):,}")
    print(f"  Elo history: {len(elo_history):,}")
    print(f"  Value history: {len(value_history):,}")

    teams = sorted(CONFEDERATIONS.keys())
    print(f"\nBuilding team features for {len(teams)} teams as of {AS_OF.date()}...")
    tf = build_team_features(
        teams=teams,
        results=results,
        elo_history=elo_history,
        value_history=value_history,
        as_of=AS_OF,
    )

    out = PROCESSED_DIR / "team_features.parquet"
    tf.to_parquet(out, index=False)
    print(f"\n  Saved: {out}")
    print(f"  Shape: {tf.shape}")

    # Sanity check the new columns
    print(f"\n  has_actual_value breakdown:")
    print(f"    real (=1):     {(tf['has_actual_value'] == 1).sum()}")
    print(f"    imputed (=0):  {(tf['has_actual_value'] == 0).sum()}")
    print(f"\n  Top 10 by value_log_eur:")
    top = tf.nlargest(10, "value_log_eur")[["team", "value_log_eur", "has_actual_value"]]
    print(top.to_string(index=False))
    print(f"\n  Bottom 10 by value_log_eur (excluding imputed):")
    real = tf[tf["has_actual_value"] == 1].nsmallest(
        10, "value_log_eur"
    )[["team", "value_log_eur", "has_actual_value"]]
    print(real.to_string(index=False))


if __name__ == "__main__":
    main()