"""
Step 0 / script 28: Score frozen 2026 predictions against actual results.

Purpose
-------
The re-runnable half of the live-tracking experiment. Reads the FROZEN
predictions written by script 27, reads the CURRENT results.parquet, joins them,
keeps only matches that have actually been played (non-null scores), and reports
how well the frozen model predicted them — at two granularities:

  1. 3-way "top pick" view: did the model's single most-likely outcome
     (home/draw/away) match what happened? (top-pick accuracy, log loss, Brier)

  2. Per-leg (binary) view: treat each match as THREE separate binary
     propositions (home win? / draw? / away win?) — the same resolution as
     individual Kalshi moneyline legs (e.g. "NO Brazil" = the home-win leg
     resolving NO). A match's 3-way top pick can be "wrong" while the specific
     leg that was actually traded resolves correctly (see Brazil/Morocco,
     2026-06-13: top pick "Brazil wins" missed on the 1-1 draw, but the traded
     leg NO-Brazil/"home win = NO" resolved correctly). This view gives 3x the
     data points per match and matches how the model's edges are actually used.

This is the script to re-run every few days. The loop is:
    uv run python scripts/01_fetch_results.py            # refresh results from upstream
    uv run python scripts/28_score_live_predictions.py   # re-score

Outputs
-------
1. A per-match table (3-way view): model probabilities vs actual outcome, hit/miss.
2. Headline 3-way running scores: n matches, top-pick accuracy, mean log loss,
   mean Brier (multiclass), plus naive baselines for context.
3. A per-leg table (binary view): one row per home/draw/away proposition, with
   the model's probability, whether it realized, and the binary log loss.
4. Pooled binary log loss / Brier across all legs.
5. A dated snapshot row appended to live_2026_scorecard_log.csv covering both
   views, so the evolution of accuracy over time is preserved across re-runs.

Notes / caveats
---------------
- Small-n warning: in the first days only a handful of matches are scored, so
  ALL headline numbers (3-way and per-leg) are noisy. The log lets you watch
  them stabilize as the group stage fills in.
- The "base-rate baseline" (3-way view) is computed FROM the same played set,
  so it is somewhat circular at small n — it knows the empirical H/D/A split of
  exactly the matches being scored. Treat it as a loose sanity check, not a
  fair external baseline, until n is large.
- Group-stage matches can legitimately draw; full-time score = the outcome. (No
  regulation-vs-shootout subtlety until knockouts, which this tool doesn't cover
  yet.)
- A match is "played" iff both score columns are non-null in results.parquet.

Run from the project root:
    uv run python scripts/28_score_live_predictions.py
    uv run python scripts/28_score_live_predictions.py --no-log   # skip appending snapshot
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PRED_PATH = PROCESSED_DIR / "live_2026_predictions.parquet"
RESULTS_PATH = PROCESSED_DIR / "results.parquet"
LOG_PATH = PROCESSED_DIR / "live_2026_scorecard_log.csv"

EPS = 1e-15


def _actual_outcome(home_score: float, away_score: float) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true",
                    help="Do not append a snapshot row to the scorecard log.")
    args = ap.parse_args()

    if not PRED_PATH.exists():
        raise SystemExit(
            f"{PRED_PATH} not found. Run script 27 first to write the frozen "
            f"predictions yardstick."
        )

    preds = pd.read_parquet(PRED_PATH)
    preds["date"] = pd.to_datetime(preds["date"])

    results = pd.read_parquet(RESULTS_PATH)
    results["date"] = pd.to_datetime(results["date"])

    # Join on (date, home_team, away_team) — the fixtures came FROM results, so
    # this key is exact and 1:1.
    merged = preds.merge(
        results[["date", "home_team", "away_team", "home_score", "away_score"]],
        on=["date", "home_team", "away_team"],
        how="left",
    )

    played = merged[merged["home_score"].notna() & merged["away_score"].notna()].copy()
    n_total = len(merged)
    n_played = len(played)

    print("=" * 78)
    print(f"  LIVE 2026 SCORECARD  —  {n_played} of {n_total} fixtures played")
    print("=" * 78)

    if n_played == 0:
        print("\nNo played matches yet (scores still null in results.parquet).")
        print("Re-run scripts/01_fetch_results.py to refresh, then re-run this.")
        return

    # --- 3-way ("top pick") view --------------------------------------------
    played["actual"] = [
        _actual_outcome(h, a)
        for h, a in zip(played["home_score"], played["away_score"])
    ]
    p_actual = np.where(
        played["actual"] == "home", played["p_home"],
        np.where(played["actual"] == "draw", played["p_draw"], played["p_away"]),
    )
    played["p_assigned_to_actual"] = p_actual
    played["logloss"] = -np.log(np.clip(p_actual, EPS, 1.0))
    onehot = np.vstack([
        (played["actual"] == "home").astype(float),
        (played["actual"] == "draw").astype(float),
        (played["actual"] == "away").astype(float),
    ]).T
    P = played[["p_home", "p_draw", "p_away"]].to_numpy()
    played["brier"] = ((P - onehot) ** 2).sum(axis=1)
    played["hit"] = (played["model_pick"] == played["actual"])

    show = played.sort_values("date").copy()
    print("\n3-WAY VIEW — model's top pick vs actual outcome\n")
    header = (f"{'date':<11} {'home':<22} {'away':<22} "
              f"{'pH':>5} {'pD':>5} {'pA':>5} {'score':>7} {'act':>5} {'pick':>5} {'hit':>4}")
    print(header)
    print("-" * len(header))
    for _, r in show.iterrows():
        score = f"{int(r['home_score'])}-{int(r['away_score'])}"
        print(f"{r['date'].date()!s:<11} {r['home_team']:<22} {r['away_team']:<22} "
              f"{r['p_home']*100:>5.1f} {r['p_draw']*100:>5.1f} {r['p_away']*100:>5.1f} "
              f"{score:>7} {r['actual']:>5} {r['model_pick']:>5} "
              f"{'Y' if r['hit'] else '.':>4}")

    acc = float(played["hit"].mean())
    mean_ll = float(played["logloss"].mean())
    mean_brier = float(played["brier"].mean())
    flat_ll = float(-np.log(1.0 / 3.0))
    base = onehot.mean(axis=0)
    base_ll = float(np.mean([
        -np.log(max(base[{"home": 0, "draw": 1, "away": 2}[o]], EPS))
        for o in played["actual"]
    ]))

    print("\n" + "=" * 78)
    print("  3-WAY RUNNING SCORES")
    print("=" * 78)
    print(f"  matches scored        : {n_played}")
    print(f"  top-pick accuracy     : {acc*100:5.1f}%   "
          f"({int(played['hit'].sum())}/{n_played})")
    print(f"  mean log loss         : {mean_ll:.4f}")
    print(f"     vs flat 1/3 baseline : {flat_ll:.4f}")
    print(f"     vs base-rate baseline: {base_ll:.4f}  (circular at small n — loose sanity check only)")
    print(f"  mean Brier (multiclass): {mean_brier:.4f}")
    if n_played < 10:
        print("\n  [!] n < 10 — these numbers are noisy; treat as provisional.")
    print("\n  Reference (historical OOS, script 06/20): pooled WC log loss ~0.967.")

    # --- Per-leg (binary) view -----------------------------------------------
    leg_rows = []
    for _, r in played.iterrows():
        for leg, p in (("home", r["p_home"]), ("draw", r["p_draw"]), ("away", r["p_away"])):
            realized = 1 if r["actual"] == leg else 0
            pc = float(np.clip(p, EPS, 1 - EPS))
            ll = -np.log(pc) if realized else -np.log(1 - pc)
            leg_rows.append({
                "date": r["date"], "home_team": r["home_team"], "away_team": r["away_team"],
                "leg": leg, "model_p": p, "realized": realized, "logloss": ll,
                "brier": (p - realized) ** 2,
            })
    legs = pd.DataFrame(leg_rows)

    print("\n" + "=" * 78)
    print("  PER-LEG (BINARY) VIEW  —  one row per home/draw/away proposition")
    print("=" * 78)
    print("  Same resolution as individual Kalshi moneyline legs (e.g. 'NO Brazil'")
    print("  = the 'home' leg resolving NO). A match's 3-way top pick can be wrong")
    print("  while the specific traded leg is still right — see Brazil/Morocco below.\n")
    lheader = (f"{'date':<11} {'home':<14} {'away':<14} {'leg':<5} "
               f"{'model p':>8} {'realized':>9} {'logloss':>8}")
    print(lheader)
    print("-" * len(lheader))
    for _, r in legs.sort_values(["date", "leg"]).iterrows():
        print(f"{r['date'].date()!s:<11} {r['home_team']:<14} {r['away_team']:<14} "
              f"{r['leg']:<5} {r['model_p']*100:>7.1f}% {r['realized']:>9} {r['logloss']:>8.3f}")

    leg_ll = float(legs["logloss"].mean())
    leg_brier = float(legs["brier"].mean())
    print(f"\n  pooled binary log loss : {leg_ll:.4f}  (n_legs={len(legs)})")
    print(f"  pooled binary Brier    : {leg_brier:.4f}")
    if len(legs) < 30:
        print("\n  [!] n_legs < 30 — still noisy, but converges faster than the 3-way view.")

    # --- Append dated snapshot to the log ------------------------------------
    if not args.no_log:
        snap = pd.DataFrame([{
            "run_date": pd.Timestamp.now().normalize().date(),
            "n_scored": n_played,
            "n_total": n_total,
            "top_pick_acc": round(acc, 4),
            "mean_logloss": round(mean_ll, 4),
            "mean_brier": round(mean_brier, 4),
            "flat_baseline_ll": round(flat_ll, 4),
            "baserate_baseline_ll": round(base_ll, 4),
            "n_legs": len(legs),
            "binary_logloss": round(leg_ll, 4),
            "binary_brier": round(leg_brier, 4),
        }])
        if LOG_PATH.exists():
            prior = pd.read_csv(LOG_PATH)
            prior = prior[prior["run_date"] != str(snap["run_date"].iloc[0])]
            snap = pd.concat([prior, snap], ignore_index=True)
        snap.to_csv(LOG_PATH, index=False)
        print(f"\n[log] appended snapshot for {snap['run_date'].iloc[-1]} -> {LOG_PATH}")
        print("      (re-running on the same day overwrites that day's row)")


if __name__ == "__main__":
    main()