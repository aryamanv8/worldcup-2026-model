#!/usr/bin/env python3
"""
04_price_derived_markets.py  —  Stage 3 / Strategy v2, goals-market sleeve

Price the live Kalshi TOTALS (KXWCTOTAL over/under) and BTTS (KXWCBTTS) markets
against the model's joint score matrix, with the v2 market-blend correction, and
emit a paper-trade slate under the same risk rules as the moneyline pricer.

WHY A SEPARATE SCRIPT
  - These are the model's *native* output (it's a goals model) and the Kalshi
    lines are liquid, but they were never validated. So this sleeve is GATED on
    `scripts/30_backtest_derived_calibration.py`: a line trades only if its
    per-market `pass` flag in data/processed/derived_calibration.json is true.
    Out of the box that is `over_1.5` and `btts`; `over_2.5` is BLOCKED because the
    model under-predicts mid-range goals (see the gate report).
  - Every edge is computed against the CORRECTED fair value (model blended toward
    the market mid), never the raw model — see paper_trading/scripts/lib_correction.py.

WHAT IT DOES
  1. Loads the model exactly like 02_price_match_markets.py (shared Deps).
  2. Reads the latest discovered markets CSV (match_markets_*.csv), keeps
     market_type in {total, btts}, status active.
  3. For each fixture, builds the recalibrated grid once, reads off
       total_over_prob(grid, line)   (YES = "over"; NO = "under")
       btts_prob(grid)               (YES = both score)
  4. Anchors to the market (devig the two asks), blends (w=0.5 default), prices
     BOTH sides through fees + quarter-Kelly, applies the >=3c corrected-edge gate.
  5. Only emits legs whose market key passed the calibration gate.
  6. Writes paper_trading/data/derived_slate.{json,md} and prints a board.

Run (on the Mac, from repo root):
    uv run python paper_trading/scripts/04_price_derived_markets.py --bankroll 500
    uv run python paper_trading/scripts/04_price_derived_markets.py --selftest   # math only, no model
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DATA = REPO_ROOT / "paper_trading" / "data"
GATE_JSON = REPO_ROOT / "data" / "processed" / "derived_calibration.json"
MONEYLINE = HERE / "02_price_match_markets.py"
CORRECTION = HERE / "lib_correction.py"

NET_EDGE_MIN = 0.03
MIN_STAKE = 5.0
# v2 risk policy (all overridable from the CLI):
MIN_VOLUME = 500.0      # liquidity floor — skip markets thinner than this (contracts)
MAX_DIVERGENCE = 0.25   # suppress a leg if |model_p - market_p| exceeds this. A huge
                        #   gap vs a quote means the model is wrong, not that there's
                        #   edge (the Colombia/Congo-DR trap). The blend can't fix it.
MAX_DEPLOY = 0.50       # total cost basis across the whole slate, as frac of bankroll
POSITION_CAP = 0.10     # per CORRELATED position (same fixture = one), as frac of bankroll


def apply_portfolio_caps(slate, bankroll, max_deploy=MAX_DEPLOY, position_cap=POSITION_CAP):
    """
    Enforce v2 caps on a ranked slate. Same-fixture legs are ONE correlated
    position: their combined cost is capped at position_cap, and total cost across
    the slate is capped at max_deploy. Greedy by net edge (slate must be pre-sorted).
    Returns (kept, deferred) with a 'deferred_reason' on each dropped leg.
    """
    kept, deferred = [], []
    per_fixture = {}
    total = 0.0
    for t in slate:
        c = t["total_cost"]
        fx = t["fixture"]
        if total + c > max_deploy * bankroll + 1e-9:
            deferred.append({**t, "deferred_reason": f"total deploy cap {max_deploy:.0%}"})
            continue
        if per_fixture.get(fx, 0.0) + c > position_cap * bankroll + 1e-9:
            deferred.append({**t, "deferred_reason": f"per-position cap {position_cap:.0%} on {fx}"})
            continue
        kept.append(t)
        per_fixture[fx] = per_fixture.get(fx, 0.0) + c
        total += c
    return kept, deferred


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# correction layer (pure numpy — always importable)
corr = _load(CORRECTION, "lib_correction")


def latest_markets_csv() -> Path:
    cands = sorted(DATA.glob("match_markets_*.csv"))
    if not cands:
        sys.exit(f"no match_markets_*.csv in {DATA} — run 01_discover_match_markets.py first.")
    return cands[-1]


def load_gate() -> dict:
    if not GATE_JSON.exists():
        sys.exit(f"missing {GATE_JSON} — run scripts/30_backtest_derived_calibration.py first "
                 f"to open the derived sleeve.")
    g = json.loads(GATE_JSON.read_text())
    return {m["market"]: bool(m["pass"]) for m in g.get("markets", [])}


def price_two_sided(model_p: float, yes_ask_c, no_ask_c, bankroll: float,
                    fee_fn, kelly_stake, w: float) -> dict | None:
    """
    Price a binary market on its CORRECTED fair value. yes_ask_c/no_ask_c in cents.
    Returns the better qualifying side (corrected net edge >= gate) or the best
    near-miss for the board.
    """
    market_p = corr.devig_yes(yes_ask_c, no_ask_c)   # clean P(YES)
    if market_p is None:
        return None
    fv_yes = corr.blend(model_p, market_p, w)          # corrected P(YES)
    best = None
    for side, p_corr, ask_c, raw_p in (
        ("yes", fv_yes, yes_ask_c, model_p),
        ("no", 1.0 - fv_yes, no_ask_c, 1.0 - model_p),
    ):
        if ask_c is None:
            continue
        a = float(ask_c) / 100.0
        if not (0 < a < 1) or p_corr <= a:
            continue
        stake, f_star = kelly_stake(p_corr, a, bankroll)
        contracts = int(stake // a)
        if contracts <= 0:
            continue
        fee = fee_fn(contracts, a)
        net_edge = p_corr - a - fee / contracts          # CORRECTED edge
        raw_edge = raw_p - a - fee / contracts            # what the model claimed
        cand = {"side": side, "p_corr": round(p_corr, 4), "raw_p": round(raw_p, 4),
                "ask": a, "net_edge": round(net_edge, 4), "raw_edge": round(raw_edge, 4),
                "shrunk_by": round(raw_edge - net_edge, 4),
                "stake": round(stake, 2), "contracts": contracts, "fee": round(fee, 2),
                "f_star": round(f_star, 4), "market_p": round(market_p, 4)}
        cand["qualifies"] = bool(net_edge >= NET_EDGE_MIN and stake >= MIN_STAKE)
        if cand["qualifies"]:
            cand["total_cost"] = round(contracts * a + fee, 2)
            cand["pnl_if_win"] = round(contracts * (1 - a) - fee, 2)
            cand["pnl_if_lose"] = round(-(contracts * a + fee), 2)
        if best is None or cand["net_edge"] > best["net_edge"]:
            best = cand
    return best


def run(bankroll: float, show_all: bool, w: float, min_volume: float,
        max_divergence: float, max_deploy: float, position_cap: float,
        markets: set | None = None) -> int:
    ml = _load(MONEYLINE, "moneyline_pricer")
    fee = ml.load_fee_model()
    deps = ml.Deps()
    gate = load_gate()
    csv = latest_markets_csv()
    df = pd.read_csv(csv)
    df = df[df["market_type"].isin(["total", "btts"]) & (df["status"] == "active")]
    print(f"Pricing derived markets from {csv.name} · {len(df)} active total/btts legs")
    print(f"Calibration gate: {', '.join(k for k,v in gate.items() if v) or 'NONE PASS'} tradeable")
    print(f"Guards: min_volume={min_volume:.0f} · max_divergence={max_divergence:.2f} · "
          f"deploy_cap={max_deploy:.0%} · position_cap={position_cap:.0%} · blend_w={w}\n")

    slate, board = [], []
    for fixture, grp in df.groupby("fixture"):
        r0 = grp.iloc[0]
        fc, err = ml.forecast_fixture(deps, str(r0["team_a"]), str(r0["team_b"]),
                                      pd.to_datetime(r0["match_date"]).date()
                                      if pd.notna(r0.get("match_date")) else None)
        if err:
            board.append((fixture, f"skip: {err}"))
            continue
        grid = fc["grid"]
        for _, m in grp.iterrows():
            mtype, line = m["market_type"], m.get("line")
            if mtype == "total":
                key = f"over_{float(line)}" if pd.notna(line) else "over_?"
                model_p = ml.total_over_prob(grid, float(line))     # P(over) = YES
                label = f"{fixture} · over/under {line}"
            else:
                key = "btts"
                model_p = ml.btts_prob(grid)
                label = f"{fixture} · BTTS"
            passed = gate.get(key, False) and (not markets or key in markets)
            res = price_two_sided(model_p, m.get("yes_ask_c"), m.get("no_ask_c"),
                                  bankroll, fee.taker_fee, ml.kelly_stake, w=w)
            # ---- v2 guards: liquidity floor + max model-vs-market divergence ----
            vol = float(m.get("volume") or 0.0)
            suppressed = None
            if vol < min_volume:
                suppressed = f"thin (vol {vol:.0f} < {min_volume:.0f})"
            elif res is not None and abs(model_p - (res.get("market_p") or model_p)) > max_divergence:
                suppressed = f"divergence {abs(model_p - res['market_p']):.2f} > {max_divergence:.2f}"
            board.append((label, key, passed, res, suppressed))
            if res and res.get("qualifies") and passed and suppressed is None:
                slate.append({
                    "fixture": fixture, "market": key, "ticker": m["market_ticker"],
                    "side": res["side"], "model_p": round(model_p, 4),
                    "corrected_fv": res["p_corr"], "market_mid": res["market_p"],
                    "ask": res["ask"], "net_edge": res["net_edge"],
                    "raw_edge_claimed": res["raw_edge"], "shrunk_by": res["shrunk_by"],
                    "contracts": res["contracts"], "stake": res["stake"],
                    "fee": res["fee"], "total_cost": res["total_cost"], "volume": vol,
                    "pnl_if_win": res["pnl_if_win"], "pnl_if_lose": res["pnl_if_lose"],
                    "match_date": str(r0.get("match_date")), "tag": "derived"})

    # rank by corrected edge, then enforce correlation-grouped caps
    slate.sort(key=lambda t: t["net_edge"], reverse=True)
    kept, deferred = apply_portfolio_caps(slate, bankroll, max_deploy, position_cap)

    _print_board(board, show_all)
    _print_slate(kept, deferred, bankroll)
    _write_slate(kept, deferred, bankroll)
    return 0


def _print_board(board, show_all):
    print("=" * 78)
    print("DERIVED BOARD (corrected edge; raw = what the uncorrected model claimed)")
    print("=" * 78)
    for row in board:
        if len(row) == 2:
            print(f"  {row[0]:<46} {row[1]}")
            continue
        label, key, passed, res, suppressed = row
        gate_s = "gate:PASS" if passed else "gate:BLOCK"
        if res is None:
            print(f"  {label:<40} {gate_s:<10} no quote")
            continue
        edge = f"{res['net_edge']*100:+5.1f}c"
        raw = f"(raw {res['raw_edge']*100:+5.1f}c)"
        if suppressed:
            flag = f"SUPPRESSED: {suppressed}"
        elif res.get("qualifies") and passed:
            flag = "TRADE"
        else:
            flag = "."
        if show_all or flag == "TRADE":
            print(f"  {label:<40} {gate_s:<10} {res['side']:<3} corrected {edge} {raw}  {flag}")


def _print_slate(kept, deferred, bankroll):
    print("\n" + "=" * 78)
    print("DERIVED SLATE (gate + corrected edge >= 3c + $5 floor + liquidity/divergence/caps)")
    print("=" * 78)
    if not kept:
        print("  none. (Correct outcome when the model's goals edge is illusory, the line")
        print("   is blocked, the market is thin, or it diverges too far from the model.)")
    tot = sum(t["total_cost"] for t in kept)
    for t in kept:
        print(f"  {t['fixture']} · {t['market']} · {t['side'].upper()}  "
              f"corrected fv {t['corrected_fv']:.2f} vs ask {t['ask']:.2f} "
              f"(market mid {t['market_mid']:.2f}) net {t['net_edge']*100:+.1f}c "
              f"[claimed {t['raw_edge_claimed']*100:+.1f}c, shrunk {t['shrunk_by']*100:.1f}c]")
        print(f"     {t['contracts']} ct  stake ${t['stake']:.2f}  fee ${t['fee']:.2f}  "
              f"cost ${t['total_cost']:.2f}  P&L win ${t['pnl_if_win']:.2f}")
    if kept:
        print(f"\n  total deployed: ${tot:.2f} of ${bankroll:.0f} ({tot/bankroll*100:.1f}%)")
    if deferred:
        print(f"\n  deferred by caps ({len(deferred)}):")
        for t in deferred:
            print(f"    {t['fixture']} · {t['market']} · {t['side']}  "
                  f"net {t['net_edge']*100:+.1f}c — {t['deferred_reason']}")


def _write_slate(kept, deferred, bankroll):
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "bankroll": bankroll, "n_trades": len(kept), "trades": kept, "deferred": deferred}
    (DATA / "derived_slate.json").write_text(json.dumps(out, indent=2))
    md = [f"# Derived-market slate — {datetime.now(timezone.utc):%Y-%m-%d %H:%MZ}", "",
          f"Bankroll basis ${bankroll:.0f} · {len(kept)} trade(s). "
          f"Edges are CORRECTED (model blended toward market).", ""]
    if kept:
        md.append("| fixture | market | side | corr fv | ask | mkt mid | net edge | claimed | contracts | cost | ticker |")
        md.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for t in kept:
            md.append(f"| {t['fixture']} | {t['market']} | {t['side']} | {t['corrected_fv']:.2f} | "
                      f"{t['ask']:.2f} | {t['market_mid']:.2f} | {t['net_edge']*100:+.1f}c | "
                      f"{t['raw_edge_claimed']*100:+.1f}c | {t['contracts']} | ${t['total_cost']:.2f} | "
                      f"{t['ticker']} |")
    else:
        md.append("_No qualifying derived trades._")
    if deferred:
        md += ["", f"## Deferred by caps ({len(deferred)})", "",
               "| fixture | market | side | net edge | reason |", "|---|---|---|---|---|"]
        for t in deferred:
            md.append(f"| {t['fixture']} | {t['market']} | {t['side']} | "
                      f"{t['net_edge']*100:+.1f}c | {t['deferred_reason']} |")
    (DATA / "derived_slate.md").write_text("\n".join(md))


# ---- selftest: pricing math only, no model / no files ----------------------
def _selftest() -> int:
    fee = _load(REPO_ROOT / "scripts" / "26_fee_model.py", "fee26")
    # minimal stand-ins matching the real signatures
    def kelly_stake(p, a, bankroll, frac=0.25, cap=0.10):
        if not (0 < a < 1) or p <= a:
            return 0.0, 0.0
        f = (p - a) / (1 - a)
        return min(frac * f * bankroll, cap * bankroll), f

    # Model loves the over (0.62) but market prices it at 0.50 (asks 52/52 -> mid .50).
    res = price_two_sided(0.62, 52, 52, 500.0, fee.taker_fee, kelly_stake, w=0.5)
    assert res is not None and res["side"] == "yes", res
    # corrected fv halves the gap: 0.5*0.62 + 0.5*0.50 = 0.56
    assert abs(res["p_corr"] - 0.56) < 1e-6, res
    # corrected edge is strictly less than the raw claimed edge
    assert res["raw_edge"] > res["net_edge"], res
    assert abs(res["shrunk_by"] - 0.06) < 1e-6, res    # ate 6c of fictional edge
    # A market that agrees with the model leaves no edge.
    res2 = price_two_sided(0.50, 50, 52, 500.0, fee.taker_fee, kelly_stake, w=0.5)
    assert res2 is None or not res2.get("qualifies"), res2

    # ---- portfolio caps: same fixture is one correlated position ----
    mk = lambda fx, edge, cost: {"fixture": fx, "market": "m", "side": "yes",
                                 "net_edge": edge, "total_cost": cost}
    slate = [mk("A", 0.10, 40), mk("A", 0.09, 40), mk("B", 0.08, 40),
             mk("C", 0.07, 40), mk("D", 0.06, 40), mk("E", 0.05, 40)]
    kept, deferred = apply_portfolio_caps(slate, bankroll=500.0, max_deploy=0.20, position_cap=0.10)
    # 20% of 500 = $100 total; 10% = $50 per fixture. First A kept ($40), second A
    # blocked (would be $80 > $50/fixture), B kept ($80), C kept ($120>100? no: 40+40+40=120>100)
    kept_cost = sum(t["total_cost"] for t in kept)
    assert kept_cost <= 0.20 * 500.0 + 1e-9, kept_cost
    assert any(d["deferred_reason"].startswith("per-position") for d in deferred), deferred
    assert any(d["deferred_reason"].startswith("total deploy") for d in deferred), deferred

    print(f"[selftest] over: corrected fv {res['p_corr']} net {res['net_edge']:+.3f} "
          f"(claimed {res['raw_edge']:+.3f}, shrunk {res['shrunk_by']:.3f}) — OK")
    print(f"[selftest] caps: kept {len(kept)} (${kept_cost:.0f}), deferred {len(deferred)} — OK")
    print("[selftest] all assertions passed")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bankroll", type=float, default=500.0)
    ap.add_argument("--blend-w", type=float, default=corr.DEFAULT_BLEND_W,
                    help="weight on the model in the blend (0..1); lower trusts market more")
    ap.add_argument("--min-volume", type=float, default=MIN_VOLUME,
                    help="liquidity floor: skip markets with fewer traded contracts")
    ap.add_argument("--max-divergence", type=float, default=MAX_DIVERGENCE,
                    help="suppress a leg if |model - market| exceeds this")
    ap.add_argument("--max-deploy", type=float, default=MAX_DEPLOY,
                    help="total cost cap as fraction of bankroll (raise toward 1.0 for 'no cap')")
    ap.add_argument("--position-cap", type=float, default=POSITION_CAP,
                    help="per correlated-position cap as fraction of bankroll")
    ap.add_argument("--markets", default="",
                    help="comma list to restrict sleeve, e.g. 'btts' (default: all gate-passed)")
    ap.add_argument("--show-all", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(_selftest())
    mk = {s.strip() for s in a.markets.split(",") if s.strip()} or None
    raise SystemExit(run(a.bankroll, a.show_all, a.blend_w, a.min_volume,
                         a.max_divergence, a.max_deploy, a.position_cap, mk))
