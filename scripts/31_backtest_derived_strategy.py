#!/usr/bin/env python3
"""
31_backtest_derived_strategy.py  —  P&L backtest of the goals sleeve (Strategy v2)

The sibling of scripts/29_backtest_trading_strategy.py, but for the TOTALS / BTTS
sleeve and with the v2 market-blend correction baked in. Script 30 answered "is the
model's goals probability calibrated?"; this answers the harder question:
"would the corrected goals strategy — edge gate, quarter-Kelly, fees — actually have
MADE MONEY against real historical prices?"

METHOD (mirrors script 29 so results are comparable)
  - Model side: per-match grids from the lambdas in
    data/processed/backtest_predictions.csv (same source script 30 used), giving
    P(over 1.5) and P(BTTS) for the 2018/2022 WC group games.
  - Market side: historical WC CLOSING totals/BTTS odds you provide at
    data/raw/wc_goals_odds.csv (pull from the SAME source as wc_closing_odds.csv —
    BetExplorer average-final — so the two backtests are comparable).
  - Only lines that PASSED scripts/30 trade (over_1.5, btts by default; over_2.5 is
    blocked). Every edge is computed on the CORRECTED fair value (model blended
    toward the de-vigged market), never the raw model.
  - Settle each bet on the realized score; quarter-Kelly sizing, Kalshi fee model.

It reuses 30's grid + lib_correction so the math matches the live pricer exactly.
Runs in a plain numpy env (no model fit needed). `--selftest` fabricates synthetic
odds and checks the harness end-to-end.

ODDS FILE SCHEMA (data/raw/wc_goals_odds.csv) — decimal odds:
    date,home_team,away_team,over15,under15,btts_yes,btts_no
    2018-06-14,Russia,Saudi Arabia,1.13,5.50,2.10,1.72
  (over25/under25 columns are accepted but only traded with --include-blocked.)

Run (on the Mac, from repo root):
    uv run python scripts/31_backtest_derived_strategy.py
    uv run python scripts/31_backtest_derived_strategy.py --with-vig      # stricter
    uv run python scripts/31_backtest_derived_strategy.py --selftest      # synthetic
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = REPO_ROOT / "data" / "processed"
PREDS_CSV = PROCESSED / "backtest_predictions.csv"
GATE_JSON = PROCESSED / "derived_calibration.json"
DEFAULT_ODDS = REPO_ROOT / "data" / "raw" / "wc_goals_odds.csv"
GATE_SCRIPT = REPO_ROOT / "scripts" / "30_backtest_derived_calibration.py"
FEE_MODEL = REPO_ROOT / "scripts" / "26_fee_model.py"
CORRECTION = REPO_ROOT / "paper_trading" / "scripts" / "lib_correction.py"

NET_EDGE_MIN = 0.03
MIN_STAKE = 5.0
KELLY_FRACTION = 0.25
POSITION_CAP = 0.10
BANKROLL = 500.0

# Team-name crosswalk reused from script 29 if present; else a small default.
DEFAULT_CROSSWALK = {
    "USA": "United States", "Korea Republic": "South Korea", "South Korea": "South Korea",
    "IR Iran": "Iran", "Iran": "Iran", "Cote d'Ivoire": "Ivory Coast",
    "Czechia": "Czech Republic", "Turkiye": "Turkey", "Turkey": "Turkey",
}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate_mod = _load(GATE_SCRIPT, "gate30")     # score_grid, total_over_prob, btts_prob
corr = _load(CORRECTION, "lib_correction")


def devig_two(dec_yes: float, dec_no: float) -> float:
    """Two decimal odds -> de-vigged P(yes)."""
    py, pn = 1.0 / dec_yes, 1.0 / dec_no
    return py / (py + pn)


def kelly_stake(p, a, bankroll, frac=KELLY_FRACTION, cap=POSITION_CAP):
    if not (0 < a < 1) or p <= a:
        return 0.0, 0.0
    f = (p - a) / (1 - a)
    return min(frac * f * bankroll, cap * bankroll), f


def price_leg(p_corr, raw_p, ask, bankroll, fee_fn):
    """Quarter-Kelly leg on the CORRECTED prob. Returns dict or None."""
    a = float(ask)
    if not (0 < a < 1) or p_corr <= a:
        return None
    stake, f_star = kelly_stake(p_corr, a, bankroll)
    contracts = int(stake // a)
    if contracts <= 0:
        return None
    fee = fee_fn(contracts, a)
    net_edge = p_corr - a - fee / contracts
    raw_edge = raw_p - a - fee / contracts
    if net_edge < NET_EDGE_MIN or stake < MIN_STAKE:
        return None
    return {"ask": a, "p_corr": p_corr, "net_edge": net_edge, "raw_edge": raw_edge,
            "contracts": contracts, "stake": stake, "fee": fee,
            "total_cost": contracts * a + fee,
            "pnl_if_win": contracts * (1 - a) - fee, "pnl_if_lose": -(contracts * a + fee)}


def load_gate() -> set:
    if not GATE_JSON.exists():
        sys.exit(f"missing {GATE_JSON} — run scripts/30_backtest_derived_calibration.py first.")
    import json
    g = json.loads(GATE_JSON.read_text())
    return {m["market"] for m in g.get("markets", []) if m["pass"]}


def crosswalk_fn():
    """Reuse script 29's ODDS_TO_MODEL if importable; else the small default."""
    try:
        m29 = _load(REPO_ROOT / "scripts" / "29_backtest_trading_strategy.py", "bt29")
        cw = getattr(m29, "ODDS_TO_MODEL", None)
        if isinstance(cw, dict) and cw:
            return lambda n: cw.get(n, n)
    except Exception:
        pass
    return lambda n: DEFAULT_CROSSWALK.get(n, n)


