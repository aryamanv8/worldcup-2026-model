"""
19_model_card.py

Stage-1 closer: stratified calibration analysis ("model card") computed from the
walk-forward backtest's held-out predictions.

Why this exists
---------------
Step 0 (script 18) showed the model is roughly calibrated where we feared
shrinkage -- Elo was the bad yardstick, not the model. This script does the
proper test: compare the model's PROBABILITIES to REALIZED outcomes across the
2010/14/18/22 backtests, stratified by the contexts that matter for Stage-2
inefficiency detection (Elo gap, matchup tier, stage, confederation pairing).

Calibration is weighted above raw log loss here, per the Stage-2 strategy: the
deliverable is a documented "reliable zone" -- where the model can be used as a
fair-value reference and where it can't.

Input
-----
A predictions table at INPUT_PREDICTIONS (parquet). One row per held-out backtest
match. Required columns (names auto-resolved against common variants):
  - predicted probs: p_home_win, p_draw, p_away_win   (must sum ~1)
  - outcome: either an 'outcome' col in {H,D,A}, OR home_score & away_score
Recommended for stratification (skipped individually if absent):
  - elo_diff   (home_elo - away_elo)   OR   home_elo & away_elo
  - home_conf, away_conf               (confederation codes)
  - stage / round / is_knockout
  - tournament / year                  (which WC)

If your backtest doesn't persist this yet, see the docstring at the bottom for a
drop-in snippet for scripts/09_backtest_world_cups.py.

Outputs
-------
  - console : overall metrics (with a log-loss sanity check vs the known 0.973),
              per-stratum calibration table, reliable-zone verdict
  - json    : data/processed/model_card.json          (Stage-2 reads this)
  - parquet : data/processed/model_card_strata.parquet
  - figure  : reports/figures/model_card_reliability.png

Run
---
  uv run python scripts/19_model_card.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------- #
# Config
# ----------------------------------------------------------------------------- #
REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_PREDICTIONS = REPO_ROOT / "data" / "processed" / "backtest_predictions.parquet"
STEP0_CURVE = REPO_ROOT / "data" / "processed" / "elo_gap_calibration.parquet"  # optional overlay
OUT_JSON = REPO_ROOT / "data" / "processed" / "model_card.json"
OUT_STRATA = REPO_ROOT / "data" / "processed" / "model_card_strata.parquet"
OUT_FIGURE = REPO_ROOT / "reports" / "figures" / "model_card_reliability.png"

EXPECTED_LOGLOSS = 0.973     # sanity anchor: computed overall LL should land near this
LL_TOLERANCE = 0.03          # if |computed - expected| exceeds this, warn loudly

N_RELIABILITY_BINS = 5       # quantile bins per class; small because backtest n is ~256
MIN_BIN_N = 8                # reliability points below this are drawn hollow / flagged
MIN_STRATUM_N = 15           # strata below this are reported as indicative-only
ECE_GOOD = 0.05              # per-class ECE under this => "calibrated" in that stratum
N_BOOT = 2000
CI_ALPHA = 0.05
RNG_SEED = 19

# Tier thresholds defined by Elo *percentile within the eval set* (scale-agnostic).
TOP_Q, MID_LOW_Q = 0.75, 0.25   # top = top 25%, mid = middle 50%, low = bottom 25%

EPS = 1e-12
CLASSES = ["H", "D", "A"]       # home win, draw, away win

# Schema resolution
PHW = ["p_home_win", "phw", "p_h", "home_win_prob", "prob_home_win"]
PD_ = ["p_draw", "pd", "p_d", "draw_prob", "prob_draw"]
PAW = ["p_away_win", "paw", "p_a", "away_win_prob", "prob_away_win"]
OUTCOME = ["outcome", "result", "ftr"]
HG = ["home_score", "home_goals", "goals_home", "score_home"]
AG = ["away_score", "away_goals", "goals_away", "score_away"]
ELO_DIFF = ["elo_diff", "elo_gap", "d_elo"]
ELO_H = ["home_elo", "elo_home", "elo_i"]
ELO_A = ["away_elo", "elo_away", "elo_j"]
CONF_H = ["home_conf", "conf_home", "home_confederation"]
CONF_A = ["away_conf", "conf_away", "away_confederation"]
STAGE = ["stage", "round", "phase"]
KNOCKOUT = ["is_knockout", "knockout"]
TOURN = ["tournament", "year", "wc_year", "edition"]


# ----------------------------------------------------------------------------- #
# Helpers
# ----------------------------------------------------------------------------- #
def resolve(df, candidates, required=True, label=""):
    for c in candidates:
        if c in df.columns:
            return c
    if required:
        print(f"\n[FATAL] could not resolve required column for '{label}'. tried: {candidates}")
        print(f"        available:\n        {sorted(df.columns.tolist())}")
        sys.exit(1)
    return None


def multiclass_logloss(P, y_idx):
    p = np.clip(P[np.arange(len(P)), y_idx], EPS, 1.0)
    return float(-np.mean(np.log(p)))


def multiclass_brier(P, Y):
    return float(np.mean(np.sum((P - Y) ** 2, axis=1)))


def boot_mean_ci(x, rng):
    if len(x) == 0:
        return np.nan, np.nan
    if len(x) == 1:
        return float(x[0]), float(x[0])
    idx = rng.integers(0, len(x), size=(N_BOOT, len(x)))
    m = x[idx].mean(axis=1)
    return float(np.quantile(m, CI_ALPHA / 2)), float(np.quantile(m, 1 - CI_ALPHA / 2))


def reliability_points(prob, hit, rng, n_bins=N_RELIABILITY_BINS):
    """Quantile-binned reliability for one class: mean predicted vs observed freq."""
    if len(prob) < n_bins:
        n_bins = max(1, len(prob))
    edges = np.unique(np.quantile(prob, np.linspace(0, 1, n_bins + 1)))
    if len(edges) < 2:
        edges = np.array([prob.min(), prob.max() + EPS])
    idx = np.clip(np.digitize(prob, edges[1:-1]), 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        sel = idx == b
        n = int(sel.sum())
        if n == 0:
            continue
        obs = hit[sel].mean()
        lo, hi = boot_mean_ci(hit[sel].astype(float), rng)
        rows.append({"pred": float(prob[sel].mean()), "obs": float(obs),
                     "ci_lo": lo, "ci_hi": hi, "n": n})
    return pd.DataFrame(rows)


def ece_per_class(prob, hit, n_bins=N_RELIABILITY_BINS):
    pts = reliability_points(prob, hit, np.random.default_rng(0), n_bins)
    if pts.empty:
        return np.nan
    w = pts["n"] / pts["n"].sum()
    return float((w * (pts["pred"] - pts["obs"]).abs()).sum())


# ----------------------------------------------------------------------------- #
# Load + assemble
# ----------------------------------------------------------------------------- #
def main():
    if not INPUT_PREDICTIONS.exists():
        print(f"[FATAL] predictions table not found at {INPUT_PREDICTIONS}")
        print("        Generate it from your backtest -- see snippet at bottom of this file.")
        sys.exit(1)

    df = pd.read_parquet(INPUT_PREDICTIONS).reset_index(drop=True)
    print(f"[load] {len(df):,} held-out backtest matches")
    rng = np.random.default_rng(RNG_SEED)

    phw = resolve(df, PHW, required=True, label="P(home win)")
    pdr = resolve(df, PD_, required=True, label="P(draw)")
    paw = resolve(df, PAW, required=True, label="P(away win)")
    P = df[[phw, pdr, paw]].to_numpy(dtype=float)
    rowsum = P.sum(axis=1)
    if np.abs(rowsum - 1).max() > 1e-3:
        print(f"[warn] prob rows don't sum to 1 (max dev {np.abs(rowsum-1).max():.3f}); renormalizing")
        P = P / rowsum[:, None]

    # realized outcome -> index into CLASSES
    oc = resolve(df, OUTCOME, required=False, label="outcome")
    if oc is not None:
        y = df[oc].astype(str).str.upper().str[0].map({"H": 0, "D": 1, "A": 2})
        if y.isna().any():
            print(f"[FATAL] outcome col '{oc}' has unmapped values: {df[oc].unique()[:10]}")
            sys.exit(1)
        y_idx = y.to_numpy()
    else:
        hg = resolve(df, HG, required=True, label="home goals")
        ag = resolve(df, AG, required=True, label="away goals")
        y_idx = np.where(df[hg] > df[ag], 0, np.where(df[hg] == df[ag], 1, 2))
    Y = np.eye(3)[y_idx]

    # --- overall metrics + sanity check ---------------------------------------
    ll = multiclass_logloss(P, y_idx)
    br = multiclass_brier(P, Y)
    print("\n=== Overall (held-out backtest) ===")
    print(f"  matches    : {len(df)}")
    print(f"  log loss   : {ll:.3f}   (expected ~{EXPECTED_LOGLOSS}; "
          f"{'OK' if abs(ll-EXPECTED_LOGLOSS) <= LL_TOLERANCE else 'MISMATCH -> wrong/misaligned table?'})")
    print(f"  brier      : {br:.3f}")
    for k, name in enumerate(["home win", "draw", "away win"]):
        print(f"  ECE {name:<9}: {ece_per_class(P[:, k], Y[:, k]):.3f}")

    # --- stratifiers ----------------------------------------------------------
    strat = {}

    dcol = resolve(df, ELO_DIFF, required=False, label="elo diff")
    if dcol is None:
        eh, ea = resolve(df, ELO_H, False, "home elo"), resolve(df, ELO_A, False, "away elo")
        gap = (df[eh] - df[ea]).to_numpy() if (eh and ea) else None
    else:
        gap = df[dcol].to_numpy(dtype=float)
    if gap is not None:
        edges = [-1e9, -300, -150, -50, 50, 150, 300, 1e9]
        labels = ["<-300", "-300..-150", "-150..-50", "-50..50", "50..150", "150..300", ">300"]
        strat["elo_gap"] = pd.cut(gap, edges, labels=labels)

        # tier matchup type via Elo percentile within eval set
        eh = resolve(df, ELO_H, False, "home elo")
        ea = resolve(df, ELO_A, False, "away elo")
        if eh and ea:
            allelo = pd.concat([df[eh], df[ea]])
            hi_t, lo_t = allelo.quantile(TOP_Q), allelo.quantile(MID_LOW_Q)
            def tier(x): return "top" if x >= hi_t else ("low" if x < lo_t else "mid")
            th, ta = df[eh].map(tier), df[ea].map(tier)
            pair = [frozenset((a, b)) for a, b in zip(th, ta)]
            namemap = {frozenset(("top", "top")): "top-top", frozenset(("top", "mid")): "top-mid",
                       frozenset(("top", "low")): "top-low", frozenset(("mid", "mid")): "mid-mid",
                       frozenset(("mid", "low")): "mid-low", frozenset(("low", "low")): "low-low",
                       frozenset(("top",)): "top-top", frozenset(("mid",)): "mid-mid",
                       frozenset(("low",)): "low-low"}
            strat["matchup_tier"] = pd.Series([namemap.get(p, "other") for p in pair])

    ch, ca = resolve(df, CONF_H, False, "home conf"), resolve(df, CONF_A, False, "away conf")
    if ch and ca:
        def confpair(a, b):
            s = {str(a).upper(), str(b).upper()}
            if s == {"UEFA"}:
                return "intra-UEFA"
            if "UEFA" in s:
                return "UEFA-vs-other"
            return "other-vs-other"
        strat["conf_pairing"] = pd.Series([confpair(a, b) for a, b in zip(df[ch], df[ca])])

    kcol = resolve(df, KNOCKOUT, False, "knockout flag")
    scol = resolve(df, STAGE, False, "stage")
    if kcol is not None:
        strat["stage"] = df[kcol].map(lambda v: "knockout" if bool(v) else "group")
    elif scol is not None:
        ko = df[scol].astype(str).str.lower().str.contains("final|round|knock|16|quarter|semi|third")
        strat["stage"] = np.where(ko, "knockout", "group")

    tcol = resolve(df, TOURN, False, "tournament")
    if tcol is not None:
        strat["tournament"] = df[tcol].astype(str)

    # --- per-stratum table ----------------------------------------------------
    exp_model = P[:, 0] + 0.5 * P[:, 1]                 # model expected score, home side
    exp_real = (y_idx == 0) * 1.0 + (y_idx == 1) * 0.5  # realized expected score
    strata_rows = []
    print("\n=== Stratified calibration ===")
    for sname, labels_series in strat.items():
        s = pd.Series(labels_series).astype("object").fillna("NA").to_numpy()
        print(f"\n--- by {sname} ---")
        print(f"  {'group':<16}{'n':>5}{'logloss':>9}{'brier':>8}"
              f"{'ECE_max':>9}{'E_model':>9}{'E_real':>8}")
        for g in pd.unique(s):
            sel = s == g
            n = int(sel.sum())
            if n == 0:
                continue
            llg = multiclass_logloss(P[sel], y_idx[sel])
            brg = multiclass_brier(P[sel], Y[sel])
            ece = max(ece_per_class(P[sel, k], Y[sel, k]) for k in range(3))
            em, er = exp_model[sel].mean(), exp_real[sel].mean()
            flag = "" if n >= MIN_STRATUM_N else "  (low-n)"
            print(f"  {str(g):<16}{n:>5}{llg:>9.3f}{brg:>8.3f}{ece:>9.3f}"
                  f"{em:>9.3f}{er:>8.3f}{flag}")
            strata_rows.append({"stratifier": sname, "group": str(g), "n": n,
                                "log_loss": llg, "brier": brg, "ece_max": ece,
                                "exp_model": float(em), "exp_real": float(er),
                                "reliable": bool(n >= MIN_STRATUM_N and ece <= ECE_GOOD)})

    strata_df = pd.DataFrame(strata_rows)

    # --- reliable-zone verdict ------------------------------------------------
    print("\n=== Reliable-zone verdict (Stage-2 reference) ===")
    if not strata_df.empty:
        good = strata_df[strata_df["reliable"]]
        bad = strata_df[(~strata_df["reliable"]) & (strata_df["n"] >= MIN_STRATUM_N)]
        print(f"  reliable strata (ECE<={ECE_GOOD}, n>={MIN_STRATUM_N}): {len(good)}")
        if not bad.empty:
            print("  WATCH (well-sampled but ECE high) -- usable only with caution:")
            for _, r in bad.sort_values("ece_max", ascending=False).iterrows():
                print(f"    {r['stratifier']}={r['group']:<14} ECE={r['ece_max']:.3f} "
                      f"E_model={r['exp_model']:.3f} vs E_real={r['exp_real']:.3f} (n={r['n']})")
        else:
            print("  No well-sampled stratum exceeds the ECE threshold -> "
                  "model is usable as a fair-value reference across observed contexts.")

    # --- persist --------------------------------------------------------------
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    card = {
        "n_matches": int(len(df)),
        "overall": {"log_loss": ll, "brier": br,
                    "ece": {c: ece_per_class(P[:, k], Y[:, k]) for k, c in enumerate(CLASSES)}},
        "thresholds": {"ece_good": ECE_GOOD, "min_stratum_n": MIN_STRATUM_N},
        "strata": strata_rows,
    }
    OUT_JSON.write_text(json.dumps(card, indent=2))
    strata_df.to_parquet(OUT_STRATA, index=False)
    print(f"\n[save] {OUT_JSON}")
    print(f"[save] {OUT_STRATA}")

    # --- figure ---------------------------------------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(2, 2, figsize=(11, 9))
        for k, (a, name) in enumerate(zip(ax.flat[:3], ["Home win", "Draw", "Away win"])):
            pts = reliability_points(P[:, k], Y[:, k], rng)
            a.plot([0, 1], [0, 1], "--", color="#999", lw=1)
            rel = pts[pts["n"] >= MIN_BIN_N]
            unrel = pts[pts["n"] < MIN_BIN_N]
            a.errorbar(rel["pred"], rel["obs"],
                       yerr=[rel["obs"] - rel["ci_lo"], rel["ci_hi"] - rel["obs"]],
                       fmt="o-", color="#1b6ca8", capsize=2, lw=1.5)
            if not unrel.empty:
                a.plot(unrel["pred"], unrel["obs"], "o", mfc="white", color="#1b6ca8")
            a.set_title(f"{name}  (ECE={ece_per_class(P[:, k], Y[:, k]):.3f})")
            a.set_xlabel("predicted"); a.set_ylabel("observed")
            a.set_xlim(0, 1); a.set_ylim(0, 1); a.grid(alpha=0.25)

        # 4th panel: expected score vs Elo gap -- model vs realized vs Step-0 empirical
        a = ax.flat[3]
        if gap is not None:
            order = np.argsort(gap)
            a.plot(gap[order], (1 / (1 + 10 ** (-gap[order] / 400))), color="#444",
                   lw=1.2, label="Elo-implied")
            bins = np.arange(-700, 750, 100)
            cen = (bins[:-1] + bins[1:]) / 2
            gi = np.clip(np.digitize(gap, bins) - 1, 0, len(cen) - 1)
            mm = [exp_model[gi == b].mean() if (gi == b).any() else np.nan for b in range(len(cen))]
            rr = [exp_real[gi == b].mean() if (gi == b).any() else np.nan for b in range(len(cen))]
            a.plot(cen, mm, "s-", color="#c0392b", label="model")
            a.plot(cen, rr, "o", color="#1b6ca8", label="realized (backtest)")
            if STEP0_CURVE.exists():
                c0 = pd.read_parquet(STEP0_CURVE)
                c0 = c0[c0.get("reliable", True)]
                a.plot(c0["gap_center"], c0["emp_mean"], color="#27ae60", lw=1.2,
                       label="empirical (Step 0, big-n)")
            a.set_xlabel("Elo gap (home - away)"); a.set_ylabel("expected score")
            a.set_ylim(0, 1); a.grid(alpha=0.25); a.legend(fontsize=7)
            a.set_title("Saturation: model vs reality")
        fig.suptitle("Model card: reliability on held-out World Cup backtests", y=1.0)
        OUT_FIGURE.parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout()
        fig.savefig(OUT_FIGURE, dpi=140)
        print(f"[save] {OUT_FIGURE}")
    except ImportError:
        print("[skip] matplotlib unavailable; json/parquet written, no figure.")


if __name__ == "__main__":
    main()


# ============================================================================= #
# Drop-in for scripts/09_backtest_world_cups.py if you don't persist predictions
# ============================================================================= #
# Inside the walk-forward loop, wherever you already compute per-match probs for
# log loss, append a record per match and write once at the end:
#
#   records = []
#   for match in heldout_matches:
#       P = model.predict_match(...)               # score-prob matrix or (pH,pD,pA)
#       pH, pD, pA = collapse_to_outcome_probs(P)  # whatever you already do
#       records.append({
#           "tournament": wc_year,
#           "home_team": match.home, "away_team": match.away,
#           "p_home_win": pH, "p_draw": pD, "p_away_win": pA,
#           "home_score": match.home_goals, "away_score": match.away_goals,
#           "elo_diff": match.home_elo - match.away_elo,
#           "home_elo": match.home_elo, "away_elo": match.away_elo,
#           "home_conf": match.home_conf, "away_conf": match.away_conf,
#           "stage": match.stage,                  # e.g. "group" / "round_of_16" / ...
#       })
#   import pandas as pd
#   pd.DataFrame(records).to_parquet("data/processed/backtest_predictions.parquet", index=False)