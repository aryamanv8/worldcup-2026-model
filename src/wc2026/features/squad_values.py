"""
Per-country squad value history derived from Transfermarkt player valuations.

For each TM country (by player citizenship) and each monthly snapshot date,
we compute the mean market value of the top-N players from that country.

DESIGN:
  - Top-N (default 23): national teams field ~23-26 players; using top-N filters
    out the noise from country coverage-depth differences in TM's database.
  - Mean (not sum): countries with thin coverage (<23 valued players) aren't
    artificially zeroed by summing in implicit zeros.
  - Monthly snapshots: TM updates player valuations twice yearly (Jun & Dec);
    daily granularity is meaningless. Monthly = 228 snapshots covering 2008-2026.

OUTPUT SCHEMA (returned DataFrame):
  - country (str): TM citizenship name
  - date (datetime): snapshot date (month start)
  - top_n_mean_eur (float): mean €value of top-N players as of date
  - n_active_players (int): count of country players with a valid valuation
                            on or before date (proxy for coverage depth)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# Maps our match-data team names → Transfermarkt country_of_citizenship strings.
# Only entries where the two differ are listed; everything else matches by direct equality.
TEAM_TO_TM_COUNTRY: dict[str, str] = {
    "South Korea": "Korea, South",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Curaçao": "Curacao",
    "Ivory Coast": "Cote d'Ivoire",
}


def tm_country_for(team_name: str, tm_country_set: set[str]) -> str | None:
    """Resolve our team name to the TM citizenship string. None if unmatchable."""
    if team_name in TEAM_TO_TM_COUNTRY:
        candidate = TEAM_TO_TM_COUNTRY[team_name]
        return candidate if candidate in tm_country_set else None
    if team_name in tm_country_set:
        return team_name
    return None


def build_country_value_history(
    players: pd.DataFrame,
    valuations: pd.DataFrame,
    n_top: int = 23,
    freq: str = "MS",
    date_start: str = "2008-01-01",
    date_end: str = "2026-12-01",
) -> pd.DataFrame:
    """
    Compute per-country monthly snapshots of top-N mean market value.

    Algorithm (per country):
      1. Pivot the country's player valuations to (date × player_id) matrix.
      2. Reindex to snapshot grid + forward-fill, so each row reflects each
         player's most recent valuation as of that snapshot date.
      3. For each row (snapshot date), take the top-N values and average them.
      4. NaN values (player not yet rated) are treated as 0 for sorting, then
         excluded from the mean count.

    Returns one row per (country, snapshot date).
    """
    # Build player → country lookup
    player_country = (
        players.dropna(subset=["country_of_citizenship"])
        .set_index("player_id")["country_of_citizenship"]
    )

    # Attach country to each valuation (inner join: drop unknown players)
    vals = valuations.merge(
        player_country.rename("country"),
        left_on="player_id", right_index=True, how="inner",
    )

    snapshot_dates = pd.date_range(date_start, date_end, freq=freq)

    rows: list[dict] = []
    for country, country_vals in vals.groupby("country"):
        # Pivot: index=date, columns=player, values=market_value
        # aggfunc="last" handles rare same-day multiple valuations per player
        pivot = country_vals.pivot_table(
            index="date", columns="player_id",
            values="market_value_in_eur", aggfunc="last",
        )

        # Insert snapshot dates into the index, forward-fill, then keep only snaps
        all_idx = pivot.index.union(snapshot_dates)
        pivot = pivot.reindex(all_idx).sort_index().ffill().loc[snapshot_dates]

        # Vectorized top-N mean across each row
        values = pivot.to_numpy()  # shape (n_snapshots, n_country_players)
        # NaN → 0 so they sort to the bottom in a descending top-N selection
        v_filled = np.where(np.isnan(values), 0.0, values)
        # Sort descending: sort -x ascending, take first n_top columns, negate back
        v_sorted_desc = -np.sort(-v_filled, axis=1)[:, :n_top]

        # Mean over non-zero entries only (so small countries aren't punished
        # by phantom zeros padding the top-N)
        nonzero_mask = v_sorted_desc > 0
        n_in_top = nonzero_mask.sum(axis=1)
        sum_top = v_sorted_desc.sum(axis=1)
        mean_top = np.where(
            n_in_top > 0,
            sum_top / np.maximum(n_in_top, 1),
            0.0,
        )

        # Total valued count for this country at each snapshot date
        n_active = (~np.isnan(values)).sum(axis=1)

        for i, snap_date in enumerate(snapshot_dates):
            rows.append({
                "country": country,
                "date": snap_date,
                "top_n_mean_eur": float(mean_top[i]),
                "n_active_players": int(n_active[i]),
            })

    return pd.DataFrame(rows)