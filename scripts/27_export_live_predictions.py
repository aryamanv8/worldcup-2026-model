"""
Step 0 / script 27: Export frozen-model predictions for the 2026 World Cup.

Purpose
-------
Produce a FIXED, write-once yardstick of the model's pre-match W/D/L prediction
for every actual 2026 World Cup fixture, so that script 28 can later score those
predictions against real results as they come in.

The model is FROZEN for the live-tracking experiment (same bundle, same T=0.77
that the simulator and paper-trading pricer use). These predictions therefore do
not change between re-runs: this script is intended to be run ONCE. Re-running it
will reproduce identical numbers (it refuses to overwrite unless --force is
passed), which is the integrity property we want — the yardstick can't drift to
flatter the results.

Prediction path (identical to simulation/engine.precompute_score_matrices):
    predict_match_dc(home, away, rho)        # DC-corrected joint score matrix
      -> recalibrate_score_matrix(M, T)      # temperature applied on the matrix
      -> outcome_probs(M)                    # collapse to home/draw/away

Home advantage
--------------
We replicate the SIMULATOR's rule, not the results-file's home/away label: a
match is non-neutral ONLY when the nominally-home team is a tournament host
(Mexico / Canada / United States) playing a group match in its own group.
Every other group match is treated as neutral (is_neutral=True), exactly as the
frozen model was calibrated. The home_team column in results.parquet is used
only to decide orientation + which side the host is on, never to grant a generic
home edge the model never applies at neutral sites.

Run from the project root:
    uv run python scripts/27_export_live_predictions.py            # write once
    uv run python scripts/27_export_live_predictions.py --force     # overwrite
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import pandas as pd

from wc2026.data.structure import load_groups
from wc2026.models.poisson import predict_match_dc
from wc2026.simulation.engine import recalibrate_score_matrix, HOST_GROUP

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROCESSED_DIR / "models"
STRUCTURE_PATH = PROJECT_ROOT / "data" / "external" / "wc2026_structure.yaml"
CALIBRATION_PATH = PROCESSED_DIR / "calibration.json"
RESULTS_PATH = PROCESSED_DIR / "results.parquet"
OUT_PATH = PROCESSED_DIR / "live_2026_predictions.parquet"

WC_START = pd.Timestamp("2026-06-11")
WC_GROUP_END = pd.Timestamp("2026-06-27")  # last group-stage date in the schedule


def _is_host_home(home_team: str, away_team: str, groups: dict) -> bool:
    """True iff home_team is a host AND both teams are in that host's group
    (i.e. this is a host group-stage match, the only non-neutral case the
    simulator models)."""
    g = HOST_GROUP.get(home_team)
    if g is None:
        return False
    group_teams = set(groups.get(g, []))
    return home_team in group_teams and away_team in group_teams


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="Overwrite an existing predictions file.")
    ap.add_argument("--end", default=str(WC_GROUP_END.date()),
                    help="Last fixture date to include (YYYY-MM-DD). "
                         "Default = end of group stage; widen later for knockouts.")
    args = ap.parse_args()

    if OUT_PATH.exists() and not args.force:
        raise SystemExit(
            f"{OUT_PATH} already exists. The frozen yardstick should be written "
            f"once. Re-run with --force only if you deliberately want to "
            f"regenerate it (e.g. to extend to knockout fixtures)."
        )

    # --- Load frozen model bundle -------------------------------------------
    with open(MODELS_DIR / "poisson_v1.pkl", "rb") as f:
        bundle = pickle.load(f)
    model = bundle["model"]
    rho = bundle["dc_rho"]
    confederation_levels = bundle["confederation_levels"]

    temperature = 1.0
    if CALIBRATION_PATH.exists():
        temperature = float(json.loads(CALIBRATION_PATH.read_text()).get("temperature", 1.0))
    print(f"[load] frozen model: {len(model.params)} params, rho={rho:+.4f}, T={temperature}")

    team_features = pd.read_parquet(PROCESSED_DIR / "team_features.parquet")
    groups = load_groups(STRUCTURE_PATH)

    # --- Pull the actual fixture list from results.parquet ------------------
    results = pd.read_parquet(RESULTS_PATH)
    results["date"] = pd.to_datetime(results["date"])
    end_date = pd.Timestamp(args.end)
    fixtures = results[(results["date"] >= WC_START) & (results["date"] <= end_date)].copy()
    fixtures = fixtures.sort_values("date").reset_index(drop=True)
    print(f"[fixtures] {len(fixtures)} fixtures from {WC_START.date()} to {end_date.date()}")

    # --- Predict each fixture with the frozen model -------------------------
    rows = []
    for _, fx in fixtures.iterrows():
        home, away = str(fx["home_team"]), str(fx["away_team"])
        host_home = _is_host_home(home, away, groups)
        is_neutral = not host_home

        pred = predict_match_dc(
            fitted_model=model,
            team_features=team_features,
            home_team=home,
            away_team=away,
            rho=rho,
            is_neutral=is_neutral,
            is_competitive=True,
            confederation_levels=confederation_levels,
            max_goals=10,
        )
        # Apply temperature on the matrix, exactly as the simulator does, then
        # re-derive the W/D/L marginals from the recalibrated matrix.
        M = recalibrate_score_matrix(pred["score_matrix"], temperature)
        n = M.shape[0]
        import numpy as np
        p_home = float(np.tril(M, -1).sum())
        p_draw = float(np.trace(M))
        p_away = float(np.triu(M, 1).sum())
        s = p_home + p_draw + p_away
        p_home, p_draw, p_away = p_home / s, p_draw / s, p_away / s

        rows.append({
            "date": fx["date"],
            "home_team": home,
            "away_team": away,
            "is_neutral": is_neutral,
            "p_home": p_home,
            "p_draw": p_draw,
            "p_away": p_away,
            "model_pick": max(
                (("home", p_home), ("draw", p_draw), ("away", p_away)),
                key=lambda kv: kv[1],
            )[0],
        })

    out = pd.DataFrame(rows)
    out.to_parquet(OUT_PATH, index=False)
    print(f"[out] wrote {len(out)} frozen predictions -> {OUT_PATH}")
    print("\nSample (first 8):")
    show = out.head(8).copy()
    for c in ("p_home", "p_draw", "p_away"):
        show[c] = (show[c] * 100).round(1)
    print(show[["date", "home_team", "away_team", "is_neutral",
                "p_home", "p_draw", "p_away", "model_pick"]].to_string(index=False))


if __name__ == "__main__":
    main()