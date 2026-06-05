"""
Day 1, Step 3: Load and validate the 2026 World Cup structure.

Cross-checks that we have Elo data for all 48 qualified teams, then shows
current Elo ratings by group as a sanity check on group strength.

Run from the project root:
    uv run python scripts/03_load_wc_structure.py
"""
from pathlib import Path

import pandas as pd

from wc2026.data.structure import (
    load_structure,
    load_groups,
    all_teams,
    all_group_fixtures,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STRUCTURE_PATH = PROJECT_ROOT / "data" / "external" / "wc2026_structure.yaml"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def closest_matches(target: str, candidates: list[str], n: int = 3) -> list[str]:
    """Cheap fuzzy match: returns candidates that share a 3-letter prefix or substring."""
    target_low = target.lower()
    prefix = target_low[:3]
    hits = [c for c in candidates if c.lower().startswith(prefix)]
    if len(hits) < n:
        # Try substring fallback (any word in target appears in candidate)
        for word in target_low.split():
            if len(word) < 4:
                continue
            hits.extend(c for c in candidates if word in c.lower() and c not in hits)
    return hits[:n]


def main() -> None:
    print(f"Loading WC 2026 structure from {STRUCTURE_PATH.name}...")
    structure = load_structure(STRUCTURE_PATH)
    groups = structure["groups"]
    teams = all_teams(groups)
    print(f"  Loaded {len(groups)} groups, {len(teams)} teams.")

    print("\nLoading Elo ratings...")
    elo = pd.read_parquet(PROCESSED_DIR / "elo_latest.parquet")
    elo_lookup = dict(zip(elo["team"], elo["elo"]))
    available = list(elo_lookup.keys())

    # Check coverage
    missing = [t for t in teams if t not in elo_lookup]
    if missing:
        print(f"\n  WARNING: {len(missing)} team(s) missing from Elo data:")
        for t in missing:
            cands = closest_matches(t, available)
            print(f"    '{t}'  -- closest candidates in Elo data: {cands}")
        print("\n  Resolve these by editing wc2026_structure.yaml to use the matching name.")
        return

    print("  All 48 teams have Elo data.\n")

    # Show each group with sorted Elo
    group_metrics = []
    for letter in sorted(groups.keys()):
        group_teams = groups[letter]
        ratings = sorted(
            [(t, elo_lookup[t]) for t in group_teams],
            key=lambda x: -x[1],
        )
        avg = sum(r for _, r in ratings) / 4
        spread = max(r for _, r in ratings) - min(r for _, r in ratings)
        group_metrics.append((letter, avg, spread, ratings))

        print(f"  Group {letter}  (avg Elo {avg:.0f}, spread {spread:.0f})")
        for team, rating in ratings:
            print(f"    {rating:7.1f}  {team}")
        print()

    print("  Group difficulty ranking (highest avg Elo = toughest):")
    for letter, avg, spread, _ in sorted(group_metrics, key=lambda x: -x[1]):
        print(f"    Group {letter}: avg={avg:.0f}  spread={spread:.0f}")

    fixtures = all_group_fixtures(groups)
    print(f"\n  Total group stage fixtures: {len(fixtures)} (6 per group × 12 groups)")


if __name__ == "__main__":
    main()