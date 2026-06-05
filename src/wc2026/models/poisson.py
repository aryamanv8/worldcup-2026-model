"""
Match-level Poisson goal model.

We model the goals scored by each team in a match as independent Poisson
random variables. The Poisson rate parameter (lambda) for each team is a
function of features describing both teams and the match context, fit by
maximum likelihood (Poisson GLM with log link).

Two-perspective formulation: each historical match is reshaped into two
rows — one row per team's attacking perspective. A single regression then
learns symmetric attack/defense coefficients across both perspectives.

The output of inference for any future match is a full joint score
distribution matrix P(home_goals=i, away_goals=j), from which all standard
prediction-market quantities can be derived.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import poisson


# --- Features used by the model ---------------------------------------------
NUMERIC_FEATURES: list[str] = [
    "attacker_elo_z",
    "defender_elo_z",
    "attacker_gf_per_match",
    "attacker_ga_per_match",
    "attacker_win_rate",
    "defender_gf_per_match",
    "defender_ga_per_match",
    "defender_win_rate",
]
BINARY_FEATURES: list[str] = [
    "is_attacker_home",
    "is_neutral",
    "is_competitive",
]
CATEGORICAL_FEATURES: list[str] = [
    "attacker_confederation",
    "defender_confederation",
]


def pivot_to_long(wide: pd.DataFrame) -> pd.DataFrame:
    """
    Reshape match-level data to attacker/defender long format.
    Each match becomes two rows: home-perspective and away-perspective.
    """
    home_perspective = pd.DataFrame({
        "match_date": wide["date"].values,
        "goals_scored": wide["home_score"].astype(int).values,
        "attacker_team": wide["home_team"].astype(str).values,
        "defender_team": wide["away_team"].astype(str).values,
        "attacker_elo": wide["home_elo"].astype(float).values,
        "defender_elo": wide["away_elo"].astype(float).values,
        "attacker_gf_per_match": wide["home_gf_per_match"].values,
        "attacker_ga_per_match": wide["home_ga_per_match"].values,
        "attacker_win_rate": wide["home_win_rate"].values,
        "defender_gf_per_match": wide["away_gf_per_match"].values,
        "defender_ga_per_match": wide["away_ga_per_match"].values,
        "defender_win_rate": wide["away_win_rate"].values,
        "attacker_confederation": wide["home_confederation"].astype(str).values,
        "defender_confederation": wide["away_confederation"].astype(str).values,
        "is_attacker_home": (~wide["neutral"]).astype(int).values,
        "is_neutral": wide["neutral"].astype(int).values,
        "is_competitive": wide["is_competitive"].astype(int).values,
    })
    away_perspective = pd.DataFrame({
        "match_date": wide["date"].values,
        "goals_scored": wide["away_score"].astype(int).values,
        "attacker_team": wide["away_team"].astype(str).values,
        "defender_team": wide["home_team"].astype(str).values,
        "attacker_elo": wide["away_elo"].astype(float).values,
        "defender_elo": wide["home_elo"].astype(float).values,
        "attacker_gf_per_match": wide["away_gf_per_match"].values,
        "attacker_ga_per_match": wide["away_ga_per_match"].values,
        "attacker_win_rate": wide["away_win_rate"].values,
        "defender_gf_per_match": wide["home_gf_per_match"].values,
        "defender_ga_per_match": wide["home_ga_per_match"].values,
        "defender_win_rate": wide["home_win_rate"].values,
        "attacker_confederation": wide["away_confederation"].astype(str).values,
        "defender_confederation": wide["home_confederation"].astype(str).values,
        # If the home team is NOT at a neutral venue, the away team is "the
        # away side" and gets is_attacker_home = 0. Always 0 from this side.
        "is_attacker_home": np.zeros(len(wide), dtype=int),
        "is_neutral": wide["neutral"].astype(int).values,
        "is_competitive": wide["is_competitive"].astype(int).values,
    })
    return pd.concat([home_perspective, away_perspective], ignore_index=True)


def prepare_design_matrix(
    long_df: pd.DataFrame,
    confederation_levels: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """
    Drop rows with missing features and build the design matrix.

    Returns:
        X: design matrix (numeric + one-hot confederations + intercept)
        y: target vector (goals_scored, int)
        feature_names: column names of X
    """
    needed = NUMERIC_FEATURES + BINARY_FEATURES + CATEGORICAL_FEATURES + ["goals_scored"]
    df = long_df.copy()

    # Standardize Elo (mean ~1500, std ~400 in international football)
    df["attacker_elo_z"] = (df["attacker_elo"] - 1500.0) / 400.0
    df["defender_elo_z"] = (df["defender_elo"] - 1500.0) / 400.0

    df = df.dropna(subset=NUMERIC_FEATURES).reset_index(drop=True)

    if confederation_levels is None:
        confederation_levels = sorted(set(
            df["attacker_confederation"].unique()
        ) | set(df["defender_confederation"].unique()))

    X_num = df[NUMERIC_FEATURES + BINARY_FEATURES].astype(float)

    # One-hot encode confederations (drop one level per side to avoid dummy trap)
    atk_conf = pd.Categorical(df["attacker_confederation"], categories=confederation_levels)
    def_conf = pd.Categorical(df["defender_confederation"], categories=confederation_levels)
    atk_dummies = pd.get_dummies(atk_conf, prefix="atk_conf", drop_first=True).astype(float)
    def_dummies = pd.get_dummies(def_conf, prefix="def_conf", drop_first=True).astype(float)

    X = pd.concat([X_num.reset_index(drop=True),
                   atk_dummies.reset_index(drop=True),
                   def_dummies.reset_index(drop=True)], axis=1)
    X = sm.add_constant(X, has_constant="add")
    y = df["goals_scored"].astype(int).reset_index(drop=True)
    return X, y, X.columns.tolist()


def fit_poisson(X: pd.DataFrame, y: pd.Series) -> sm.GLM:
    """Fit Poisson GLM via statsmodels (log link)."""
    return sm.GLM(y, X, family=sm.families.Poisson()).fit()


def predict_expected_goals(
    fitted_model: sm.GLM,
    features: pd.DataFrame,
) -> np.ndarray:
    """Predict expected goals (lambda) for one or more rows."""
    return np.asarray(fitted_model.predict(features))


def score_matrix(lambda_home: float, lambda_away: float, max_goals: int = 10) -> np.ndarray:
    """
    Independent-Poisson joint score distribution.
    Returns a (max_goals+1) x (max_goals+1) array where entry [i, j]
    is P(home_goals=i, away_goals=j).
    """
    p_h = poisson.pmf(np.arange(max_goals + 1), lambda_home)
    p_a = poisson.pmf(np.arange(max_goals + 1), lambda_away)
    return np.outer(p_h, p_a)


def outcome_probs(score_mtx: np.ndarray) -> dict[str, float]:
    """Marginalize a score matrix into 1X2 (home/draw/away) probabilities."""
    p_home = float(np.tril(score_mtx, -1).sum())  # home > away
    p_draw = float(np.trace(score_mtx))           # diagonal
    p_away = float(np.triu(score_mtx, 1).sum())   # away > home
    total = p_home + p_draw + p_away
    if total > 0:
        p_home, p_draw, p_away = p_home / total, p_draw / total, p_away / total
    return {"home": p_home, "draw": p_draw, "away": p_away}

def predict_match(
    fitted_model,
    team_features: pd.DataFrame,
    home_team: str,
    away_team: str,
    is_neutral: bool = True,
    is_competitive: bool = True,
    confederation_levels: list[str] | None = None,
    max_goals: int = 12,
) -> dict:
    """
    End-to-end match prediction.

    Args:
        fitted_model: A fitted statsmodels GLM (Poisson).
        team_features: DataFrame from team_features.parquet (one row per team).
        home_team: Name of the nominally-home team.
        away_team: Name of the nominally-away team.
        is_neutral: True if played at a neutral venue (default True — the
            common case at the World Cup).
        is_competitive: True if a competitive match (not a friendly).
        confederation_levels: Categorical levels used at training time.
            Required so the one-hot encoding is consistent.
        max_goals: Maximum goals to include in the score matrix.

    Returns:
        Dict containing:
            home_team, away_team
            lambda_home, lambda_away (expected goals)
            score_matrix: (max_goals+1) x (max_goals+1) joint probability array
            probs: {"home": p_home_win, "draw": p_draw, "away": p_away_win}
            most_likely_score: (i, j) tuple
    """
    # Look up team features
    home_feats = team_features[team_features["team"] == home_team]
    away_feats = team_features[team_features["team"] == away_team]
    if len(home_feats) == 0:
        raise KeyError(f"No features found for home team {home_team!r}")
    if len(away_feats) == 0:
        raise KeyError(f"No features found for away team {away_team!r}")
    h = home_feats.iloc[0]
    a = away_feats.iloc[0]

    # Build a one-row wide DataFrame in the same shape as training data
    wide_row = pd.DataFrame([{
        "date": pd.Timestamp.now(),
        "home_team": home_team,
        "away_team": away_team,
        "home_score": 0,  # placeholder; not used by pivot_to_long target column
        "away_score": 0,
        "tournament": "FIFA World Cup" if is_competitive else "Friendly",
        "neutral": is_neutral,
        "is_competitive": is_competitive,
        "home_elo": h["elo_current"],
        "away_elo": a["elo_current"],
        "home_gf_per_match": h["gf_per_match_12mo"],
        "home_ga_per_match": h["ga_per_match_12mo"],
        "home_win_rate": h["win_rate_12mo"],
        "away_gf_per_match": a["gf_per_match_12mo"],
        "away_ga_per_match": a["ga_per_match_12mo"],
        "away_win_rate": a["win_rate_12mo"],
        "home_confederation": h["confederation"],
        "away_confederation": a["confederation"],
    }])

    long_row = pivot_to_long(wide_row)
    X, _, _ = prepare_design_matrix(long_row, confederation_levels)

    lambdas = np.asarray(fitted_model.predict(X))
    # Row 0 is the home-perspective (home team attacking); row 1 is away-perspective.
    lambda_home = float(lambdas[0])
    lambda_away = float(lambdas[1])

    mtx = score_matrix(lambda_home, lambda_away, max_goals=max_goals)
    probs = outcome_probs(mtx)
    most_likely_ij = np.unravel_index(np.argmax(mtx), mtx.shape)

    return {
        "home_team": home_team,
        "away_team": away_team,
        "is_neutral": is_neutral,
        "is_competitive": is_competitive,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "score_matrix": mtx,
        "probs": probs,
        "most_likely_score": (int(most_likely_ij[0]), int(most_likely_ij[1])),
    }

# --- Dixon-Coles low-score correction ---------------------------------------
from scipy.optimize import minimize_scalar


def _tau_factors(home_goals: np.ndarray, away_goals: np.ndarray,
                 lambdas_home: np.ndarray, lambdas_away: np.ndarray,
                 rho: float) -> np.ndarray:
    """
    Compute the Dixon-Coles tau correction factor for each (i, j) pair.

    tau(0,0) = 1 - lambda_h * lambda_a * rho
    tau(0,1) = 1 + lambda_h * rho
    tau(1,0) = 1 + lambda_a * rho
    tau(1,1) = 1 - rho
    tau(i,j) = 1 for all other (i, j)
    """
    tau = np.ones_like(home_goals, dtype=float)
    mask_00 = (home_goals == 0) & (away_goals == 0)
    mask_01 = (home_goals == 0) & (away_goals == 1)
    mask_10 = (home_goals == 1) & (away_goals == 0)
    mask_11 = (home_goals == 1) & (away_goals == 1)
    tau[mask_00] = 1.0 - lambdas_home[mask_00] * lambdas_away[mask_00] * rho
    tau[mask_01] = 1.0 + lambdas_home[mask_01] * rho
    tau[mask_10] = 1.0 + lambdas_away[mask_10] * rho
    tau[mask_11] = 1.0 - rho
    return tau


def fit_dixon_coles_rho(
    fitted_poisson_model,
    wide_df: pd.DataFrame,
    confederation_levels: list[str],
) -> float:
    """
    Fit the Dixon-Coles rho parameter by MLE, holding the Poisson lambdas fixed.

    The full DC log-likelihood given lambdas (lambda_h, lambda_a) and observed
    (home_goals, away_goals) per match is:
        sum [ log Poisson(home_goals; lambda_h)
            + log Poisson(away_goals; lambda_a)
            + log tau(home_goals, away_goals, lambda_h, lambda_a, rho) ]

    Since the Poisson terms don't depend on rho, maximizing over rho reduces
    to maximizing sum log tau. We use scipy.optimize.minimize_scalar.
    """
    # Drop matches with any missing features so both perspectives survive together
    feature_cols = [
        "home_gf_per_match", "home_ga_per_match", "home_win_rate",
        "away_gf_per_match", "away_ga_per_match", "away_win_rate",
    ]
    wide_clean = wide_df.dropna(subset=feature_cols).reset_index(drop=True)

    long_df = pivot_to_long(wide_clean)
    X, _, _ = prepare_design_matrix(long_df, confederation_levels)

    lambdas = np.asarray(fitted_poisson_model.predict(X))
    n = len(wide_clean)
    lambdas_home = lambdas[:n]
    lambdas_away = lambdas[n:]

    home_goals = wide_clean["home_score"].astype(int).values
    away_goals = wide_clean["away_score"].astype(int).values

    def neg_log_lik(rho: float) -> float:
        tau = _tau_factors(home_goals, away_goals, lambdas_home, lambdas_away, rho)
        # Negative tau means the rho is too large in magnitude — return inf to push optimizer away
        if np.any(tau <= 0):
            return np.inf
        return -np.sum(np.log(tau))

    result = minimize_scalar(neg_log_lik, bounds=(-0.4, 0.3), method="bounded")
    return float(result.x)


def score_matrix_dc(
    lambda_home: float,
    lambda_away: float,
    rho: float,
    max_goals: int = 10,
) -> np.ndarray:
    """
    Joint score distribution under Dixon-Coles-corrected independent Poisson.
    """
    base = score_matrix(lambda_home, lambda_away, max_goals=max_goals)
    if rho == 0.0:
        return base

    # Apply tau to the four corrected cells
    base[0, 0] *= (1.0 - lambda_home * lambda_away * rho)
    if max_goals >= 1:
        base[0, 1] *= (1.0 + lambda_home * rho)
        base[1, 0] *= (1.0 + lambda_away * rho)
        base[1, 1] *= (1.0 - rho)

    # Renormalize so total probability = 1 (small numerical drift from the correction)
    s = base.sum()
    if s > 0:
        base = base / s
    return base


def predict_match_dc(
    fitted_model,
    team_features: pd.DataFrame,
    home_team: str,
    away_team: str,
    rho: float,
    is_neutral: bool = True,
    is_competitive: bool = True,
    confederation_levels: list[str] | None = None,
    max_goals: int = 12,
) -> dict:
    """
    Same as predict_match() but applies the Dixon-Coles correction.
    """
    base = predict_match(
        fitted_model=fitted_model,
        team_features=team_features,
        home_team=home_team,
        away_team=away_team,
        is_neutral=is_neutral,
        is_competitive=is_competitive,
        confederation_levels=confederation_levels,
        max_goals=max_goals,
    )
    mtx_dc = score_matrix_dc(base["lambda_home"], base["lambda_away"], rho, max_goals=max_goals)
    probs_dc = outcome_probs(mtx_dc)
    base["score_matrix"] = mtx_dc
    base["probs"] = probs_dc
    base["rho"] = rho
    base["most_likely_score"] = tuple(int(x) for x in np.unravel_index(np.argmax(mtx_dc), mtx_dc.shape))
    return base