"""
Builds the training matrix for the match-level Poisson model.

Each row is one historical match, with:
  - Target: actual home_score and away_score
  - Features for both teams as of just BEFORE the match (point-in-time correct)
  - Match context: home/neutral, tournament type, competitive flag, etc.

Point-in-time correctness is critical: features computed using information
from after the match itself would cause look-ahead bias. We enforce this by
using only Elo ratings before the match (via merge_asof with allow_exact_
matches=False) and rolling form features over [date - 365d, date).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from tqdm import tqdm

from wc2026.data.confederations import CONFEDERATIONS

FRIENDLY_TOURNAMENTS = {"Friendly"}
DEFAULT_ELO = 1500.0
DEFAULT_WINDOW_DAYS = 365


def _build_team_long(results: pd.DataFrame) -> pd.DataFrame:
    """
    Reshape match-level results into team-perspective long format.
    Each played match contributes two rows (one per team).
    """
    played = results.dropna(subset=["home_score", "away_score"]).copy()

    home = pd.DataFrame({
        "team": played["home_team"].values,
        "opponent": played["away_team"].values,
        "date": played["date"].values,
        "team_score": played["home_score"].astype(int).values,
        "opp_score": played["away_score"].astype(int).values,
        "tournament": played["tournament"].values,
        "neutral": played["neutral"].values,
        "was_home": (~played["neutral"]).values,
    })
    away = pd.DataFrame({
        "team": played["away_team"].values,
        "opponent": played["home_team"].values,
        "date": played["date"].values,
        "team_score": played["away_score"].astype(int).values,
        "opp_score": played["home_score"].astype(int).values,
        "tournament": played["tournament"].values,
        "neutral": played["neutral"].values,
        "was_home": False,
    })
    long = pd.concat([home, away], ignore_index=True)
    long["is_competitive"] = ~long["tournament"].isin(FRIENDLY_TOURNAMENTS)
    long["won"] = (long["team_score"] > long["opp_score"]).astype(int)
    long["drew"] = (long["team_score"] == long["opp_score"]).astype(int)
    return long.sort_values(["team", "date"]).reset_index(drop=True)


def _form_for_team(
    team_history: pd.DataFrame | None,
    as_of: pd.Timestamp,
    window_start: pd.Timestamp,
) -> dict:
    """Compute rolling form features for one team given pre-indexed history."""
    empty = {
        "n_matches": 0,
        "n_competitive": 0,
        "gf_per_match": np.nan,
        "ga_per_match": np.nan,
        "win_rate": np.nan,
        "gf_per_match_competitive": np.nan,
        "ga_per_match_competitive": np.nan,
        "days_since_last_match": np.nan,
    }
    if team_history is None or len(team_history) == 0:
        return empty

    mask = (team_history["date"] >= window_start) & (team_history["date"] < as_of)
    window = team_history.loc[mask]
    n = len(window)
    if n == 0:
        return empty

    comp = window[window["is_competitive"]]
    n_comp = len(comp)

    return {
        "n_matches": n,
        "n_competitive": n_comp,
        "gf_per_match": float(window["team_score"].mean()),
        "ga_per_match": float(window["opp_score"].mean()),
        "win_rate": float(window["won"].mean()),
        "gf_per_match_competitive": float(comp["team_score"].mean()) if n_comp > 0 else np.nan,
        "ga_per_match_competitive": float(comp["opp_score"].mean()) if n_comp > 0 else np.nan,
        "days_since_last_match": float((as_of - window["date"].max()).days),
    }


def build_training_matrix(
    results: pd.DataFrame,
    elo_history: pd.DataFrame,
    value_history: pd.DataFrame,
    min_date: pd.Timestamp | None = None,
    max_date: pd.Timestamp | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> pd.DataFrame:
    """
    Build the training matrix for the match-level Poisson model.

    Args:
        results: Full match results with [date, home_team, away_team, scores, ...].
        elo_history: Output of compute_elo_history().
        min_date: Lower bound on match date for inclusion (inclusive).
        max_date: Upper bound on match date for inclusion (inclusive).
        window_days: Lookback for rolling form features (default 365 days).

    Returns:
        DataFrame with one row per match, including target columns
        (home_score, away_score), context columns, and features for both teams.
    """
    # Filter to played matches
    played = results.dropna(subset=["home_score", "away_score"]).copy()
    if min_date is not None:
        played = played[played["date"] >= pd.Timestamp(min_date)]
    if max_date is not None:
        played = played[played["date"] <= pd.Timestamp(max_date)]

    played = played.sort_values("date").reset_index(drop=True)
    played["home_score"] = played["home_score"].astype(int)
    played["away_score"] = played["away_score"].astype(int)

    print(f"  Training set: {len(played):,} matches "
          f"({played['date'].min().date()} → {played['date'].max().date()})")

    # Build team-long format using FULL results (so 1995 matches have 1994 history)
    print("  Indexing team match history...")
    team_long = _build_team_long(results)
    team_history_by_team = {
        team: subdf.reset_index(drop=True)
        for team, subdf in team_long.groupby("team", sort=False)
    }

    # Vectorized Elo lookup via merge_asof.
    # Note: pandas 3.0 introduces two flavors of StringDtype with different NA
    # handling. Our results parquet uses one flavor, elo_history uses another.
    # We normalize both sides to plain object/str before merge_asof.
    print("  Merging point-in-time Elo ratings...")
    elo_sorted = elo_history[["team", "date", "rating_after"]].sort_values("date").copy()
    elo_sorted["team"] = elo_sorted["team"].astype(str)

    # Home Elo
    home_input = (
        played[["date", "home_team"]]
        .sort_values("date")
        .rename(columns={"home_team": "team"})
        .copy()
    )
    home_input["team"] = home_input["team"].astype(str)
    home_elo_join = pd.merge_asof(
        home_input,
        elo_sorted,
        on="date", by="team",
        direction="backward",
        allow_exact_matches=False,
    )
    played["home_elo"] = home_elo_join["rating_after"].fillna(DEFAULT_ELO).values

    # Away Elo
    away_input = (
        played[["date", "away_team"]]
        .sort_values("date")
        .rename(columns={"away_team": "team"})
        .copy()
    )
    away_input["team"] = away_input["team"].astype(str)
    away_elo_join = pd.merge_asof(
        away_input,
        elo_sorted,
        on="date", by="team",
        direction="backward",
        allow_exact_matches=False,
    )
    played["away_elo"] = away_elo_join["rating_after"].fillna(DEFAULT_ELO).values

    # ------------------------------------------------------------------
    # Squad market value (Transfermarkt top-23 mean), point-in-time.
    #
    # Strategy:
    #   - vh has monthly snapshots dated YYYY-MM-01 covering every
    #     (country, month) from 2008-01 to 2026-12.
    #   - Build a year_month integer key on both sides; exact-merge on
    #     (country, year_month). This gives us the snapshot active at
    #     the start of the match's month — point-in-time correct since
    #     snapshots are dated to the 1st.
    #   - For matches before 2008-01 OR for teams not in vh, the merge
    #     returns NaN; we fall back to the country's earliest known
    #     value as a "prior" via a second left-join.
    #   - has_actual_value = 1 iff the primary (country, ym) match
    #     succeeded; 0 if we used the prior or have no value at all.
    # ------------------------------------------------------------------
    print("  Merging point-in-time squad market values...")
    from wc2026.features.squad_values import TEAM_TO_TM_COUNTRY

    def _to_tm(name: str) -> str:
        return TEAM_TO_TM_COUNTRY.get(name, name)

    def _ym(s: pd.Series) -> pd.Series:
        return (s.dt.year * 100 + s.dt.month).astype("int64")

    # Right side: vh slim, with year_month + log_value
    vh_slim = value_history[["country", "date", "top_n_mean_eur"]].copy()
    vh_slim["country"] = vh_slim["country"].astype(object)
    vh_slim["ym"] = _ym(vh_slim["date"])
    vh_slim["log_value"] = np.log(vh_slim["top_n_mean_eur"].clip(lower=1.0))

    # Per-country prior: earliest log_value for each country (for the backfill)
    earliest = (
        vh_slim.sort_values("date")
        .groupby("country", as_index=False)
        .first()[["country", "log_value"]]
        .rename(columns={"log_value": "earliest_log_value"})
    )

    # Left side: map team names to TM countries, compute year_month
    played["_home_country"] = (
        played["home_team"].map(_to_tm).astype(object)
    )
    played["_away_country"] = (
        played["away_team"].map(_to_tm).astype(object)
    )
    played["_ym"] = _ym(played["date"])

    # --- Home side ---
    home_join = (
        played[["_home_country", "_ym"]]
        .rename(columns={"_home_country": "country", "_ym": "ym"})
        .merge(
            vh_slim[["country", "ym", "log_value"]],
            on=["country", "ym"],
            how="left",
        )
        .merge(earliest, on="country", how="left")
    )
    played["home_has_actual_value"] = (
        home_join["log_value"].notna().astype(int).values
    )
    played["home_value_log_eur"] = (
        home_join["log_value"].fillna(home_join["earliest_log_value"]).values
    )

    # --- Away side ---
    away_join = (
        played[["_away_country", "_ym"]]
        .rename(columns={"_away_country": "country", "_ym": "ym"})
        .merge(
            vh_slim[["country", "ym", "log_value"]],
            on=["country", "ym"],
            how="left",
        )
        .merge(earliest, on="country", how="left")
    )
    played["away_has_actual_value"] = (
        away_join["log_value"].notna().astype(int).values
    )
    played["away_value_log_eur"] = (
        away_join["log_value"].fillna(away_join["earliest_log_value"]).values
    )

    played = played.drop(columns=["_home_country", "_away_country", "_ym"])
    
    # Rolling form features per match per team
    print("  Computing form features...")
    home_rows: list[dict] = []
    away_rows: list[dict] = []
    for _, m in tqdm(played.iterrows(), total=len(played), desc="  Form"):
        as_of = m["date"]
        window_start = as_of - pd.Timedelta(days=window_days)
        home_rows.append(_form_for_team(
            team_history_by_team.get(m["home_team"]), as_of, window_start
        ))
        away_rows.append(_form_for_team(
            team_history_by_team.get(m["away_team"]), as_of, window_start
        ))

    home_form = pd.DataFrame(home_rows).add_prefix("home_")
    away_form = pd.DataFrame(away_rows).add_prefix("away_")

    out = pd.concat(
        [played.reset_index(drop=True), home_form, away_form], axis=1
    )

    # Add derived features
    out["home_confederation"] = out["home_team"].map(CONFEDERATIONS).fillna("OTHER")
    out["away_confederation"] = out["away_team"].map(CONFEDERATIONS).fillna("OTHER")
    out["is_competitive"] = ~out["tournament"].isin(FRIENDLY_TOURNAMENTS)
    out["elo_diff"] = out["home_elo"] - out["away_elo"]
    out["same_confederation"] = out["home_confederation"] == out["away_confederation"]

    return out