"""
Diagnostic: verify Transfermarkt data and identify team-name mapping issues.

Checks:
  1. How many of our 48 WC teams have a direct match in national_teams.csv?
  2. For unmatched teams, what are the closest candidates in TM data?
  3. How many players are mapped to each WC team's country?
  4. What's the date range of player_valuations?

Run from the project root:
    uv run python scripts/12_explore_transfermarkt.py
"""
from pathlib import Path

import pandas as pd

from wc2026.data.structure import load_groups, all_teams

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_TM = PROJECT_ROOT / "data" / "raw" / "transfermarkt"
STRUCTURE_PATH = PROJECT_ROOT / "data" / "external" / "wc2026_structure.yaml"


def find_close_matches(target: str, candidates: list[str], n: int = 3) -> list[str]:
    """Cheap fuzzy matching for name suggestions."""
    target_low = target.lower()
    # Direct prefix match
    hits = [c for c in candidates if c.lower().startswith(target_low[:3])]
    # Substring match
    for word in target_low.split():
        if len(word) >= 4:
            hits.extend(c for c in candidates if word in c.lower() and c not in hits)
    return hits[:n]


def main() -> None:
    print("Loading Transfermarkt data...")
    players = pd.read_csv(RAW_TM / "players.csv.gz", compression="gzip", low_memory=False)
    valuations = pd.read_csv(RAW_TM / "player_valuations.csv.gz", compression="gzip",
                              parse_dates=["date"])
    national_teams = pd.read_csv(RAW_TM / "national_teams.csv.gz", compression="gzip")
    countries = pd.read_csv(RAW_TM / "countries.csv.gz", compression="gzip")

    print(f"  players:        {len(players):>8,} rows, {players.shape[1]} columns")
    print(f"  valuations:     {len(valuations):>8,} rows, "
          f"date range {valuations['date'].min().date()} → {valuations['date'].max().date()}")
    print(f"  national_teams: {len(national_teams):>8,} rows")
    print(f"  countries:      {len(countries):>8,} rows")

    print("\n" + "=" * 90)
    print("CHECK 1: WC teams matched against national_teams.csv (for current total_market_value)")
    print("=" * 90)
    nt_names = set(national_teams["name"].astype(str))
    groups = load_groups(STRUCTURE_PATH)
    wc_teams = all_teams(groups)

    matched_nt = []
    unmatched_nt = []
    for team in wc_teams:
        if team in nt_names:
            matched_nt.append(team)
        else:
            unmatched_nt.append(team)
    print(f"  Direct matches:   {len(matched_nt)} / {len(wc_teams)}")
    print(f"  Unmatched teams (need name mapping):")
    for t in unmatched_nt:
        suggestions = find_close_matches(t, list(nt_names))
        print(f"    {t!r:<28} → suggestions: {suggestions}")

    print("\n" + "=" * 90)
    print("CHECK 2: WC teams matched against players.country_of_citizenship "
          "(for historical aggregations)")
    print("=" * 90)
    countries_in_players = set(
        players["country_of_citizenship"].dropna().astype(str).unique()
    )
    print(f"  Distinct countries in players.country_of_citizenship: {len(countries_in_players)}")

    matched_cit = []
    unmatched_cit = []
    for team in wc_teams:
        if team in countries_in_players:
            matched_cit.append(team)
        else:
            unmatched_cit.append(team)
    print(f"  Direct matches:   {len(matched_cit)} / {len(wc_teams)}")
    print(f"  Unmatched teams:")
    for t in unmatched_cit:
        suggestions = find_close_matches(t, list(countries_in_players))
        print(f"    {t!r:<28} → suggestions: {suggestions}")

    print("\n" + "=" * 90)
    print("CHECK 3: For matched teams, number of players + sample current values "
          "(spot-check)")
    print("=" * 90)
    # Use a few headline teams to spot-check
    for t in ["Spain", "France", "Argentina", "Brazil", "England", "Saudi Arabia", "Canada"]:
        if t not in countries_in_players:
            continue
        n_players = (players["country_of_citizenship"] == t).sum()
        n_with_valuation = players[
            (players["country_of_citizenship"] == t)
            & players["market_value_in_eur"].notna()
        ].shape[0]
        total_value_now = players.loc[
            players["country_of_citizenship"] == t, "market_value_in_eur"
        ].sum()
        # National team total_market_value if present
        nt_val = national_teams.loc[national_teams["name"] == t, "total_market_value"]
        if len(nt_val) > 0 and pd.notna(nt_val.iloc[0]):
            nt_val_str = f"€{int(nt_val.iloc[0]):>14,}"
        else:
            nt_val_str = "n/a"
        print(f"  {t:<15}  n_players={n_players:>5}  "
              f"n_valued={n_with_valuation:>5}  "
              f"current_sum=€{int(total_value_now):>14,}  "
              f"nt_total_mv={nt_val_str}")

    print("\n" + "=" * 90)
    print("CHECK 4: Valuation history depth — useful for backtesting historical WCs")
    print("=" * 90)
    by_year = valuations.assign(year=valuations["date"].dt.year).groupby("year").size()
    print("  Valuations by year:")
    for year, n in by_year.items():
        print(f"    {year}: {n:,}")

    print("\n" + "=" * 90)
    print("CHECK 5: Hunt for Ivory Coast / Côte d'Ivoire variants")
    print("=" * 90)
    needles = ["ivoire", "ivory", "côte", "cote d"]
    # Search in player citizenship
    cit_lower = {c.lower(): c for c in countries_in_players}
    cit_hits = sorted({orig for low, orig in cit_lower.items()
                       if any(n in low for n in needles)})
    print(f"  Matches in players.country_of_citizenship: {cit_hits}")
    # Search in national_teams names and country_names
    nt_lower = {n.lower(): n for n in national_teams["name"].astype(str)}
    nt_hits = sorted({orig for low, orig in nt_lower.items()
                      if any(n in low for n in needles)})
    print(f"  Matches in national_teams.name:            {nt_hits}")
    # And in countries.csv
    co_lower = {c.lower(): c for c in countries["country_name"].astype(str)}
    co_hits = sorted({orig for low, orig in co_lower.items()
                      if any(n in low for n in needles)})
    print(f"  Matches in countries.country_name:         {co_hits}")


if __name__ == "__main__":
    main()