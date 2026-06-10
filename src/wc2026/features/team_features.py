"""
Per-team feature construction.

For each team qualified for the World Cup, computes a single feature row
that the match-level model consumes. Features cover:
  - Current Elo and 12-month trend
  - Recent form (goals scored/conceded, win rate)
  - Sample-size diagnostics (matches played in window)
  - Rest proxy (days since last match)
  - Confederation (categorical)
  - Squad market value snapshot (log EUR, with has_actual_value flag)

All "recent" features use a 12-month rolling window ending at a specified
'as_of' date. We separate friendlies vs. competitive matches because
friendlies have different stakes and signal.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from wc2026.data.confederations import confederation_of
from wc2026.features.elo import DEFAULT_RATING
from wc2026.features.squad_values import TEAM_TO_TM_COUNTRY
from wc2026.models.poisson import VALUE_LOG_MEAN

FRIENDLY_TOURNAMENTS = {"Friendly"}


def _team_matches(results: pd.DataFrame, team: str) -> pd.DataFrame:
    """All matches a team played, with their score and the opponent's score
    expressed from THEIR perspective."""
    home = results[results["home_team"] == team].copy()
    home["team_score"] = home["home_score"]
    home["opp_score"] = home["away_score"]
    home["opponent"] = home["away_team"]
    home["was_home"] = ~home["neutral"]

    away = results[results["away_team"] == team].copy()
    away["team_score"] = away["away_score"]
    away["opp_score"] = away["home_score"]
    away["opponent"] = away["home_team"]
    away["was_home"] = False  # never home if listed as away

    cols = ["date", "team_score", "opp_score", "opponent", "tournament", "neutral", "was_home"]
    return pd.concat([home[cols], away[cols]], ignore_index=True).sort_values("date")


def _window_stats(matches: pd.DataFrame, competitive_only: bool) -> dict:
    """Aggregates a set of matches into goals-per-match / win-rate stats."""
    if competitive_only:
        matches = matches[~matches["tournament"].isin(FRIENDLY_TOURNAMENTS)]
    n = len(matches)
    if n == 0:
        return {"n": 0, "gf_per_match": None, "ga_per_match": None, "win_rate": None}
    gf = matches["team_score"].sum() / n
    ga = matches["opp_score"].sum() / n
    wins = (matches["team_score"] > matches["opp_score"]).sum()
    return {
        "n": n,
        "gf_per_match": float(gf),
        "ga_per_match": float(ga),
        "win_rate": float(wins / n),
    }


def _elo_as_of(elo_history: pd.DataFrame, team: str, as_of: pd.Timestamp) -> float:
    """Most recent Elo for a team on or before `as_of`. Defaults to 1500 if no history."""
    sub = elo_history[(elo_history["team"] == team) & (elo_history["date"] <= as_of)]
    if len(sub) == 0:
        return DEFAULT_RATING
    return float(sub.sort_values("date").iloc[-1]["rating_after"])


def _build_value_lookups(
    value_history: pd.DataFrame,
    as_of: pd.Timestamp,
) -> tuple[dict[str, float], dict[str, float]]:
    """
    Build two per-country log-value dictionaries:
      - active: the country's log_value at the exact year_month of `as_of`.
      - earliest: the country's earliest known log_value (backfill prior for
        pre-coverage dates).
    """
    ym = as_of.year * 100 + as_of.month
    vh = value_history[["country", "date", "top_n_mean_eur"]].copy()
    vh["country"] = vh["country"].astype(object)
    vh["ym"] = (vh["date"].dt.year * 100 + vh["date"].dt.month).astype("int64")
    vh["log_value"] = np.log(vh["top_n_mean_eur"].clip(lower=1.0))

    vh_at_ym = vh[vh["ym"] == ym]
    active = dict(zip(vh_at_ym["country"], vh_at_ym["log_value"]))

    earliest_df = (
        vh.sort_values("date")
        .groupby("country", as_index=False)
        .first()[["country", "log_value"]]
    )
    earliest = dict(zip(earliest_df["country"], earliest_df["log_value"]))

    return active, earliest


def build_team_features(
    teams: list[str],
    results: pd.DataFrame,
    elo_history: pd.DataFrame,
    value_history: pd.DataFrame,
    as_of: pd.Timestamp,
    window_days: int = 365,
) -> pd.DataFrame:
    """
    Build a one-row-per-team feature table.

    Args:
        teams: List of team names to build features for.
        results: Cleaned match results (must have 'date' as datetime).
        elo_history: Output of compute_elo_history().
        value_history: Output of build_country_value_history() — monthly
            country-level squad value snapshots.
        as_of: Snapshot date — features reflect everything known up to and
            including this date.
        window_days: Window for recent-form stats (default 365 = 12 months).

    Returns:
        DataFrame with one row per team. value_log_eur is always non-null
        (imputed to VALUE_LOG_MEAN if no TM coverage) so predict_match
        never gets a NaN-feature row. has_actual_value distinguishes the
        three cases: exact match (1), backfilled prior (0), imputed (0).
    """
    as_of = pd.Timestamp(as_of)
    window_start = as_of - timedelta(days=window_days)

    # Precompute squad-value lookups (one pass over value_history)
    active_value, earliest_value = _build_value_lookups(value_history, as_of)

    def _to_tm(name: str) -> str:
        return TEAM_TO_TM_COUNTRY.get(name, name)

    rows = []
    for team in teams:
        m_all = _team_matches(results, team)
        m_all = m_all[m_all["date"] <= as_of]
        m_window = m_all[m_all["date"] >= window_start]

        stats_all = _window_stats(m_window, competitive_only=False)
        stats_comp = _window_stats(m_window, competitive_only=True)

        elo_now = _elo_as_of(elo_history, team, as_of)
        elo_past = _elo_as_of(elo_history, team, window_start)

        # Days since last competitive match (rest proxy)
        m_comp = m_all[~m_all["tournament"].isin(FRIENDLY_TOURNAMENTS)]
        if len(m_comp) > 0:
            days_since_competitive = (as_of - m_comp["date"].max()).days
        else:
            days_since_competitive = None

        # Days since any match
        if len(m_all) > 0:
            days_since_any = (as_of - m_all["date"].max()).days
        else:
            days_since_any = None

        # Squad value lookup: three-way fallback.
        #   1. Active (country, ym) match -> real value, has_actual=1
        #   2. Backfill prior (country's earliest known) -> proxy, has_actual=0
        #   3. No TM coverage at all -> impute population mean (z=0), has_actual=0
        # The model NEVER sees NaN here, so predict_match always produces a
        # non-empty design matrix. has_actual_value lets the GLM partial out
        # the noise from imputed/backfilled rows.
        tm_country = _to_tm(team)
        if tm_country in active_value:
            value_log_eur = active_value[tm_country]
            has_actual_value = 1
        elif tm_country in earliest_value:
            value_log_eur = earliest_value[tm_country]
            has_actual_value = 0
        else:
            value_log_eur = VALUE_LOG_MEAN
            has_actual_value = 0

        rows.append({
            "team": team,
            "confederation": confederation_of(team),
            "elo_current": elo_now,
            "elo_12mo_ago": elo_past,
            "elo_trend_12mo": elo_now - elo_past,
            "n_matches_12mo": stats_all["n"],
            "gf_per_match_12mo": stats_all["gf_per_match"],
            "ga_per_match_12mo": stats_all["ga_per_match"],
            "win_rate_12mo": stats_all["win_rate"],
            "n_competitive_12mo": stats_comp["n"],
            "gf_per_match_12mo_competitive": stats_comp["gf_per_match"],
            "ga_per_match_12mo_competitive": stats_comp["ga_per_match"],
            "win_rate_12mo_competitive": stats_comp["win_rate"],
            "days_since_last_match": days_since_any,
            "days_since_last_competitive": days_since_competitive,
            "value_log_eur": value_log_eur,
            "has_actual_value": has_actual_value,
        })

    return pd.DataFrame(rows)