def backtest(preds: pd.DataFrame, odds: pd.DataFrame, gate: set, fee_fn,
             w: float, with_vig: bool, include_blocked: bool) -> pd.DataFrame:
    preds = preds.copy()
    if "tournament" not in preds.columns and "wc" in preds.columns:
        preds["tournament"] = preds["wc"]   # CSV names it "wc"; parquet renames to "tournament"
    rho = gate_mod._load_rho()
    resolve = crosswalk_fn()
    odds = odds.copy()
    odds["m_home"] = odds["home_team"].map(resolve)
    odds["m_away"] = odds["away_team"].map(resolve)
    obyteam: dict = {}
    have_dates = "date" in odds.columns and pd.to_datetime(odds["date"], errors="coerce").notna().any()
    for _, r in odds.iterrows():
        obyteam.setdefault(frozenset((r["m_home"], r["m_away"])), []).append(r)

    lines = {"over_1.5": 1.5}
    if include_blocked:
        lines["over_2.5"] = 2.5

    rows = []
    matched = 0
    for _, m in preds.iterrows():
        cands = obyteam.get(frozenset((m["home_team"], m["away_team"])))
        if not cands:
            continue
        o = cands[0]
        if len(cands) > 1 and have_dates:
            md = pd.Timestamp(m["date"])
            o = min(cands, key=lambda r: abs((pd.Timestamp(r["date"]) - md).days)
                    if pd.notna(r.get("date")) else 10**6)
        matched += 1
        grid = gate_mod.score_grid(float(m["lambda_home"]), float(m["lambda_away"]), rho)
        tot = m["home_score"] + m["away_score"]
        both = int(m["home_score"] >= 1 and m["away_score"] >= 1)

        # ---- totals lines ----
        for key, ln in lines.items():
            if key not in gate and not (include_blocked and key == "over_2.5"):
                continue
            d_over = o.get(f"over{str(ln).replace('.', '')}")
            d_under = o.get(f"under{str(ln).replace('.', '')}")
            if pd.isna(d_over) or pd.isna(d_under):
                continue
            q_over = devig_two(float(d_over), float(d_under))
            model_over = gate_mod.total_over_prob(grid, ln)
            ask_over = (1.0 / float(d_over)) if with_vig else q_over
            ask_under = (1.0 / float(d_under)) if with_vig else (1 - q_over)
            outcome_over = int(tot > ln)
            rows += _eval_market(m, key, model_over, q_over, ask_over, ask_under,
                                 outcome_over, fee_fn, w)

        # ---- BTTS ----
        if "btts" in gate:
            dy, dn = o.get("btts_yes"), o.get("btts_no")
            if not (pd.isna(dy) or pd.isna(dn)):
                q_btts = devig_two(float(dy), float(dn))
                model_btts = gate_mod.btts_prob(grid)
                ask_yes = (1.0 / float(dy)) if with_vig else q_btts
                ask_no = (1.0 / float(dn)) if with_vig else (1 - q_btts)
                rows += _eval_market(m, "btts", model_btts, q_btts, ask_yes, ask_no,
                                     both, fee_fn, w)

    print(f"[join] matched {matched}/{len(preds)} matches to goals odds; "
          f"{len(rows)} qualifying trades (w={w}, with_vig={with_vig})")
    return pd.DataFrame(rows)


