#!/usr/bin/env python3
"""
30_backtest_derived_calibration.py  —  gate for the totals/BTTS sleeve (Strategy v2)

The W/D/L surface was validated by the tournament backtest (script 25); the goals
markets (over/under totals, both-teams-to-score) were NEVER scored. This script is
the honest gate from `docs/strategy_v2.md §4`: it scores the model's totals and
BTTS predictions against the out-of-sample World Cup backtest set and decides
whether the derived sleeve is calibrated enough to trade.

It reuses the per-match lambdas already saved by script 09
(`data/processed/backtest_predictions.csv` -> lambda_home, lambda_away,
home_score, away_score) and the model's Dixon-Coles rho, so it does NOT re-run the
model fit. The grid is built exactly as production builds it:
`score_matrix_dc(lambda_home, lambda_away, rho)`.

OUTPUT
  - console: reliability bins (predicted vs realized) + log loss vs base-rate
    baseline for each market, and a PASS/FAIL verdict per market.
  - reports/derived_calibration_<ts>.md   (the same, as a record)
  - data/processed/derived_calibration.json  (machine-readable verdict; the
    pricer / morning.sh can refuse to open the sleeve unless pass == true)

PASS criteria (deliberately conservative):
  - mean log loss strictly below the base-rate baseline, AND
  - mean |predicted - realized| across populated reliability bins <= 0.06.

Run (on the Mac, from repo root):
    uv run python scripts/30_backtest_derived_calibration.py
"""
from __future__ import annotations

import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = REPO_ROOT / "data" / "processed"
PREDS_CSV = PROCESSED / "backtest_predictions.csv"
MODEL_PKL = PROCESSED / "models" / "poisson_v1.pkl"
OUT_JSON = PROCESSED / "derived_calibration.json"
REPORTS = REPO_ROOT / "reports"

TOTAL_LINES = [0.5, 1.5, 2.5, 3.5, 4.5]
MAX_GOALS = 12
BIN_EDGES = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
MAE_BIN_TOL = 0.06   # mean abs (pred - realized) across populated bins


# --- grid (same construction as production) ---------------------------------
def _load_rho() -> float:
    """Read the fitted Dixon-Coles rho from the model pkl. 0.0 if unavailable."""
    try:
        with open(MODEL_PKL, "rb") as fh:
            obj = pickle.load(fh)
        if isinstance(obj, dict):
            for k in ("dc_rho", "rho"):
                if k in obj and obj[k] is not None:
                    return float(obj[k])
        return float(getattr(obj, "dc_rho", 0.0) or 0.0)
    except Exception as e:  # pragma: no cover - Mac-only path
        print(f"  [warn] could not read rho from {MODEL_PKL.name}: {e}; using 0.0")
        return 0.0


def score_grid(lh: float, la: float, rho: float, max_goals: int = MAX_GOALS) -> np.ndarray:
    """Bivariate-Poisson grid with the Dixon-Coles low-score correction.

    Mirrors src/wc2026/models/poisson.score_matrix_dc so this gate matches what
    the pricer will use. Falls back to that implementation if importable.
    """
    try:
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from wc2026.models.poisson import score_matrix_dc  # type: ignore
        return score_matrix_dc(lh, la, rho, max_goals=max_goals)
    except Exception:
        # numpy-only Poisson pmf fallback (no scipy dependency):
        #   pmf(k; lam) = exp(-lam) * lam^k / k!
        k = np.arange(max_goals + 1)
        logfact = np.cumsum(np.concatenate(([0.0], np.log(np.arange(1, max_goals + 1)))))
        ph = np.exp(-lh + k * np.log(max(lh, 1e-12)) - logfact)
        pa = np.exp(-la + k * np.log(max(la, 1e-12)) - logfact)
        g = np.outer(ph, pa)
        if rho != 0.0:
            g[0, 0] *= (1.0 - lh * la * rho)
            g[0, 1] *= (1.0 + lh * rho)
            g[1, 0] *= (1.0 + la * rho)
            g[1, 1] *= (1.0 - rho)
        s = g.sum()
        return g / s if s > 0 else g


def total_over_prob(grid: np.ndarray, line: float) -> float:
    n = grid.shape[0]
    i = np.arange(n)[:, None]
    j = np.arange(n)[None, :]
    return float(grid[(i + j) > line].sum())


def btts_prob(grid: np.ndarray) -> float:
    return float(grid[1:, 1:].sum())


# --- scoring ----------------------------------------------------------------
def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _reliability(p: np.ndarray, y: np.ndarray):
    """Return (rows, mae) where rows = list of (bin_label, n, mean_pred, realized)."""
    rows, abs_errs = [], []
    idx = np.digitize(p, BIN_EDGES[1:-1])
    for b in range(len(BIN_EDGES) - 1):
        mask = idx == b
        n = int(mask.sum())
        if n == 0:
            continue
        mp, rr = float(p[mask].mean()), float(y[mask].mean())
        rows.append((f"({BIN_EDGES[b]:.1f},{BIN_EDGES[b+1]:.1f}]", n, mp, rr))
        abs_errs.append(abs(mp - rr))
    return rows, (float(np.mean(abs_errs)) if abs_errs else 1.0)


