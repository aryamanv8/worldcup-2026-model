"""
20_temperature_recalibration.py

Step 1 of the Stage-1 finish: recalibrate the match model's win/draw/loss
probabilities with a single-parameter temperature.

Why temperature
---------------
The model card (script 19) showed the model is mildly *under*confident: across
Elo-gap buckets it shades matchups toward a coin flip, underrating the stronger
side by ~0.07-0.14 in expected-score terms (E_model < E_real for favorites,
E_model > E_real for underdogs). Underconfidence = probabilities pulled toward
uniform. The textbook one-parameter fix is temperature sharpening:

    p_i' = p_i^(1/T) / sum_j p_j^(1/T)

T < 1 sharpens (pushes favorites up, underdogs down); T > 1 softens. One
parameter => negligible overfitting risk even on 256 matches. We expect T < 1.

Honest evaluation
-----------------
The walk-forward predictions are already out-of-sample, but T is still a fitted
quantity, so we validate it leave-one-World-Cup-out: fit T on three WCs, measure
the change in log loss on the held-out fourth, rotate. The production constant is
then fit on all four. We report (a) per-WC OOS log loss before/after, (b) whether
the four fold-Ts agree (stability => real effect, not noise), and (c) whether the
favorite-underrating in the Elo-gap buckets actually shrinks -- aggregate log
loss improving is necessary but not sufficient; we want the specific bias gone.

Scope
-----
This recalibrates the OUTCOME (W/D/L) probabilities only. Wiring T into the
tournament simulator (which samples scorelines) is a step-2 decision, not handled
here. Output is the calibration constant + recalibrated backtest predictions.

Outputs
-------
  - console : fitted T (per fold + production), log loss / Brier before vs after,
              Elo-gap E_model_before / E_model_after / E_real comparison
  - json    : data/processed/calibration.json   (the production constant)
  - parquet : data/processed/backtest_predictions_recalibrated.parquet

Run
---
  uv run python scripts/20_temperature_recalibration.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
PRED = REPO_ROOT / "data" / "processed" / "backtest_predictions.parquet"
OUT_CAL = REPO_ROOT / "data" / "processed" / "calibration.json"
OUT_RECAL = REPO_ROOT / "data" / "processed" / "backtest_predictions_recalibrated.parquet"

EPS = 1e-12
T_GRID = np.round(np.arange(0.50, 2.001, 0.01), 3)   # transparent grid; refine if needed
GAP_EDGES = [-1e9, -300, -150, -50, 50, 150, 300, 1e9]
GAP_LABELS = ["<-300", "-300..-150", "-150..-50", "-50..50", "50..150", "150..300", ">300"]


def power_scale(P: np.ndarray, T: float) -> np.ndarray:
    Pw = np.clip(P, EPS, 1.0) ** (1.0 / T)
    return Pw / Pw.sum(axis=1, keepdims=True)


def logloss(P: np.ndarray, y: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(P[np.arange(len(P)), y], EPS, 1.0))))


def brier(P: np.ndarray, y: np.ndarray) -> float:
    Y = np.eye(3)[y]
    return float(np.mean(np.sum((P - Y) ** 2, axis=1)))


def fit_T(P: np.ndarray, y: np.ndarray) -> float:
    losses = [logloss(power_scale(P, T), y) for T in T_GRID]
    return float(T_GRID[int(np.argmin(losses))])


def main() -> None:
    if not PRED.exists():
        print(f"[FATAL] {PRED} not found -- run script 09 first.")
        sys.exit(1)

    df = pd.read_parquet(PRED)
    P = df[["p_home_win", "p_draw", "p_away_win"]].to_numpy(dtype=float)
    P = np.clip(P, EPS, 1.0)
    P = P / P.sum(axis=1, keepdims=True)
    y = np.where(df["home_score"] > df["away_score"], 0,
                 np.where(df["home_score"] == df["away_score"], 1, 2))
    wc = df["tournament"].astype(str).to_numpy()
    gap = df["elo_diff"].to_numpy(dtype=float) if "elo_diff" in df.columns else None
    print(f"[load] {len(df)} matches across {len(set(wc))} World Cups")

    # --- leave-one-WC-out validation -----------------------------------------
    print("\n=== Leave-one-WC-out temperature ===")
    print(f"  {'held-out':<10}{'fold T':>8}{'LL before':>11}{'LL after':>10}{'delta':>9}")
    fold_Ts, ll_before_oos, ll_after_oos = [], [], []
    for w in sorted(set(wc)):
        tr, te = wc != w, wc == w
        T = fit_T(P[tr], y[tr])
        b = logloss(P[te], y[te])
        a = logloss(power_scale(P[te], T), y[te])
        fold_Ts.append(T)
        ll_before_oos.append(b * te.sum())
        ll_after_oos.append(a * te.sum())
        print(f"  {w:<10}{T:>8.2f}{b:>11.4f}{a:>10.4f}{a-b:>+9.4f}")

    n = len(df)
    pooled_before = sum(ll_before_oos) / n
    pooled_after = sum(ll_after_oos) / n
    print(f"  {'POOLED':<10}{'':>8}{pooled_before:>11.4f}{pooled_after:>10.4f}"
          f"{pooled_after-pooled_before:>+9.4f}   (honest OOS)")
    print(f"\n  fold Ts: {fold_Ts}  -> spread {max(fold_Ts)-min(fold_Ts):.2f} "
          f"({'stable' if max(fold_Ts)-min(fold_Ts) <= 0.15 else 'UNSTABLE -- effect may be noise'})")

    # --- production constant (fit on all data) --------------------------------
    T_prod = fit_T(P, y)
    Pcal = power_scale(P, T_prod)
    print(f"\n=== Production temperature (fit on all 4 WCs) ===")
    print(f"  T = {T_prod:.2f}   ({'sharpening, as expected' if T_prod < 1 else 'softening'})")
    print(f"  log loss : {logloss(P, y):.4f} -> {logloss(Pcal, y):.4f}")
    print(f"  brier    : {brier(P, y):.4f} -> {brier(Pcal, y):.4f}")

    # --- did the favorite-underrating actually shrink? ------------------------
    if gap is not None:
        em_b = P[:, 0] + 0.5 * P[:, 1]
        em_a = Pcal[:, 0] + 0.5 * Pcal[:, 1]
        er = (y == 0) * 1.0 + (y == 1) * 0.5
        bucket = pd.cut(gap, GAP_EDGES, labels=GAP_LABELS)
        g = pd.DataFrame({"bucket": bucket, "em_b": em_b, "em_a": em_a, "er": er})
        agg = g.groupby("bucket", observed=True).agg(
            n=("er", "size"), E_real=("er", "mean"),
            E_before=("em_b", "mean"), E_after=("em_a", "mean")).reset_index()
        agg["|gap|_before"] = (agg["E_before"] - agg["E_real"]).abs()
        agg["|gap|_after"] = (agg["E_after"] - agg["E_real"]).abs()
        print("\n=== Favorite-bias check: expected score vs reality by Elo gap ===")
        print(f"  {'bucket':<13}{'n':>4}{'E_real':>8}{'E_before':>9}{'E_after':>8}"
              f"{'|err|_b':>9}{'|err|_a':>9}")
        for _, r in agg.iterrows():
            print(f"  {r['bucket']:<13}{int(r['n']):>4}{r['E_real']:>8.3f}"
                  f"{r['E_before']:>9.3f}{r['E_after']:>8.3f}"
                  f"{r['|gap|_before']:>9.3f}{r['|gap|_after']:>9.3f}")
        improved = (agg["|gap|_after"] < agg["|gap|_before"]).sum()
        print(f"  buckets where bias shrank: {improved}/{len(agg)}")

    # --- persist --------------------------------------------------------------
    OUT_CAL.write_text(json.dumps({
        "method": "temperature_power_scaling",
        "formula": "p_i' = p_i**(1/T) / sum_j p_j**(1/T)",
        "temperature": T_prod,
        "fitted_on": "all 4 backtest WCs (2010/14/18/22), 256 matches",
        "loocv_fold_temperatures": dict(zip(sorted(set(wc)), fold_Ts)),
        "loocv_pooled_logloss_before": pooled_before,
        "loocv_pooled_logloss_after": pooled_after,
        "scope": "outcome (W/D/L) probabilities only; simulator wiring is step 2",
    }, indent=2))

    recal = df.copy()
    recal[["p_home_win", "p_draw", "p_away_win"]] = Pcal
    recal.to_parquet(OUT_RECAL, index=False)
    print(f"\n[save] {OUT_CAL}")
    print(f"[save] {OUT_RECAL}")
    print("  To see the recalibrated model card, point script 19's INPUT_PREDICTIONS "
          "at the recalibrated file and rerun.")


if __name__ == "__main__":
    main()