def _eval_market(m, key, model_p, market_p, ask_yes, ask_no, outcome_yes, fee_fn, w):
    """Evaluate YES and NO on one market; take the better corrected edge; settle."""
    fv = corr.blend(model_p, market_p, w)
    best, best_side = None, None
    for side, p_corr, raw_p, ask in (("yes", fv, model_p, ask_yes),
                                     ("no", 1 - fv, 1 - model_p, ask_no)):
        leg = price_leg(p_corr, raw_p, ask, BANKROLL, fee_fn)
        if leg and (best is None or leg["net_edge"] > best["net_edge"]):
            best, best_side = leg, side
    if best is None:
        return []
    won = (outcome_yes == 1) if best_side == "yes" else (outcome_yes == 0)
    return [{"tournament": m["tournament"], "date": m["date"], "market": key,
             "fixture": f"{m['home_team']} v {m['away_team']}", "side": best_side,
             "model_p": round(model_p, 4), "market_p": round(market_p, 4),
             "corrected_fv": round(best["p_corr"], 4), "ask": round(best["ask"], 4),
             "net_edge": round(best["net_edge"], 4), "raw_edge": round(best["raw_edge"], 4),
             "contracts": best["contracts"], "total_cost": round(best["total_cost"], 2),
             "bet_won": bool(won),
             "pnl": round(best["pnl_if_win"] if won else best["pnl_if_lose"], 2)}]


def report(df: pd.DataFrame, w: float) -> str:
    L = []
    P = L.append
    P("=" * 72)
    P(f"  DERIVED (TOTALS/BTTS) STRATEGY BACKTEST  ·  blend w={w}")
    P("=" * 72)
    if df.empty:
        P("  No qualifying trades. Either the market priced the goals view efficiently,")
        P("  or the corrected-edge gate is too strict on this sample.")
        return "\n".join(L)
    staked, pnl = df["total_cost"].sum(), df["pnl"].sum()
    wins = int(df["bet_won"].sum())
    P(f"  qualifying trades : {len(df)}")
    P(f"  win rate          : {wins}/{len(df)} = {wins/len(df):.1%}")
    P(f"  total staked      : ${staked:.2f}")
    P(f"  total P&L         : ${pnl:+.2f}")
    P(f"  ROI on staked     : {pnl/staked:+.1%}")
    P(f"  mean corrected edge claimed : {df['net_edge'].mean()*100:+.1f}c")
    pnls = df["pnl"].values
    if len(pnls) > 1 and pnls.std(ddof=1) > 0:
        P(f"  per-trade Sharpe  : {pnls.mean()/pnls.std(ddof=1):+.2f}")
    P("\n  --- by market ---")
    for k, g in df.groupby("market"):
        P(f"  {k:<10} n={len(g):>3}  win={g['bet_won'].mean():.0%}  "
          f"P&L=${g['pnl'].sum():+8.2f}  ROI={g['pnl'].sum()/g['total_cost'].sum():+.1%}")
    P("\n  --- by tournament ---")
    for t, g in df.groupby("tournament"):
        P(f"  {str(t):<8} n={len(g):>3}  win={g['bet_won'].mean():.0%}  P&L=${g['pnl'].sum():+8.2f}")
    P("\n  --- calibration of taken bets (corrected_fv vs realized win) ---")
    bins = [0, 0.4, 0.5, 0.6, 0.7, 1.01]
    g2 = df.copy()
    g2["_b"] = pd.cut(g2["corrected_fv"], bins)
    for b, g in g2.groupby("_b", observed=True):
        P(f"  fv {str(b):<14} n={len(g):>3}  mean={g['corrected_fv'].mean():.3f}  "
          f"realized={g['bet_won'].mean():.3f}")
    return "\n".join(L)


