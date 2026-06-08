"""
Build per-country squad-value history from Transfermarkt player valuations.

For each TM country and each month from 2008-01 to 2026-12, computes:
  - top_n_mean_eur:    mean €value of top-23 players from that country as of date
  - n_active_players:  count of valued players for that country

Output: data/processed/country_value_history.parquet
"""

from pathlib import Path

import pandas as pd

from wc2026.data.structure import all_teams, load_groups
from wc2026.features.squad_values import (
    build_country_value_history,
    tm_country_for,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_TM = PROJECT_ROOT / "data" / "raw" / "transfermarkt"
STRUCTURE_PATH = PROJECT_ROOT / "data" / "external" / "wc2026_structure.yaml"
PROCESSED = PROJECT_ROOT / "data" / "processed"


def main() -> None:
    print("Loading Transfermarkt data...")
    players = pd.read_csv(
        RAW_TM / "players.csv.gz", compression="gzip", low_memory=False
    )
    valuations = pd.read_csv(
        RAW_TM / "player_valuations.csv.gz", compression="gzip",
        parse_dates=["date"],
    )
    print(f"  {len(players):,} players, {len(valuations):,} valuations")

    print("Building country value history (~30-60s)...")
    hist = build_country_value_history(
        players, valuations,
        n_top=23, freq="MS",
        date_start="2008-01-01", date_end="2026-12-01",
    )
    print(
        f"  {len(hist):,} (country, date) snapshots across "
        f"{hist['country'].nunique()} countries"
    )

    # Verify WC team coverage
    groups = load_groups(STRUCTURE_PATH)
    wc_teams = all_teams(groups)
    tm_country_set = set(hist["country"].unique())

    print("\nWC team → TM country mapping verification:")
    unmapped = []
    for team in wc_teams:
        if tm_country_for(team, tm_country_set) is None:
            unmapped.append(team)
    if unmapped:
        print(f"  WARNING: {len(unmapped)} WC teams have no TM mapping:")
        for t in unmapped:
            print(f"    - {t}")
    else:
        print(f"  All 48 WC teams mapped successfully ✓")

    out_path = PROCESSED / "country_value_history.parquet"
    hist.to_parquet(out_path, index=False)
    print(f"\nSaved → {out_path}")

    # Sanity check: current values for headline teams
    print("\nSpot check: top-23 mean value as of 2026-06-01")
    print("-" * 70)
    snapshot = hist[hist["date"] == pd.Timestamp("2026-06-01")].copy()
    snapshot["top_n_mean_eur_m"] = snapshot["top_n_mean_eur"] / 1e6
    snapshot = snapshot.sort_values("top_n_mean_eur_m", ascending=False)

    spot_teams = [
        "Spain", "France", "Argentina", "Brazil", "England", "Germany",
        "Belgium", "Netherlands", "Portugal", "Italy", "Croatia",
        "United States", "Mexico", "Canada", "Japan", "Korea, South",
        "Saudi Arabia", "Iran", "Australia",
        "Cote d'Ivoire", "Senegal", "Morocco",
        "Curacao", "Haiti", "Cabo Verde",
    ]
    for c in spot_teams:
        row = snapshot[snapshot["country"] == c]
        if len(row) == 0:
            print(f"  {c:<25}  (not in TM data)")
            continue
        val_m = row["top_n_mean_eur_m"].iloc[0]
        n = row["n_active_players"].iloc[0]
        rank = (snapshot["top_n_mean_eur_m"] >= val_m).sum()
        print(f"  {c:<25}  €{val_m:>6.1f}M mean   {n:>5} valued   "
              f"(rank {rank}/{len(snapshot)})")


if __name__ == "__main__":
    main()