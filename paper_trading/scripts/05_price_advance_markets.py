#!/usr/bin/env python3
"""
05_price_advance_markets.py  —  Stage 3 / Strategy v2, progression sleeve

Price the tournament-progression markets (team to reach round-of-16 / quarter /
semi / final, and outright champion) against the simulator, with the v2 market-
blend correction, and manage them with a RULE-BASED take-profit instead of
hold-to-settlement.

WHY THIS SLEEVE IS DIFFERENT
  - Per-match markets are held to settlement for clean attribution. Progression
    markets are continuous and our edge there is largest pre-tournament and DECAYS
    as real results arrive, so harvesting that decay (sell into appreciation) is
    the strategy, not a deviation (docs/strategy_v2.md §5).
  - Stage 2 found NO value edge on the liquid outright/champion market (favorite-
    longshot bias is market structure). So champion is, by default, only a take-
    profit vehicle, not an entry signal — entries should come from the less
    efficient earlier-round (advance / reach-RO16) contracts, and only if a
    CORRECTED edge survives.

INPUTS (produced on the Mac)
  - data/processed/model_vs_market.parquet  (script 23): per (contract, team)
      model_fv, market_raw, market_devig, yes_bid, yes_ask, volume.
      ** Refresh it each run (scripts 22 -> 23) so prices are live; the committed
         file is a June-11 snapshot and is stale for take-profit. **
  - paper_trading/portfolio.json : open positions; those tagged "progression" are
      managed for take-profit here.

OUTPUTS
  - paper_trading/data/advance_slate.json/.md : entry candidates + take-profit
      actions on held progression positions.

Run (on the Mac, from repo root):
    uv run python paper_trading/scripts/05_price_advance_markets.py --bankroll 500
    uv run python paper_trading/scripts/05_price_advance_markets.py --selftest   # math only
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DATA = REPO_ROOT / "paper_trading" / "data"
MVM = REPO_ROOT / "data" / "processed" / "model_vs_market.parquet"
PORTFOLIO = REPO_ROOT / "paper_trading" / "portfolio.json"
FEE_MODEL = REPO_ROOT / "scripts" / "26_fee_model.py"
CORRECTION = HERE / "lib_correction.py"

NET_EDGE_MIN = 0.03
MIN_STAKE = 5.0
KELLY_FRACTION = 0.25
POSITION_CAP = 0.10
# Entry is allowed on earlier-round contracts; champion is take-profit-only by default.
ENTRY_CONTRACTS = {"reach_round_of_16", "reach_quarter_final", "reach_semi_final", "reach_final"}
# Take-profit: sell when sellable price >= corrected fair value (edge realized) OR
# >= entry * (1 + TP_MULT), whichever first.
TP_MULT = 0.60


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


corr = _load(CORRECTION, "lib_correction")


def kelly_stake(p, a, bankroll, frac=KELLY_FRACTION, cap=POSITION_CAP):
    if not (0 < a < 1) or p <= a:
        return 0.0, 0.0
    f = (p - a) / (1 - a)
    return min(frac * f * bankroll, cap * bankroll), f


def entry_candidate(model_fv, market_devig, yes_ask, bankroll, fee_fn, w, position_cap=POSITION_CAP):
    """BUY-YES progression entry on CORRECTED edge. Returns dict or None."""
    fv = corr.blend(model_fv, market_devig, w)
    a = float(yes_ask)
    if not (0 < a < 1) or fv <= a:
        return None
    stake, f_star = kelly_stake(fv, a, bankroll, cap=position_cap)
    contracts = int(stake // a)
    if contracts <= 0:
        return None
    fee = fee_fn(contracts, a)
    net_edge = fv - a - fee / contracts
    raw_edge = float(model_fv) - a - fee / contracts
    if net_edge < NET_EDGE_MIN or stake < MIN_STAKE:
        return None
    return {"side": "yes", "corrected_fv": round(fv, 4), "model_fv": round(float(model_fv), 4),
            "market_devig": round(float(market_devig), 4), "ask": a,
            "net_edge": round(net_edge, 4), "raw_edge_claimed": round(raw_edge, 4),
            "shrunk_by": round(raw_edge - net_edge, 4), "contracts": contracts,
            "stake": round(stake, 2), "fee": round(fee, 2),
            "total_cost": round(contracts * a + fee, 2),
            "take_profit_target": round(min(fv, a * (1 + TP_MULT)), 4),
            "tp_rule": f"sell at corrected fv {fv:.2f} or {a*(1+TP_MULT):.2f} (entry x{1+TP_MULT:.2f})"}


def take_profit_action(pos, current_bid, corrected_fv, fee_fn):
    """
    Decide whether to SELL a held progression position now.
    pos: dict with entry, qty. current_bid: price we can sell into.
    Returns dict with action HOLD/SELL + reason + marked P&L.
    """
    entry = float(pos["entry"])
    qty = int(pos["qty"])
    target_edge = float(corrected_fv)
    target_mult = entry * (1 + TP_MULT)
    sell = (current_bid >= target_edge) or (current_bid >= target_mult)
    fee = fee_fn(qty, current_bid)
    marked_pnl = qty * (current_bid - entry) - fee   # exit fee only; entry fee already sunk
    reason = ("edge realized (bid >= corrected fv)" if current_bid >= target_edge
              else f"+{TP_MULT*100:.0f}% target hit" if current_bid >= target_mult
              else "below both targets")
    return {"fixture": pos.get("fixture", pos.get("outcome_label", "?")),
            "ticker": pos.get("ticker"), "entry": entry, "qty": qty,
            "current_bid": round(float(current_bid), 4),
            "corrected_fv": round(float(corrected_fv), 4),
            "sell_target_mult": round(target_mult, 4),
            "action": "SELL" if sell else "HOLD", "reason": reason,
            "marked_pnl_if_sell": round(marked_pnl, 2)}


def run(bankroll: float, w: float, show_all: bool,
        max_deploy: float = 0.06, position_cap: float = 0.02) -> int:
    fee = _load(FEE_MODEL, "fee26")
    if not MVM.exists():
        raise SystemExit(f"missing {MVM} — run scripts 22 then 23 on the Mac to refresh "
                         f"the outright/advance market snapshot first.")
    mvm = pd.read_parquet(MVM)
    print(f"Loaded {len(mvm)} progression contracts from {MVM.name}")
    print(f"TINY EXPERIMENT: deploy_cap {max_deploy:.0%} · position_cap {position_cap:.0%} "
          f"· blend_w {w} (no backtest exists for this sleeve)\n")

    # ---- entry candidates (earlier-round contracts; corrected edge) ----------
    entries = []
    for _, r in mvm.iterrows():
        if r["contract"] not in ENTRY_CONTRACTS:
            continue
        c = entry_candidate(r["model_fv"], r["market_devig"], r["yes_ask"],
                            bankroll, fee.taker_fee, w, position_cap=position_cap)
        if c:
            c.update({"contract": r["contract"], "team": r["team"],
                      "ticker": r["market_ticker"], "tag": "progression"})
            entries.append(c)
    entries.sort(key=lambda x: x["net_edge"], reverse=True)
    # total-deploy cap across the sleeve (greedy by edge)
    kept, deferred, spent = [], [], 0.0
    for e in entries:
        if spent + e["total_cost"] <= max_deploy * bankroll + 1e-9:
            kept.append(e); spent += e["total_cost"]
        else:
            deferred.append({**e, "deferred_reason": f"deploy cap {max_deploy:.0%}"})
    if deferred:
        print(f"[cap] {len(deferred)} entry(ies) deferred by the {max_deploy:.0%} deploy cap")
    entries = kept

    # ---- take-profit on held progression positions ---------------------------
    tp_actions = []
    if PORTFOLIO.exists():
        pf = json.loads(PORTFOLIO.read_text())
        bid_by_ticker = {r["market_ticker"]: (r["yes_bid"], corr.blend(r["model_fv"], r["market_devig"], w))
                         for _, r in mvm.iterrows()}
        for pos in pf.get("open", []):
            if pos.get("tag") != "progression":
                continue
            tk = pos.get("ticker")
            if tk in bid_by_ticker:
                bid, cfv = bid_by_ticker[tk]
                tp_actions.append(take_profit_action(pos, bid, cfv, fee.taker_fee))
            else:
                tp_actions.append({"fixture": pos.get("fixture"), "ticker": tk,
                                   "action": "HOLD", "reason": "no live quote in snapshot"})

    _report(entries, tp_actions, bankroll, show_all)
    _write(entries, tp_actions, bankroll)
    return 0


def _report(entries, tp_actions, bankroll, show_all):
    print("=" * 78)
    print("PROGRESSION ENTRY CANDIDATES (corrected edge >= 3c; champion is TP-only)")
    print("=" * 78)
    if not entries:
        print("  none. (Expected if the market already prices our progression view — "
              "Stage 2's result for liquid outrights.)")
    for e in entries:
        print(f"  {e['team']:<22} {e['contract']:<20} YES  corr fv {e['corrected_fv']:.2f} "
              f"vs ask {e['ask']:.2f} (mkt {e['market_devig']:.2f}) net {e['net_edge']*100:+.1f}c "
              f"[claimed {e['raw_edge_claimed']*100:+.1f}c]  {e['contracts']}ct ${e['total_cost']:.2f}")
        print(f"      take-profit: {e['tp_rule']}")
    print("\n" + "=" * 78)
    print("TAKE-PROFIT ON HELD PROGRESSION POSITIONS")
    print("=" * 78)
    if not tp_actions:
        print("  none held. (Rule is armed for when progression positions are opened.)")
    for t in tp_actions:
        line = f"  {str(t.get('fixture')):<24} {t['action']:<5} {t.get('reason','')}"
        if "current_bid" in t:
            line += (f"  bid {t['current_bid']:.2f} vs corr fv {t['corrected_fv']:.2f} / "
                     f"tgt {t['sell_target_mult']:.2f}  P&L if sell ${t['marked_pnl_if_sell']:.2f}")
        print(line)


def _write(entries, tp_actions, bankroll):
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "bankroll": bankroll,
           "entries": entries, "take_profit": tp_actions}
    (DATA / "advance_slate.json").write_text(json.dumps(out, indent=2))
    md = [f"# Progression slate — {datetime.now(timezone.utc):%Y-%m-%d %H:%MZ}", "",
          "Corrected edges (model blended toward market). Champion is take-profit-only.", ""]
    md.append("## Entry candidates")
    if entries:
        md.append("| team | contract | corr fv | ask | mkt | net edge | claimed | ct | cost |")
        md.append("|---|---|---|---|---|---|---|---|---|")
        for e in entries:
            md.append(f"| {e['team']} | {e['contract']} | {e['corrected_fv']:.2f} | {e['ask']:.2f} | "
                      f"{e['market_devig']:.2f} | {e['net_edge']*100:+.1f}c | {e['raw_edge_claimed']*100:+.1f}c | "
                      f"{e['contracts']} | ${e['total_cost']:.2f} |")
    else:
        md.append("_None — market already prices our progression view._")
    md += ["", "## Take-profit actions"]
    if tp_actions:
        md.append("| position | action | reason | P&L if sell |")
        md.append("|---|---|---|---|")
        for t in tp_actions:
            md.append(f"| {t.get('fixture')} | {t['action']} | {t.get('reason','')} | "
                      f"${t.get('marked_pnl_if_sell','-')} |")
    else:
        md.append("_No progression positions held._")
    (DATA / "advance_slate.md").write_text("\n".join(md))


def _selftest() -> int:
    fee = _load(FEE_MODEL, "fee26")
    # Entry: model 0.55 to reach QF, market devig 0.45, ask 0.45. Corrected fv 0.50.
    e = entry_candidate(0.55, 0.45, 0.45, 500.0, fee.taker_fee, w=0.5)
    assert e is not None and e["corrected_fv"] == 0.5, e
    assert e["raw_edge_claimed"] > e["net_edge"] > 0, e
    # Take-profit: bought at 0.30, now bid 0.55, corrected fv 0.50 -> SELL (edge realized)
    tp = take_profit_action({"entry": 0.30, "qty": 50, "ticker": "X"}, 0.55, 0.50, fee.taker_fee)
    assert tp["action"] == "SELL" and "edge realized" in tp["reason"], tp
    assert tp["marked_pnl_if_sell"] > 0, tp
    # Below targets -> HOLD
    tp2 = take_profit_action({"entry": 0.30, "qty": 50, "ticker": "X"}, 0.40, 0.50, fee.taker_fee)
    assert tp2["action"] == "HOLD", tp2     # 0.40 < fv 0.50 and < 0.30*1.6=0.48
    print(f"[selftest] entry corr fv {e['corrected_fv']} net {e['net_edge']:+.3f} "
          f"(claimed {e['raw_edge_claimed']:+.3f}); TP SELL P&L ${tp['marked_pnl_if_sell']:.2f}")
    print("[selftest] all assertions passed")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bankroll", type=float, default=500.0)
    ap.add_argument("--blend-w", type=float, default=corr.DEFAULT_BLEND_W)
    ap.add_argument("--max-deploy", type=float, default=0.06,
                    help="total cost cap for the progression sleeve (frac of bankroll)")
    ap.add_argument("--position-cap", type=float, default=0.02,
                    help="per-position cap (frac of bankroll) — tiny experiment")
    ap.add_argument("--show-all", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(_selftest())
    raise SystemExit(run(a.bankroll, a.blend_w, a.show_all, a.max_deploy, a.position_cap))
