"""
Elo rating system for international football.

Implements the standard 'World Football Elo' formulation (per eloratings.net).
Each team has a rating R. After each match, ratings update by:

    R_new = R_old + K * (actual_score - expected_score)

where:
    expected_score = 1 / (1 + 10^((R_opp - R_self - HA) / 400))
    K = K0 * G
    K0 = base importance constant (varies by tournament type)
    G  = goal-difference multiplier (1.0, 1.5, or (11+N)/8 for N>=3)
    HA = home advantage in rating points (0 if neutral venue)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from tqdm import tqdm

# --- Hyperparameters --------------------------------------------------------
DEFAULT_RATING = 1500.0   # initial rating for any team's first appearance
HOME_ADVANTAGE = 100.0    # rating points added to home team (0 if neutral)

# K-factor by tournament importance (per eloratings.net classification)
K_FACTORS: dict[str, float] = {
    # World Cup
    "FIFA World Cup": 60.0,
    "FIFA World Cup qualification": 40.0,
    # Continental championships
    "UEFA Euro": 50.0,
    "Copa América": 50.0,
    "African Cup of Nations": 50.0,
    "AFC Asian Cup": 50.0,
    "Gold Cup": 50.0,
    "CONCACAF Championship": 50.0,
    # Continental qualifiers
    "UEFA Euro qualification": 40.0,
    "African Cup of Nations qualification": 40.0,
    "AFC Asian Cup qualification": 40.0,
    # Major regular competitions
    "UEFA Nations League": 40.0,
    "Confederations Cup": 40.0,
    # Friendlies — lowest weight
    "Friendly": 20.0,
}
DEFAULT_K = 30.0  # fallback for any tournament not in the map above


# --- Core functions ---------------------------------------------------------
def goal_diff_multiplier(goal_diff: int) -> float:
    """World Football Elo G-factor: scales K by absolute goal difference."""
    n = abs(int(goal_diff))
    if n <= 1:
        return 1.0
    if n == 2:
        return 1.5
    return (11.0 + n) / 8.0


def expected_score(rating_self: float, rating_opp: float, home_adv: float = 0.0) -> float:
    """Logistic expected score in [0, 1] given ratings and home advantage."""
    diff = rating_opp - rating_self - home_adv
    return 1.0 / (1.0 + 10.0 ** (diff / 400.0))


def k_factor_for(tournament: str) -> float:
    """Returns the base K factor for a given tournament name."""
    return K_FACTORS.get(tournament, DEFAULT_K)


def compute_elo_history(
    results: pd.DataFrame,
    default_rating: float = DEFAULT_RATING,
    home_advantage: float = HOME_ADVANTAGE,
) -> pd.DataFrame:
    """
    Walks through every match chronologically and produces a long-format
    Elo history (one row per team per match).

    Args:
        results: DataFrame with columns
            [date, home_team, away_team, home_score, away_score, tournament, neutral].
        default_rating: Initial rating for a team's first appearance.
        home_advantage: Rating points added to the home team's effective strength
            (set to 0 for matches played at a neutral venue).

    Returns:
        Long-format DataFrame with columns:
            date, team, opponent, tournament, is_home, neutral,
            rating_before, rating_after, k_used.
        Two rows per match (one per team) — supports both per-team and
        per-match queries.
    """
    # Drop unplayed matches (future scheduled fixtures have NaN scores).
    # These are useful as simulator inputs but cannot contribute to Elo.
    n_total = len(results)
    played = results.dropna(subset=["home_score", "away_score"])
    n_dropped = n_total - len(played)
    if n_dropped > 0:
        print(f"  [compute_elo_history] Skipping {n_dropped} unplayed/incomplete matches.")
    results_sorted = played.sort_values("date").reset_index(drop=True)

    ratings: dict[str, float] = {}
    rows: list[dict] = []

    for _, m in tqdm(results_sorted.iterrows(), total=len(results_sorted), desc="Computing Elo"):
        home, away = m["home_team"], m["away_team"]
        home_score, away_score = int(m["home_score"]), int(m["away_score"])
        tournament = m["tournament"]
        neutral = bool(m["neutral"])
        date = m["date"]

        r_home = ratings.get(home, default_rating)
        r_away = ratings.get(away, default_rating)
        ha = 0.0 if neutral else home_advantage

        # Actual scores: win=1, draw=0.5, loss=0
        if home_score > away_score:
            s_home = 1.0
        elif home_score < away_score:
            s_home = 0.0
        else:
            s_home = 0.5
        s_away = 1.0 - s_home

        e_home = expected_score(r_home, r_away, home_adv=ha)
        e_away = 1.0 - e_home

        k = k_factor_for(tournament) * goal_diff_multiplier(home_score - away_score)

        new_r_home = r_home + k * (s_home - e_home)
        new_r_away = r_away + k * (s_away - e_away)

        rows.append({
            "date": date, "team": home, "opponent": away, "tournament": tournament,
            "is_home": True, "neutral": neutral,
            "rating_before": r_home, "rating_after": new_r_home, "k_used": k,
        })
        rows.append({
            "date": date, "team": away, "opponent": home, "tournament": tournament,
            "is_home": False, "neutral": neutral,
            "rating_before": r_away, "rating_after": new_r_away, "k_used": k,
        })

        ratings[home] = new_r_home
        ratings[away] = new_r_away

    return pd.DataFrame(rows)


def latest_ratings(elo_history: pd.DataFrame) -> pd.DataFrame:
    """Returns the most recent Elo rating for each team."""
    return (
        elo_history.sort_values("date")
        .groupby("team", as_index=False)
        .tail(1)
        [["team", "date", "rating_after"]]
        .rename(columns={"rating_after": "elo"})
        .sort_values("elo", ascending=False)
        .reset_index(drop=True)
    )


def rating_as_of(elo_history: pd.DataFrame, team: str, as_of: pd.Timestamp) -> float:
    """
    Returns a team's Elo rating immediately after their last match on or before
    `as_of`. Returns DEFAULT_RATING if the team has no prior matches.
    """
    mask = (elo_history["team"] == team) & (elo_history["date"] <= as_of)
    matches = elo_history.loc[mask].sort_values("date")
    if len(matches) == 0:
        return DEFAULT_RATING
    return float(matches.iloc[-1]["rating_after"])