def run(odds_path: Path, w: float, with_vig: bool, include_blocked: bool, fragility: bool) -> int:
    if not PREDS_CSV.exists():
        sys.exit(f"missing {PREDS_CSV} — run scripts/09_backtest_world_cups.py first.")
    if not odds_path.exists():
        _odds_help(odds_path)
        return 2
    preds = pd.read_csv(PREDS_CSV).dropna(subset=["lambda_home", "lambda_away",
                                                  "home_score", "away_score"])
    odds = pd.read_csv(odds_path)
    gate = load_gate()
    fee = _load(FEE_MODEL, "fee26")
    print(f"Gate-passed lines tradeable: {sorted(gate)}\n")
    df = backtest(preds, odds, gate, fee.taker_fee, w, with_vig, include_blocked)
    print(report(df, w))
    out = PROCESSED / "derived_strategy_backtest.csv"
    df.to_csv(out, index=False)
    print(f"\nWrote {out}")

    if fragility and not df.empty:
        print("\n" + "=" * 72)
        print("  FRAGILITY — does the correction help? P&L vs blend weight w")
        print("=" * 72)
        for ww in (0.0, 0.25, 0.5, 0.75, 1.0):
            d = backtest(preds, odds, gate, fee.taker_fee, ww, with_vig, include_blocked)
            if d.empty:
                print(f"  w={ww:.2f}  no trades")
            else:
                print(f"  w={ww:.2f}  n={len(d):>3}  P&L=${d['pnl'].sum():+8.2f}  "
                      f"ROI={d['pnl'].sum()/d['total_cost'].sum():+.1%}  "
                      f"win={d['bet_won'].mean():.0%}   (w=1 is raw model, w=0 is pure market)")
    return 0


def _odds_help(path: Path):
    print(f"""
[odds] No goals-odds file at: {path}

  This backtest needs historical World Cup CLOSING totals + BTTS odds. Pull them
  from the SAME source as data/raw/wc_closing_odds.csv (BetExplorer average-final)
  for the 2018 + 2022 group games, and save a CSV at the path above:

      date,home_team,away_team,over15,under15,btts_yes,btts_no
      2018-06-14,Russia,Saudi Arabia,1.13,5.50,2.10,1.72

  (over25/under25 optional; only used with --include-blocked.) Team names are
  crosswalked to the martj42 convention; unmatched names are reported.
""".rstrip())


def _selftest() -> int:
    """Fabricate odds for the real backtest matches and run the pipeline."""
    preds = pd.read_csv(PREDS_CSV).dropna(subset=["lambda_home", "lambda_away",
                                                  "home_score", "away_score"]).head(60)
    rho = gate_mod._load_rho()
    rng = np.random.default_rng(1)
    recs = []
    for _, m in preds.iterrows():
        g = gate_mod.score_grid(float(m["lambda_home"]), float(m["lambda_away"]), rho)
        p_over = gate_mod.total_over_prob(g, 1.5)
        p_btts = gate_mod.btts_prob(g)
        # market = model nudged + noise, with a 4% two-sided vig
        q_over = float(np.clip(p_over + rng.normal(0, 0.05), 0.05, 0.95))
        q_btts = float(np.clip(p_btts + rng.normal(0, 0.05), 0.05, 0.95))
        recs.append({"date": m["date"], "home_team": m["home_team"], "away_team": m["away_team"],
                     "over15": round(1 / (q_over * 1.02), 3), "under15": round(1 / ((1 - q_over) * 1.02), 3),
                     "btts_yes": round(1 / (q_btts * 1.02), 3), "btts_no": round(1 / ((1 - q_btts) * 1.02), 3)})
    odds = pd.DataFrame(recs)
    gate = {"over_1.5", "btts"}
    fee = _load(FEE_MODEL, "fee26")
    df = backtest(preds, odds, gate, fee.taker_fee, w=0.5, with_vig=False, include_blocked=False)
    assert "market" in df.columns
    assert set(df["market"].unique()) <= {"over_1.5", "btts"}, df["market"].unique()
    # P&L must be finite and settle correctly (win flag consistent with pnl sign)
    if not df.empty:
        assert ((df["bet_won"] & (df["pnl"] > 0)) | (~df["bet_won"] & (df["pnl"] < 0))).all()
    print(report(df, 0.5))
    print("\n[selftest] harness ran end-to-end on synthetic odds — OK")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--odds", default=str(DEFAULT_ODDS))
    ap.add_argument("--blend-w", type=float, default=corr.DEFAULT_BLEND_W)
    ap.add_argument("--with-vig", action="store_true",
                    help="charge the bookmaker vig (raw 1/odds as price) — stricter, realistic")
    ap.add_argument("--include-blocked", action="store_true",
                    help="also trade over_2.5 (blocked by the calibration gate) for comparison")
    ap.add_argument("--no-fragility", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(_selftest())
    raise SystemExit(run(Path(a.odds), a.blend_w, a.with_vig, a.include_blocked, not a.no_fragility))
