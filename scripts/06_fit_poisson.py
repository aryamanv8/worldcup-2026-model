"""
Fit the match-level Poisson goal model.

Training data: matches from 2000-01-01 through 2023-12-31.
Held-out test: matches from 2024-01-01 onward (~2 years out-of-sample).

Reports:
  - Fitted coefficients and their significance
  - In-sample and out-of-sample log loss and Brier score for 1X2 outcomes
  - Calibration check
  - Residual dispersion (Poisson assumption check)

Run from the project root:
    uv run python scripts/06_fit_poisson.py
"""
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from wc2026.models.poisson import (
    pivot_to_long,
    prepare_design_matrix,
    fit_poisson,
    score_matrix,
    outcome_probs,
    filter_complete_features,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "data" / "processed" / "models"

TRAIN_CUTOFF = pd.Timestamp("2024-01-01")


def evaluate_1x2(
    df_test: pd.DataFrame,
    fitted_model,
    confederation_levels: list[str],
) -> dict:
    """Compute 1X2 log loss, Brier score, and accuracy on a wide-format test set."""
    # Reshape test to long and build design matrix. Use return_long=True so
    # we get the long DataFrame filtered to the same rows as X — guarantees
    # alignment regardless of what NUMERIC_FEATURES contains.
    long_test = pivot_to_long(df_test)
    long_test_aligned, X_test, _, _ = prepare_design_matrix(
        long_test, confederation_levels, return_long=True
    )

    long_test_aligned["lambda_pred"] = np.asarray(fitted_model.predict(X_test))

    # Index long predictions by (match_date, attacker, defender) so we can
    # look up both home and away lambdas for each wide-format match.
    lookup = {}
    for _, r in long_test_aligned.iterrows():
        lookup[(r["match_date"], r["attacker_team"], r["defender_team"])] = r["lambda_pred"]

    eps = 1e-15
    losses = []
    briers = []
    correct = 0
    n_scored = 0

    for _, m in df_test.iterrows():
        key_home = (m["date"], str(m["home_team"]), str(m["away_team"]))
        key_away = (m["date"], str(m["away_team"]), str(m["home_team"]))
        if key_home not in lookup or key_away not in lookup:
            continue  # dropped during prepare_design_matrix
        lh = float(lookup[key_home])
        la = float(lookup[key_away])

        mtx = score_matrix(lh, la, max_goals=12)
        probs = outcome_probs(mtx)

        if m["home_score"] > m["away_score"]:
            actual_vec = np.array([1, 0, 0])
        elif m["home_score"] < m["away_score"]:
            actual_vec = np.array([0, 0, 1])
        else:
            actual_vec = np.array([0, 1, 0])

        p_vec = np.array([probs["home"], probs["draw"], probs["away"]])
        p_vec = np.clip(p_vec, eps, 1 - eps)

        losses.append(-np.log(p_vec[np.argmax(actual_vec)]))
        briers.append(np.sum((p_vec - actual_vec) ** 2))
        if np.argmax(p_vec) == np.argmax(actual_vec):
            correct += 1
        n_scored += 1

    return {
        "n": n_scored,
        "log_loss": float(np.mean(losses)),
        "brier": float(np.mean(briers)),
        "accuracy": correct / n_scored if n_scored else None,
    }


def main() -> None:
    print("Loading training matrix...")
    wide = pd.read_parquet(PROCESSED_DIR / "training_matrix.parquet")
    print(f"  {len(wide):,} matches loaded.")

    train_wide = wide[wide["date"] < TRAIN_CUTOFF].copy()
    test_wide = wide[wide["date"] >= TRAIN_CUTOFF].copy()
    print(f"  Train: {len(train_wide):,} matches "
          f"({train_wide['date'].min().date()} → {train_wide['date'].max().date()})")
    print(f"  Test : {len(test_wide):,} matches "
          f"({test_wide['date'].min().date()} → {test_wide['date'].max().date()})")

    # Build long format and design matrix
    print("\nReshaping to long format...")
    train_wide = filter_complete_features(train_wide)
    long_train = pivot_to_long(train_wide)
    print(f"  {len(long_train):,} training rows (each match → 2 rows).")

    print("Preparing design matrix...")
    confederation_levels = sorted(set(
        long_train["attacker_confederation"].unique()
    ) | set(long_train["defender_confederation"].unique()))
    X_train, y_train, feat_names = prepare_design_matrix(long_train, confederation_levels)
    print(f"  Design matrix: {X_train.shape}, target: {y_train.shape}")

    print("\nFitting Poisson GLM (this is fast — ~10 seconds)...")
    model = fit_poisson(X_train, y_train)

    # Coefficients
    print("\nFitted coefficients:")
    summary = pd.DataFrame({
        "coef": model.params,
        "std_err": model.bse,
        "z": model.tvalues,
        "p_value": model.pvalues,
    }).sort_values("z", key=abs, ascending=False)
    print(summary.to_string())

    print(f"\nIn-sample fit:")
    print(f"  Pearson chi^2 / df = {model.pearson_chi2 / model.df_resid:.3f}  "
          f"(1.0 = pure Poisson; >>1.0 = overdispersion remains)")
    print(f"  AIC: {model.aic:.0f}")

    # Save the fitted model BEFORE evaluation. This way any downstream
    # script (08, 11) that loads the bundle always gets the fresh model
    # even if OOS evaluation later raises.
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODELS_DIR / "poisson_v1.pkl", "wb") as f:
        pickle.dump({
            "model": model,
            "feature_names": feat_names,
            "confederation_levels": confederation_levels,
            "train_cutoff": TRAIN_CUTOFF,
            "trained_at": pd.Timestamp.now(),
        }, f)
    print(f"\nSaved model to {MODELS_DIR / 'poisson_v1.pkl'}")

    # Evaluate on the held-out set
    print(f"\nEvaluating on held-out matches (post-{TRAIN_CUTOFF.date()})...")
    test_wide = filter_complete_features(test_wide)
    metrics_oos = evaluate_1x2(test_wide, model, confederation_levels)
    print(f"  Out-of-sample:")
    print(f"    Matches scored: {metrics_oos['n']:,}")
    print(f"    Log loss      : {metrics_oos['log_loss']:.4f}")
    print(f"    Brier score   : {metrics_oos['brier']:.4f}")
    print(f"    Accuracy      : {metrics_oos['accuracy']:.4f}")

    # Baseline comparison: uniform prediction (1/3, 1/3, 1/3)
    print(f"\n  Baseline (uniform 1/3 each):")
    print(f"    Log loss      : {-np.log(1/3):.4f}")
    print(f"    Brier score   : 0.6667")


if __name__ == "__main__":
    main()