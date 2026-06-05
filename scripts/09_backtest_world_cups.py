"""
Walk-forward backtest on the last 4 men's World Cups.

For each tournament we:
  1. Filter the training matrix to only matches before the WC's start date
     (no look-ahead).
  2. Refit the Poisson regression on that subset.
  3. Refit the Dixon-Coles rho.
  4. Build team features for the WC's participants as of the WC start.
  5. Predict every WC match using actual match neutrality flags.
  6. Compute log loss, Brier score, and accuracy.

Reports per-WC and pooled metrics + saves all predictions for inspection.

Run from the project root:
    uv run python scripts/09_backtest_world_cups.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

from wc2026.features.team_features import build_team_features
from wc2026.models.poisson import (
    pivot_to_long,
    prepare_design_matrix,
    fit_poisson,
    fit_dixon_coles_rho,
    predict_match_dc,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# Approx start/end dates for each WC (matches in 'FIFA World Cup' tournament in our data)
WORLD_CUPS = [
    ("2010", pd.Timestamp("2010-06-11"), pd.Timestamp("2010-07-11")),
    ("2014", pd.Timestamp("2014-06-12"), pd.Timestamp("2014-07-13")),
    ("2018", pd.Timestamp("2018-06-14"), pd.Timestamp("2018-07-15")),
    ("2022", pd.Timestamp("2022-11-20"), pd.Timestamp("2022-12-18")),
]


def backtest_one_wc(
    wc_name: str,
    wc_start: pd.Timestamp,
    wc_end: pd.Timestamp,
    training_matrix: pd.DataFrame,
    results: pd.DataFrame,
    elo_history: pd.DataFrame,
) -> tuple[dict, pd.DataFrame]:
    """Run walk-forward backtest for one World Cup."""
    print(f"\n========== {wc_name} World Cup ==========")
    snapshot = wc_start - pd.Timedelta(days=1)

    # 1. Slice training matrix to pre-WC matches
    train_wide = training_matrix[training_matrix["date"] <= snapshot].copy()
    print(f"  Training matches: {len(train_wide):,}")

    # 2. Fit Poisson regression
    print(f"  Fitting Poisson model...")
    long_train = pivot_to_long(train_wide)
    confederation_levels = sorted(set(
        long_train["attacker_confederation"].unique()
    ) | set(long_train["defender_confederation"].unique()))
    X_train, y_train, _ = prepare_design_matrix(long_train, confederation_levels)
    model = fit_poisson(X_train, y_train)

    # 3. Fit DC rho
    rho = fit_dixon_coles_rho(model, train_wide, confederation_levels)
    print(f"  Dixon-Coles rho = {rho:+.4f}")

    # 4. Identify WC matches and teams
    wc_matches = results[
        (results["tournament"] == "FIFA World Cup")
        & (results["date"] >= wc_start)
        & (results["date"] <= wc_end)
    ].dropna(subset=["home_score", "away_score"]).reset_index(drop=True)

    wc_teams = sorted(set(wc_matches["home_team"].astype(str))
                      | set(wc_matches["away_team"].astype(str)))
    print(f"  WC matches: {len(wc_matches)}, unique teams: {len(wc_teams)}")

    # 5. Build team features as of snapshot
    team_features = build_team_features(
        teams=wc_teams,
        results=results,
        elo_history=elo_history,
        as_of=snapshot,
    )

    # 6. Predict each WC match
    rows = []
    for _, m in tqdm(wc_matches.iterrows(), total=len(wc_matches), desc="  Predicting"):
        pred = predict_match_dc(
            fitted_model=model,
            team_features=team_features,
            home_team=str(m["home_team"]),
            away_team=str(m["away_team"]),
            rho=rho,
            is_neutral=bool(m["neutral"]),
            is_competitive=True,
            confederation_levels=confederation_levels,
        )
        if m["home_score"] > m["away_score"]:
            actual = "home"
        elif m["home_score"] < m["away_score"]:
            actual = "away"
        else:
            actual = "draw"

        rows.append({
            "wc": wc_name,
            "date": m["date"],
            "home_team": m["home_team"],
            "away_team": m["away_team"],
            "home_score": int(m["home_score"]),
            "away_score": int(m["away_score"]),
            "neutral": bool(m["neutral"]),
            "actual": actual,
            "p_home": pred["probs"]["home"],
            "p_draw": pred["probs"]["draw"],
            "p_away": pred["probs"]["away"],
            "lambda_home": pred["lambda_home"],
            "lambda_away": pred["lambda_away"],
        })

    pred_df = pd.DataFrame(rows)

    # 7. Score
    eps = 1e-15
    pred_df["p_actual"] = np.where(
        pred_df["actual"] == "home", pred_df["p_home"],
        np.where(pred_df["actual"] == "draw", pred_df["p_draw"], pred_df["p_away"])
    )
    pred_df["p_actual"] = pred_df["p_actual"].clip(eps, 1 - eps)
    pred_df["log_loss"] = -np.log(pred_df["p_actual"])

    pred_df["brier"] = (
        (pred_df["p_home"] - (pred_df["actual"] == "home").astype(int)) ** 2
        + (pred_df["p_draw"] - (pred_df["actual"] == "draw").astype(int)) ** 2
        + (pred_df["p_away"] - (pred_df["actual"] == "away").astype(int)) ** 2
    )
    pred_df["predicted"] = pred_df[["p_home", "p_draw", "p_away"]].idxmax(axis=1).map({
        "p_home": "home", "p_draw": "draw", "p_away": "away"
    })
    pred_df["correct"] = (pred_df["predicted"] == pred_df["actual"]).astype(int)

    metrics = {
        "wc": wc_name,
        "n_matches": len(pred_df),
        "log_loss": float(pred_df["log_loss"].mean()),
        "brier": float(pred_df["brier"].mean()),
        "accuracy": float(pred_df["correct"].mean()),
        "rho": rho,
    }
    print(f"  Log loss: {metrics['log_loss']:.4f}")
    print(f"  Brier:    {metrics['brier']:.4f}")
    print(f"  Accuracy: {metrics['accuracy']:.4f}")
    return metrics, pred_df


def main() -> None:
    print("Loading data...")
    results = pd.read_parquet(PROCESSED_DIR / "results.parquet")
    elo_history = pd.read_parquet(PROCESSED_DIR / "elo_history.parquet")
    training_matrix = pd.read_parquet(PROCESSED_DIR / "training_matrix.parquet")
    print(f"  Results: {len(results):,}")
    print(f"  Training matrix: {len(training_matrix):,}")

    all_metrics = []
    all_preds = []
    for wc_name, wc_start, wc_end in WORLD_CUPS:
        metrics, preds = backtest_one_wc(
            wc_name, wc_start, wc_end, training_matrix, results, elo_history
        )
        all_metrics.append(metrics)
        all_preds.append(preds)

    metrics_df = pd.DataFrame(all_metrics)
    preds_df = pd.concat(all_preds, ignore_index=True)

    print("\n" + "=" * 60)
    print("Per-WC metrics:")
    print("=" * 60)
    print(metrics_df.to_string(index=False))

    pooled = {
        "n_matches": len(preds_df),
        "log_loss": float(preds_df["log_loss"].mean()),
        "log_loss_se": float(preds_df["log_loss"].std() / np.sqrt(len(preds_df))),
        "brier": float(preds_df["brier"].mean()),
        "accuracy": float(preds_df["correct"].mean()),
    }
    print("\n" + "=" * 60)
    print("Pooled metrics across all 4 WCs:")
    print("=" * 60)
    for k, v in pooled.items():
        if isinstance(v, float):
            print(f"  {k:15s}: {v:.4f}")
        else:
            print(f"  {k:15s}: {v}")

    # Reference baselines for comparison
    print(f"\n  Reference points:")
    print(f"    Uniform 1/3:         log_loss = {-np.log(1/3):.4f}, brier = {2/3:.4f}")
    print(f"    Naive Elo + softmax: ~1.02 (typical for Elo-only model on WC data)")
    print(f"    Sharp bookmaker:     ~0.94-0.96")

    metrics_df.to_csv(PROCESSED_DIR / "backtest_per_wc.csv", index=False)
    preds_df.to_csv(PROCESSED_DIR / "backtest_predictions.csv", index=False)
    print(f"\nSaved to:")
    print(f"  {PROCESSED_DIR / 'backtest_per_wc.csv'}")
    print(f"  {PROCESSED_DIR / 'backtest_predictions.csv'}")


if __name__ == "__main__":
    main()