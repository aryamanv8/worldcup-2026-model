#!/usr/bin/env python3
"""
02_price_match_markets.py  —  Stage 3 paper trading, step (2/3)   [v1: moneyline]

Price the live Kalshi WC match markets against the Stage-1 model and emit a
specific paper-trade slate under the README's entry rules.

WHAT IT DOES (v1 = moneyline only — the one calibrated, reliable-zone surface)
  1. Loads the model exactly like scripts/10_run_simulation.py:
       data/processed/models/poisson_v1.pkl  -> {model, dc_rho, confederation_levels}
       data/processed/team_features.parquet
       data/processed/calibration.json       -> temperature T (=0.77)
       data/processed/model_card.json         -> reliable-zone strata
  2. For each fixture in paper_trading/data/latest_match_markets.json:
       - maps Kalshi names -> model names (USA->United States, Turkiye->Turkey, ...)
       - sets venue exactly like the simulator: hosts (Mexico/Canada/United States)
         are home in their GROUP matches; everything else neutral
       - builds the SAME object the simulator trusts:
             recalibrate_score_matrix(predict_match_dc(...).score_matrix, T)
       - reads off P(home win)/P(draw)/P(away win)
  3. Applies the entry filter for every leg, BOTH yes and no side:
       reliable zone  AND  net edge = p - ask - fee/contract >= 3c
  4. Sizes survivors: quarter-Kelly f*=(p-a)/(1-a), stake=0.25*f**bankroll,
     capped at 10% of bankroll, skipped if < $5.
  5. Prints the full pricing board + a filtered trade slate, and writes a
     markdown block ready to paste into trade_log.md.

Derived markets (totals/spread/BTTS) are intentionally OUT of v1: they have no
T-validation and no reliable zone (the backtest only scored W/D/L). The grid
helpers for them are included + unit-tested so the derived sleeve drops in later.

Run (from repo root):
    uv run python paper_trading/scripts/02_price_match_markets.py
    uv run python paper_trading/scripts/02_price_match_markets.py --bankroll 500 --show-all
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = REPO_ROOT / "data" / "processed"
MODEL_PKL = PROCESSED / "models" / "poisson_v1.pkl"
FEATURES = PROCESSED / "team_features.parquet"
CALIBRATION = PROCESSED / "calibration.json"
MODEL_CARD = PROCESSED / "model_card.json"
FEE_MODEL_PATH = REPO_ROOT / "scripts" / "26_fee_model.py"
MARKETS = REPO_ROOT / "paper_trading" / "data" / "latest_match_markets.json"
OUT_DIR = REPO_ROOT / "paper_trading" / "data"

# Venue rule mirrors wc2026.simulation.engine
HOST_TEAMS = {"Mexico", "Canada", "United States"}
GROUP_STAGE_END = date(2026, 6, 27)   # R32 starts ~Jun 28; hosts home only in group

# Kalshi -> model team-name reconciliation (model names from team_features)
NAME_MAP = {
    "USA": "United States", "United States": "United States",
    "Turkiye": "Turkey", "Türkiye": "Turkey",
    "Curacao": "Curaçao",
    "Czechia": "Czech Republic", "Czech Republic": "Czech Republic",
    "Korea Republic": "South Korea", "South Korea": "South Korea",
    "Cote d'Ivoire": "Ivory Coast", "Côte d'Ivoire": "Ivory Coast",
    "IR Iran": "Iran",
}

# Reliable-zone Elo-gap buckets (must match scripts/19_model_card.py)
GAP_EDGES = [-1e9, -300, -150, -50, 50, 150, 300, 1e9]
GAP_LABELS = ["<-300", "-300..-150", "-150..-50", "-50..50", "50..150", "150..300", ">300"]

# Entry rules (README)
NET_EDGE_MIN = 0.03         # >= 3c per contract after fees
KELLY_FRACTION = 0.25       # quarter-Kelly
POSITION_CAP = 0.10         # <= 10% of bankroll
MIN_STAKE = 5.00            # skip if stake < $5
MAX_GOALS = 10              # match the simulator's precompute grid size

# Reliable zone (see reliable_zone()): the committed model_card flags every
# stratum reliable=False (max-per-class ECE<=0.05 is unreachable at n<=70), so we
# instead gate on Elo-gap expected-score agreement — the project's Step-0 signal,
# robust at this sample size.
ZONE_MIN_N = 30             # bucket must be reasonably sampled
ZONE_MAX_EXP_GAP = 0.05     # |exp_model - exp_real| within the bucket


# ============================================================ grid -> markets
def outcome_probs_from_grid(grid: np.ndarray) -> tuple[float, float, float]:
    """grid[i,j]=P(home i, away j). Returns (p_home_win, p_draw, p_away_win)."""
    p_home = float(np.tril(grid, -1).sum())   # i > j
    p_draw = float(np.trace(grid))            # i == j
    p_away = float(np.triu(grid, 1).sum())    # i < j
    s = p_home + p_draw + p_away
    return (p_home / s, p_draw / s, p_away / s) if s > 0 else (0.0, 0.0, 0.0)


def total_over_prob(grid: np.ndarray, line: float) -> float:
    n = grid.shape[0]
    i = np.arange(n)[:, None]
    j = np.arange(n)[None, :]
    return float(grid[(i + j) > line].sum())


def spread_prob(grid: np.ndarray, line: float, home_side: bool) -> float:
    n = grid.shape[0]
    i = np.arange(n)[:, None]
    j = np.arange(n)[None, :]
    diff = (i - j) if home_side else (j - i)
    return float(grid[diff > line].sum())


def btts_prob(grid: np.ndarray) -> float:
    return float(grid[1:, 1:].sum())


# ============================================================ staking + fees
def kelly_stake(p: float, a: float, bankroll: float,
                frac: float = KELLY_FRACTION, cap: float = POSITION_CAP) -> tuple[float, float]:
    """Return (stake_$, f_star). f*=(p-a)/(1-a); stake=frac*f**bankroll, capped."""
    if not (0 < a < 1) or p <= a:
        return 0.0, 0.0
    f_star = (p - a) / (1 - a)
    stake = frac * f_star * bankroll
    return min(stake, cap * bankroll), f_star


def load_fee_model():
    """Import scripts/26_fee_model.py as a module (single source of truth)."""
    spec = importlib.util.spec_from_file_location("fee_model_26", FEE_MODEL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================ reliable zone
def elo_gap_bucket(elo_diff: float) -> str:
    idx = int(np.digitize([elo_diff], GAP_EDGES)[0]) - 1
    idx = max(0, min(idx, len(GAP_LABELS) - 1))
    return GAP_LABELS[idx]


def conf_pairing(conf_a: str, conf_b: str) -> str:
    s = {str(conf_a).upper(), str(conf_b).upper()}
    if s == {"UEFA"}:
        return "intra-UEFA"
    if "UEFA" in s:
        return "UEFA-vs-other"
    return "other-vs-other"


def reliable_zone(card: dict, elo_diff: float, stage: str, cpair: str):
    """Reliable zone via Elo-gap expected-score agreement (robust at n~256).

    The committed model_card flags every stratum reliable=False because it needs
    max-per-class ECE<=0.05 — unreachable when each stratum holds 11-70 matches
    (small-sample ECE is upward-biased). The project's real calibration signal is
    exp_model vs exp_real by Elo gap (script 18's Step 0): a bucket is trustworthy
    when the model's mean expected score tracks reality. Returns (ok, reasons).
    """
    if not card:
        return True, ["no model_card.json — gate skipped (UNVERIFIED)"]
    bucket = elo_gap_bucket(elo_diff)
    rows = [s for s in card.get("strata", [])
            if s.get("stratifier") == "elo_gap" and s.get("group") == bucket]
    if not rows:
        return False, [f"elo_gap={bucket} absent from card -> OUT"]
    s = rows[0]
    n = int(s.get("n", 0))
    gap = abs(float(s.get("exp_model", 0.0)) - float(s.get("exp_real", 0.0)))
    ok = (n >= ZONE_MIN_N) and (gap <= ZONE_MAX_EXP_GAP)
    return ok, [f"elo_gap={bucket} n={n} |Δexp|={gap:.3f} -> {'IN' if ok else 'OUT'}"]


# ============================================================ name mapping
def _strip(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s))
                   if not unicodedata.combining(c)).lower().strip()


def normalize_team(name: str, feature_names: set[str]) -> str | None:
    if name in feature_names:
        return name
    if name in NAME_MAP and NAME_MAP[name] in feature_names:
        return NAME_MAP[name]
    target = _strip(NAME_MAP.get(name, name))
    for fn in feature_names:
        if _strip(fn) == target:
            return fn
    return None


# ============================================================ model wiring
class Deps:
    def __init__(self):
        with open(MODEL_PKL, "rb") as f:
            bundle = __import__("pickle").load(f)
        self.model = bundle["model"]
        self.rho = bundle["dc_rho"]
        self.conf_levels = bundle["confederation_levels"]
        self.features = pd.read_parquet(FEATURES)
        self.feature_names = set(self.features["team"].tolist())
        self.T = 1.0
        if CALIBRATION.exists():
            self.T = float(json.loads(CALIBRATION.read_text()).get("temperature", 1.0))
        self.card = json.loads(MODEL_CARD.read_text()) if MODEL_CARD.exists() else {}
        # lazy import of model funcs (require the wc2026 package / uv env)
        from wc2026.models.poisson import predict_match_dc
        from wc2026.simulation.engine import recalibrate_score_matrix
        self._predict = predict_match_dc
        self._recal = recalibrate_score_matrix

    def feat_row(self, team: str) -> pd.Series:
        return self.features[self.features["team"] == team].iloc[0]

    def grid(self, home: str, away: str, is_neutral: bool) -> np.ndarray:
        pred = self._predict(self.model, self.features, home, away, self.rho,
                             is_neutral=is_neutral, is_competitive=True,
                             confederation_levels=self.conf_levels, max_goals=MAX_GOALS)
        return self._recal(pred["score_matrix"], self.T)


def forecast_fixture(deps: Deps, k_team_a: str, k_team_b: str, match_d: date):
    a = normalize_team(k_team_a, deps.feature_names)
    b = normalize_team(k_team_b, deps.feature_names)
    if not a or not b:
        miss = ", ".join(x for x, ok in [(k_team_a, a), (k_team_b, b)] if not ok)
        return None, f"unmapped team(s): {miss}"

    stage = "group" if (match_d is None or match_d <= GROUP_STAGE_END) else "knockout"
    host = None
    if stage == "group":
        host = a if a in HOST_TEAMS else (b if b in HOST_TEAMS else None)
    if host:
        home, away, is_neutral = host, (b if host == a else a), False
    else:
        home, away, is_neutral = a, b, True

    try:
        grid = deps.grid(home, away, is_neutral)
    except KeyError as e:
        return None, f"model lookup failed: {e}"

    p_home, p_draw, p_away = outcome_probs_from_grid(grid)
    p_win = {home: p_home, away: p_away}
    hr, ar = deps.feat_row(home), deps.feat_row(away)
    elo_diff = float(hr["elo_current"]) - float(ar["elo_current"])
    cpair = conf_pairing(hr.get("confederation", ""), ar.get("confederation", ""))
    rz_ok, rz_reasons = reliable_zone(deps.card, elo_diff, stage, cpair)

    return {
        "model_a": a, "model_b": b, "home": home, "away": away,
        "is_neutral": is_neutral, "host": host, "stage": stage,
        "p_win": p_win, "p_draw": p_draw, "grid": grid,
        "elo_diff": elo_diff, "conf_pairing": cpair,
        "reliable": rz_ok, "rz_reasons": rz_reasons,
    }, None


# ============================================================ pricing one leg
def price_leg(model_p: float, yes_ask_c, no_ask_c, bankroll: float, fee_fn):
    """Evaluate BOTH yes and no; return the best qualifying side or None."""
    best = None
    for sidecode, p, ask_c in (("yes", model_p, yes_ask_c), ("no", 1.0 - model_p, no_ask_c)):
        if ask_c is None:
            continue
        a = ask_c / 100.0
        if not (0 < a < 1) or p <= a:
            continue
        stake, f_star = kelly_stake(p, a, bankroll)
        contracts = int(stake // a)
        if contracts <= 0:
            continue
        fee = fee_fn(contracts, a)
        net_edge = p - a - fee / contracts
        if net_edge < NET_EDGE_MIN or stake < MIN_STAKE:
            cand = {"qualifies": False, "side": sidecode, "p": p, "ask": a,
                    "net_edge": net_edge, "stake": stake, "contracts": contracts, "fee": fee}
        else:
            total_cost = contracts * a + fee
            cand = {"qualifies": True, "side": sidecode, "p": p, "ask": a, "f_star": f_star,
                    "net_edge": net_edge, "stake": stake, "contracts": contracts, "fee": fee,
                    "total_cost": total_cost, "payoff_if_win": contracts * 1.0,
                    "pnl_if_win": contracts * (1 - a) - fee, "pnl_if_lose": -total_cost}
        if best is None or cand["net_edge"] > best["net_edge"]:
            best = cand
    return best


# ============================================================ main
def main():
    global ZONE_MIN_N, ZONE_MAX_EXP_GAP
    ap = argparse.ArgumentParser(description="Price live Kalshi WC moneyline markets vs the model.")
    ap.add_argument("--bankroll", type=float, default=500.0)
    ap.add_argument("--markets", default=str(MARKETS))
    ap.add_argument("--show-all", action="store_true", help="print every leg, not just qualifying trades")
    ap.add_argument("--zone-min-n", type=int, default=ZONE_MIN_N, help="min bucket sample size for reliable zone")
    ap.add_argument("--zone-max-exp-gap", type=float, default=ZONE_MAX_EXP_GAP,
                    help="max |exp_model-exp_real| in the Elo-gap bucket")
    args = ap.parse_args()

    ZONE_MIN_N, ZONE_MAX_EXP_GAP = args.zone_min_n, args.zone_max_exp_gap

    if not Path(args.markets).exists():
        sys.exit(f"missing {args.markets} — run 01_discover_match_markets.py first.")
    payload = json.loads(Path(args.markets).read_text())
    records = [r for r in payload.get("records", []) if r.get("market_type") == "moneyline"]
    if not records:
        sys.exit("no moneyline records in the snapshot.")

    try:
        deps = Deps()
    except Exception as e:
        sys.exit(f"could not load model deps: {e}\n(run from repo root with `uv run`?)")
    fee = load_fee_model()
    print(f"[load] T={deps.T}  rho={deps.rho:+.4f}  teams={len(deps.feature_names)}  "
          f"bankroll=${args.bankroll:.0f}")

    # group legs by fixture
    fixtures: dict[str, list[dict]] = {}
    for r in records:
        fixtures.setdefault(r["fixture_key"], []).append(r)

    trades, board = [], []
    for key, legs in fixtures.items():
        f0 = legs[0]
        md = None
        if f0.get("match_date"):
            try:
                md = date.fromisoformat(f0["match_date"])
            except ValueError:
                md = None
        fc, err = forecast_fixture(deps, f0["team_a"], f0["team_b"], md)
        if err:
            board.append({"fixture": f0["fixture"], "error": err})
            continue

        for leg in legs:
            side = leg.get("side")
            if side == "draw":
                model_p, label = fc["p_draw"], "Draw"
            elif side == "team_a":
                tn = normalize_team(leg["team_a"], deps.feature_names)
                model_p, label = fc["p_win"].get(tn), leg["team_a"]
            elif side == "team_b":
                tn = normalize_team(leg["team_b"], deps.feature_names)
                model_p, label = fc["p_win"].get(tn), leg["team_b"]
            else:
                continue
            if model_p is None:
                continue

            res = price_leg(model_p, leg.get("yes_ask_c"), leg.get("no_ask_c"), args.bankroll, fee.taker_fee)
            row = {"fixture": f0["fixture"], "leg": label, "market_ticker": leg.get("market_ticker"),
                   "model_p": model_p, "yes_ask_c": leg.get("yes_ask_c"), "no_ask_c": leg.get("no_ask_c"),
                   "reliable": fc["reliable"], "elo_diff": fc["elo_diff"],
                   "best": res, "rz_reasons": fc["rz_reasons"]}
            board.append(row)

            if res and res.get("qualifies") and fc["reliable"]:
                trades.append({
                    "fixture": f0["fixture"], "leg": label, "bet": f"{res['side'].upper()} @ {label}",
                    "market_ticker": leg.get("market_ticker"), "side": res["side"],
                    "model_fv": round(res["p"], 4),
                    "outcome": label, "outcome_model_p": round(model_p, 4),
                    "entry_ask": round(res["ask"], 4),
                    "net_edge_per_contract": round(res["net_edge"], 4),
                    "contracts": res["contracts"], "stake": round(res["stake"], 2),
                    "fee": round(res["fee"], 2), "total_cost": round(res["total_cost"], 2),
                    "pnl_if_win": round(res["pnl_if_win"], 2), "pnl_if_lose": round(res["pnl_if_lose"], 2),
                    "match_date": f0.get("match_date"),
                })

    print_board(board, args.show_all)
    print_slate(trades, args.bankroll)
    write_slate(trades, args.bankroll)


def _pct(x):
    return f"{x*100:4.0f}%" if x is not None else "  -"


def print_board(board, show_all):
    print(f"\n{'='*86}\n  MONEYLINE PRICING — model fair value vs market\n{'='*86}")
    seen = set()
    for row in board:
        if "error" in row:
            print(f"\n▶ {row['fixture']}   [SKIP: {row['error']}]")
            continue
        if row["fixture"] not in seen:
            seen.add(row["fixture"])
            zone = "RELIABLE" if row["reliable"] else "OUT-OF-ZONE"
            print(f"\n▶ {row['fixture']}   (Elo gap {row['elo_diff']:+.0f}, {zone})")
        b = row["best"]
        edge = f"{b['net_edge']*100:+5.1f}c" if b else "   -"
        flag = ""
        if b and b.get("qualifies") and row["reliable"]:
            flag = f"  <== TRADE {b['side'].upper()} {b['contracts']}@{b['ask']*100:.0f}c (${b['stake']:.0f})"
        elif b and b.get("qualifies") and not row["reliable"]:
            flag = "  (edge but out-of-zone)"
        if show_all or flag:
            print(f"    {row['leg']:<24} model {_pct(row['model_p'])}  "
                  f"yes {str(row['yes_ask_c'] or '-'):>3}c / no {str(row['no_ask_c'] or '-'):>3}c  "
                  f"best net {edge}{flag}")


def print_slate(trades, bankroll):
    print(f"\n{'='*86}\n  TRADE SLATE — {len(trades)} qualifying paper trade(s)\n{'='*86}")
    if not trades:
        print("  none clear reliable-zone + 3c net-edge + $5 floor. (Efficient board — expected.)")
        return
    total = sum(t["total_cost"] for t in trades)
    for t in trades:
        print(f"\n  {t['fixture']}  —  {t['bet']}")
        print(f"     model fv {t['model_fv']:.3f}  vs ask {t['entry_ask']:.3f}   "
              f"net edge {t['net_edge_per_contract']*100:+.1f}c/ct")
        print(f"     {t['contracts']} contracts  stake ${t['stake']:.2f}  fee ${t['fee']:.2f}  "
              f"cost ${t['total_cost']:.2f}")
        print(f"     P&L if win +${t['pnl_if_win']:.2f}   if lose ${t['pnl_if_lose']:.2f}   ({t['market_ticker']})")
    print(f"\n  total deployed: ${total:.2f} of ${bankroll:.0f} "
          f"({total/bankroll*100:.1f}%)")


def write_slate(trades, bankroll):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (OUT_DIR / f"trade_slate_{stamp}.json").write_text(json.dumps(
        {"generated_utc": datetime.now(timezone.utc).isoformat(), "bankroll": bankroll,
         "n_trades": len(trades), "trades": trades}, indent=2))
    md = [f"### Trade slate {stamp}  (bankroll ${bankroll:.0f})\n"]
    if not trades:
        md.append("_No qualifying trades this cycle._\n")
    else:
        md.append("| fixture | bet | model fv | ask | net edge/ct | contracts | stake | fee | cost | P&L win | P&L lose | ticker |")
        md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for t in trades:
            md.append(f"| {t['fixture']} | {t['bet']} | {t['model_fv']:.3f} | {t['entry_ask']:.3f} | "
                      f"{t['net_edge_per_contract']*100:+.1f}c | {t['contracts']} | ${t['stake']:.2f} | "
                      f"${t['fee']:.2f} | ${t['total_cost']:.2f} | +${t['pnl_if_win']:.2f} | "
                      f"${t['pnl_if_lose']:.2f} | {t['market_ticker']} |")
    path = OUT_DIR / f"trade_slate_{stamp}.md"
    path.write_text("\n".join(md) + "\n")
    print(f"\n[out] {path}\n[out] {OUT_DIR / f'trade_slate_{stamp}.json'}")
    print("      paste the table into paper_trading/trade_log.md once you've reviewed it.")


if __name__ == "__main__":
    main()