def _score_market(name: str, p: np.ndarray, y: np.ndarray) -> dict:
    base = float(y.mean())
    ll = _logloss(p, y)
    ll_base = _logloss(np.full_like(p, base), y)
    rows, mae = _reliability(p, y)
    passed = bool(ll < ll_base and mae <= MAE_BIN_TOL)
    return {"market": name, "n": int(len(y)), "base_rate": round(base, 4),
            "logloss": round(ll, 4), "logloss_baseline": round(ll_base, 4),
            "beats_baseline": bool(ll < ll_base), "bin_mae": round(mae, 4),
            "pass": passed, "reliability": rows}


def main() -> int:
    if not PREDS_CSV.exists():
        sys.exit(f"missing {PREDS_CSV} — run scripts/09_backtest_world_cups.py first.")
    df = pd.read_csv(PREDS_CSV)
    need = {"lambda_home", "lambda_away", "home_score", "away_score"}
    missing = need - set(df.columns)
    if missing:
        sys.exit(f"{PREDS_CSV} missing columns: {missing}")
    df = df.dropna(subset=list(need)).reset_index(drop=True)
    rho = _load_rho()
    print(f"Loaded {len(df)} OOS matches · Dixon-Coles rho = {rho:.4f}\n")

    # Build per-match predicted probs for every derived market.
    grids = [score_grid(float(r.lambda_home), float(r.lambda_away), rho)
             for r in df.itertuples()]
    tot = (df["home_score"] + df["away_score"]).to_numpy()
    both = ((df["home_score"] >= 1) & (df["away_score"] >= 1)).astype(int).to_numpy()

    results = []
    for line in TOTAL_LINES:
        p = np.array([total_over_prob(g, line) for g in grids])
        y = (tot > line).astype(int)
        results.append(_score_market(f"over_{line}", p, y))
    p_btts = np.array([btts_prob(g) for g in grids])
    results.append(_score_market("btts", p_btts, both))

    # --- report -------------------------------------------------------------
    lines_out = [f"# Derived-market calibration gate — {datetime.now(timezone.utc):%Y-%m-%d %H:%MZ}",
                 "",
                 f"OOS matches: **{len(df)}** · Dixon-Coles rho: {rho:.4f} · "
                 f"source: `data/processed/backtest_predictions.csv`",
                 "", "## Verdict", "",
                 "| market | n | base | log loss | baseline | beats? | bin MAE | PASS |",
                 "|---|---|---|---|---|---|---|---|"]
    all_pass = True
    for r in results:
        all_pass &= r["pass"]
        lines_out.append(
            f"| {r['market']} | {r['n']} | {r['base_rate']:.2f} | {r['logloss']:.4f} | "
            f"{r['logloss_baseline']:.4f} | {'yes' if r['beats_baseline'] else 'NO'} | "
            f"{r['bin_mae']:.3f} | {'PASS' if r['pass'] else 'FAIL'} |")
    tradeable = [r["market"] for r in results if r["pass"]]
    blocked = [r["market"] for r in results if not r["pass"]]
    lines_out += ["",
                  f"**Tradeable now (per-market gate): {', '.join(tradeable) if tradeable else 'none'}**",
                  f"**Blocked (do NOT trade): {', '.join(blocked) if blocked else 'none'}**",
                  "",
                  "> The pricer keys off the per-market `pass` flags in "
                  "`derived_calibration.json`, not the all-or-nothing summary. A market "
                  "trades only if it passed here.",
                  "", "## Reliability (predicted vs realized)", ""]
    for r in results:
        lines_out.append(f"### {r['market']}  (n={r['n']})")
        lines_out.append("| pred bin | n | mean pred | realized |")
        lines_out.append("|---|---|---|---|")
        for lab, n, mp, rr in r["reliability"]:
            lines_out.append(f"| {lab} | {n} | {mp:.3f} | {rr:.3f} |")
        lines_out.append("")

    report = "\n".join(lines_out)
    print(report)

    REPORTS.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (REPORTS / f"derived_calibration_{ts}.md").write_text(report)
    OUT_JSON.write_text(json.dumps(
        {"generated_utc": datetime.now(timezone.utc).isoformat(),
         "rho": rho, "n": int(len(df)), "all_pass": bool(all_pass),
         "markets": [{k: v for k, v in r.items() if k != "reliability"} for r in results]},
        indent=2))
    print(f"\nWrote {OUT_JSON} and reports/derived_calibration_{ts}.md")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
