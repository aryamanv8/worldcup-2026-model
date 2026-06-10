"""
12_elo_gap_calibration.py

Step 0 of the hierarchical-Bayesian milestone: establish the EMPIRICAL
expected-score vs Elo-gap curve as the calibration target *before* fitting any
new model.

Why this exists
---------------
Every shrinkage diagnostic so far has measured "model expected score vs Elo
expected score" (Delta = -0.29 on Spain-Austria, etc.). But Elo's expected-score
logistic is itself a model, and it is known to be overconfident at extreme gaps
in international football (sparse fixtures, no relegation pressure, blowout
qualifiers). So "Delta vs Elo" is "Delta vs a possibly-miscalibrated reference."

This script replaces the reference with ground truth: bucket ~25k historical
matches by point-in-time Elo gap and compute the *observed* mean expected score
per bucket, with bootstrap CIs. The resulting curve is the acceptance band the
hierarchical model must reproduce. It also tells us, for free, whether the truth
sits near Elo (0.87) or near the GLM (0.58) on the sentinel matchups -- which
decides what "fixed" even means.

Outputs
-------
  - console : per-bin table (n, empirical E[score] + CI, Elo-implied, GLM) and a
              sentinel readout for the four diagnostic matchups
  - parquet : data/processed/elo_gap_calibration.parquet  (feeds the Step-3 acceptance test)
  - figure  : reports/figures/elo_gap_calibration.png

Run
---
  uv run python scripts/12_elo_gap_calibration.py

NOTE: column-name resolution is best-effort against common schema variants.
If it cannot find a required column it prints the available columns and exits
cleanly -- edit the *_CANDIDATES lists at the top to match your training matrix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------- #
# Config
# ----------------------------------------------------------------------------- #
REPO_ROOT = Path(__file__).resolve().parents[1]
TRAINING_MATRIX = REPO_ROOT / "data" / "processed" / "training_matrix.parquet"
OUT_PARQUET = REPO_ROOT / "data" / "processed" / "elo_gap_calibration.parquet"
OUT_FIGURE = REPO_ROOT / "reports" / "figures" / "elo_gap_calibration.png"

# Binning. Fixed-width signed-gap bins read directly as a saturation curve.
# Quantile bins put almost all mass near gap=0 and leave the tails -- exactly the
# region we care about -- under-resolved, so we use fixed width and let the CIs
# expose tail sparsity honestly.
BIN_WIDTH = 50.0           # Elo points
GAP_LIMIT = 700.0          # gaps beyond +/-this are clipped into the end bins
MIN_RELIABLE_N = 30        # bins below this are flagged, not dropped

# Venue regime. WC knockout/group matches are neutral, so the neutral curve is
# the primary, WC-relevant target. We also draw the all-matches curve to see
# whether home advantage changes the saturation *shape* (it shifts level, not
# usually shape). Set to "all" if neutral matches are too sparse at the tails.
PRIMARY_VENUE = "neutral"  # "neutral" | "all"

# Bootstrap CI for the per-bin mean of a {0, 0.5, 1} variable. We bootstrap the
# mean rather than apply a binomial Wilson interval because the outcome is
# three-valued (win/draw/loss -> 1/0.5/0), not a Bernoulli proportion.
N_BOOT = 2000
CI_ALPHA = 0.05
RNG_SEED = 12

# Sentinel matchups: the consistent diagnostic cases. We store the *Elo-implied*
# expected score (what Elo claims) and back out the implied gap, so we can mark
# exactly where on the curve each sentinel sits without needing live Elo values.
SENTINELS = {
    "Spain vs Austria":       0.87,
    "Argentina vs Austria":   0.85,
    "Mexico vs Bosnia":       0.86,
    "Spain vs Saudi Arabia":  0.96,
}

# Schema resolution. Order = priority. First match wins.
TEAM_I_GOALS_CANDIDATES = ["home_goals", "goals_home", "score_home", "gf", "team_goals", "home_score"]
TEAM_J_GOALS_CANDIDATES = ["away_goals", "goals_away", "score_away", "ga", "opp_goals", "away_score"]
ELO_I_CANDIDATES = ["home_elo", "elo_home", "elo_i", "team_elo", "elo_team"]
ELO_J_CANDIDATES = ["away_elo", "elo_away", "elo_j", "opp_elo", "elo_opponent"]
ELO_DIFF_CANDIDATES = ["elo_diff", "elo_gap", "elo_difference", "d_elo"]
NEUTRAL_CANDIDATES = ["neutral", "is_neutral", "neutral_venue"]
RESULT_CANDIDATES = ["result", "outcome", "score_i"]  # optional precomputed expected score


# ----------------------------------------------------------------------------- #
# Helpers
# ----------------------------------------------------------------------------- #
def resolve(df: pd.DataFrame, candidates: list[str], *, required: bool, label: str) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    if required:
        print(f"\n[FATAL] could not resolve required column for '{label}'.")
        print(f"        tried: {candidates}")
        print(f"        available columns:\n        {sorted(df.columns.tolist())}")
        sys.exit(1)
    return None


def elo_expected(gap: np.ndarray | float) -> np.ndarray | float:
    """Elo expected score for the first team given gap = elo_i - elo_j."""
    return 1.0 / (1.0 + np.power(10.0, -np.asarray(gap, dtype=float) / 400.0))


def gap_from_expected(p: float) -> float:
    """Invert the Elo expected-score logistic: implied gap for a given E[score]."""
    return -400.0 * np.log10(1.0 / p - 1.0)


def bootstrap_ci(values: np.ndarray, n_boot: int, alpha: float, rng: np.random.Generator):
    """Percentile bootstrap CI on the mean of a bounded {0,0.5,1} sample."""
    n = values.size
    if n == 0:
        return np.nan, np.nan
    if n == 1:
        return values[0], values[0]
    idx = rng.integers(0, n, size=(n_boot, n))
    means = values[idx].mean(axis=1)
    lo = np.quantile(means, alpha / 2.0)
    hi = np.quantile(means, 1.0 - alpha / 2.0)
    return float(lo), float(hi)


def expected_score_from_goals(gi: pd.Series, gj: pd.Series) -> np.ndarray:
    s = np.where(gi > gj, 1.0, np.where(gi == gj, 0.5, 0.0))
    return s.astype(float)


# ----------------------------------------------------------------------------- #
# GLM overlay hook
# ----------------------------------------------------------------------------- #
def glm_expected_scores(df: pd.DataFrame) -> np.ndarray | None:
    """
    Optional: return the current Poisson-DC model's expected score
    (P(win) + 0.5 * P(draw)) for each row of `df`, in the same i-vs-j
    orientation as the empirical curve.

    I can't know your predict_match signature from here, so this is an explicit
    hook rather than a guess. Wire it to your real interface, e.g.:

        from wc2026.models.poisson import load_model
        model = load_model(REPO_ROOT / "data" / "processed" / "poisson_v1.pkl")
        out = np.empty(len(df))
        for k, row in enumerate(df.itertuples()):
            M = model.predict_match(...)          # score-probability matrix
            out[k] = M[np.triu_indices_from(M, 1)].sum() + 0.5 * np.trace(M)
        return out

    Return None to skip the overlay (empirical + Elo curves still produced).
    """
    return None


# ----------------------------------------------------------------------------- #
# Main
# ----------------------------------------------------------------------------- #
def main() -> None:
    if not TRAINING_MATRIX.exists():
        print(f"[FATAL] training matrix not found at {TRAINING_MATRIX}")
        sys.exit(1)

    df = pd.read_parquet(TRAINING_MATRIX)
    print(f"[load] {len(df):,} matches from {TRAINING_MATRIX.name}")
    rng = np.random.default_rng(RNG_SEED)

    # --- expected score (i-perspective) ---------------------------------------
    result_col = resolve(df, RESULT_CANDIDATES, required=False, label="precomputed expected score")
    if result_col is not None and df[result_col].dropna().between(0, 1).all():
        score = df[result_col].astype(float).to_numpy()
        print(f"[score] using precomputed expected-score column '{result_col}'")
    else:
        gi = resolve(df, TEAM_I_GOALS_CANDIDATES, required=True, label="team_i goals")
        gj = resolve(df, TEAM_J_GOALS_CANDIDATES, required=True, label="team_j goals")
        score = expected_score_from_goals(df[gi], df[gj])
        print(f"[score] derived from goals: '{gi}' vs '{gj}'")

    # --- Elo gap (i - j) ------------------------------------------------------
    diff_col = resolve(df, ELO_DIFF_CANDIDATES, required=False, label="elo diff")
    if diff_col is not None:
        gap = df[diff_col].astype(float).to_numpy()
        print(f"[gap] using precomputed Elo diff column '{diff_col}'")
    else:
        ei = resolve(df, ELO_I_CANDIDATES, required=True, label="team_i Elo")
        ej = resolve(df, ELO_J_CANDIDATES, required=True, label="team_j Elo")
        gap = (df[ei].astype(float) - df[ej].astype(float)).to_numpy()
        print(f"[gap] computed as '{ei}' - '{ej}'")

    # --- venue ----------------------------------------------------------------
    neutral_col = resolve(df, NEUTRAL_CANDIDATES, required=False, label="neutral flag")
    if neutral_col is not None:
        neutral = df[neutral_col].astype(bool).to_numpy()
    else:
        neutral = np.zeros(len(df), dtype=bool)
        print("[venue] no neutral flag found -> treating all matches as non-neutral; "
              "PRIMARY_VENUE='neutral' will be empty. Set PRIMARY_VENUE='all'.")

    glm = glm_expected_scores(df)
    if glm is not None:
        glm = np.asarray(glm, dtype=float)

    base = pd.DataFrame({"gap": gap, "score": score, "neutral": neutral})
    if glm is not None:
        base["glm"] = glm
    base = base.dropna(subset=["gap", "score"])

    edges = np.arange(-GAP_LIMIT, GAP_LIMIT + BIN_WIDTH, BIN_WIDTH)
    centers = (edges[:-1] + edges[1:]) / 2.0

    def aggregate(frame: pd.DataFrame) -> pd.DataFrame:
        g = np.clip(frame["gap"].to_numpy(), edges[0], edges[-1] - 1e-9)
        idx = np.digitize(g, edges) - 1
        rows = []
        for b in range(len(centers)):
            sel = idx == b
            n = int(sel.sum())
            if n == 0:
                continue
            sv = frame["score"].to_numpy()[sel]
            lo, hi = bootstrap_ci(sv, N_BOOT, CI_ALPHA, rng)
            rows.append({
                "gap_center": centers[b],
                "n": n,
                "emp_mean": float(sv.mean()),
                "ci_lo": lo,
                "ci_hi": hi,
                "elo_implied": float(elo_expected(centers[b])),
                "glm_mean": (float(frame["glm"].to_numpy()[sel].mean())
                             if "glm" in frame.columns else np.nan),
                "reliable": n >= MIN_RELIABLE_N,
            })
        return pd.DataFrame(rows)

    tbl_all = aggregate(base)
    tbl_neutral = aggregate(base[base["neutral"]]) if neutral.any() else pd.DataFrame()
    primary = tbl_neutral if (PRIMARY_VENUE == "neutral" and not tbl_neutral.empty) else tbl_all
    primary_label = "neutral" if primary is tbl_neutral else "all"

    # --- console table --------------------------------------------------------
    pd.set_option("display.max_rows", None)
    print(f"\n=== Empirical expected-score by Elo gap  [{primary_label} venue] ===")
    show = primary.copy()
    for c in ("emp_mean", "ci_lo", "ci_hi", "elo_implied", "glm_mean"):
        show[c] = show[c].round(3)
    print(show.to_string(index=False))

    # --- sentinel readout -----------------------------------------------------
    print("\n=== Sentinel matchups: where Elo's claim lands vs ground truth ===")
    sent_rows = []
    for name, elo_p in SENTINELS.items():
        implied_gap = gap_from_expected(elo_p)
        b = int(np.clip(np.digitize([implied_gap], edges)[0] - 1, 0, len(centers) - 1)) # noqa
        match = primary[np.isclose(primary["gap_center"], centers[b])]
        if match.empty:
            emp, lo, hi, n = (np.nan,) * 3 + (0,)
        else:
            r = match.iloc[0]
            emp, lo, hi, n = r["emp_mean"], r["ci_lo"], r["ci_hi"], int(r["n"])
        print(f"  {name:<24} Elo={elo_p:.2f}  implied gap=+{implied_gap:5.0f}  "
              f"empirical={emp:.3f} [{lo:.3f},{hi:.3f}] (n={n})")
        sent_rows.append({"matchup": name, "elo_implied": elo_p,
                          "implied_gap": implied_gap, "empirical": emp,
                          "ci_lo": lo, "ci_hi": hi, "n": n})
    print("\n  Read: if 'empirical' sits well below Elo, Elo is overconfident and the")
    print("  GLM's shrinkage was partly correct. If it sits near Elo, the GLM is")
    print("  genuinely under-pricing top teams and the hierarchy must reach it.")

    # --- persist --------------------------------------------------------------
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    primary.assign(venue=primary_label).to_parquet(OUT_PARQUET, index=False)
    pd.DataFrame(sent_rows).to_parquet(
        OUT_PARQUET.with_name("elo_gap_calibration_sentinels.parquet"), index=False)
    print(f"\n[save] {OUT_PARQUET}")

    # --- figure ---------------------------------------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(9, 6))
        smooth = np.linspace(edges[0], edges[-1], 400)
        ax.plot(smooth, elo_expected(smooth), color="#444", lw=1.5, label="Elo-implied (logistic)")

        rel = primary[primary["reliable"]]
        ax.plot(rel["gap_center"], rel["emp_mean"], "o-", color="#1b6ca8",
                lw=2, ms=4, label=f"Empirical ({primary_label})")
        ax.fill_between(rel["gap_center"], rel["ci_lo"], rel["ci_hi"],
                        color="#1b6ca8", alpha=0.18)
        unrel = primary[~primary["reliable"]]
        if not unrel.empty:
            ax.plot(unrel["gap_center"], unrel["emp_mean"], "o", color="#1b6ca8",
                    ms=4, mfc="white", label=f"Empirical (n<{MIN_RELIABLE_N})")

        if primary is not tbl_all and not tbl_all.empty:
            ra = tbl_all[tbl_all["reliable"]]
            ax.plot(ra["gap_center"], ra["emp_mean"], "--", color="#9aa0a6",
                    lw=1.2, label="Empirical (all venues)")

        if primary["glm_mean"].notna().any():
            ax.plot(primary["gap_center"], primary["glm_mean"], "s",
                    color="#c0392b", ms=4, label="Current GLM")

        for name, elo_p in SENTINELS.items():
            x = gap_from_expected(elo_p)
            ax.axvline(x, color="#e67e22", ls=":", lw=1, alpha=0.7)
            ax.annotate(name.split(" vs ")[0] + "\u2013" + name.split(" vs ")[1],
                        xy=(x, 0.02), rotation=90, fontsize=7, va="bottom",
                        ha="right", color="#a85b00")

        ax.set_xlabel("Elo gap (team_i - team_j)")
        ax.set_ylabel("Expected score  (win=1, draw=0.5, loss=0)")
        ax.set_title("Calibration target: empirical expected score vs Elo gap")
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left", fontsize=8)
        OUT_FIGURE.parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout()
        fig.savefig(OUT_FIGURE, dpi=140)
        print(f"[save] {OUT_FIGURE}")
    except ImportError:
        print("[skip] matplotlib not available; parquet written, no figure.")


if __name__ == "__main__":
    main()