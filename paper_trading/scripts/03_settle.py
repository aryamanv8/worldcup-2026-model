#!/usr/bin/env python3
"""
03_settle.py — settlement & P&L bookkeeping for the WC2026 paper-trading book.

portfolio.json is the structured source of truth. trade_log.md is the human mirror:
this script computes everything and PRINTS paste-ready markdown, so you never do the
arithmetic by hand. It also appends calibration_log.csv (model prob vs entry vs
closing vs result) — the record that later answers "edge or bias?".

Usage
-----
  # one-time: seed the ledger with the day-1 book
  uv run python paper_trading/scripts/03_settle.py --init

  # optional: record the closing (kickoff) price of the side you bet, for CLV
  uv run python paper_trading/scripts/03_settle.py --close KXWCGAME-26JUN13BRAMAR 0.40

  # settle a finished match by its regulation winner code (TIE for a draw)
  uv run python paper_trading/scripts/03_settle.py --settle KXWCGAME-26JUN13BRAMAR --winner TIE

  # show the book
  uv run python paper_trading/scripts/03_settle.py --status

Winner codes are the Kalshi FIFA3 suffix of the market ticker (e.g. BRA, MAR) or TIE.
A YES position wins iff its outcome occurred; a NO position wins iff it did not.
Settlement is regulation time (90'+stoppage), matching Kalshi KXWCGAME settlement.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # paper_trading/  (tracked)
DATA = ROOT / "data"                    # transient snapshots (gitignored)
PORTFOLIO = ROOT / "portfolio.json"     # structured source of truth (tracked)
CALIB = ROOT / "calibration_log.csv"    # model-prob vs result vs closing (tracked)
BANKROLL_START = 500.00

# Day-1 book (the four positions logged 2026-06-12/13). `model_fv` is the model's
# fair value FOR THE SIDE BET (NO = complement), so it lines up with bet_won in the
# calibration log. cost = qty*entry + fee.
SEED = [
    dict(id=1, opened="2026-06-12", fixture="Brazil vs Morocco",
         match_prefix="KXWCGAME-26JUN13BRAMAR", ticker="KXWCGAME-26JUN13BRAMAR-BRA",
         outcome_code="BRA", outcome_label="Brazil", side="no",
         entry=0.42, qty=27, fee=0.47, model_fv=0.474, net_edge=0.037,
         match_date="2026-06-13", tag="reliable"),
    dict(id=2, opened="2026-06-13", fixture="Turkiye vs Paraguay",
         match_prefix="KXWCGAME-26JUN19TURPAR", ticker="KXWCGAME-26JUN19TURPAR-PAR",
         outcome_code="PAR", outcome_label="Paraguay", side="yes",
         entry=0.24, qty=125, fee=1.60, model_fv=0.423, net_edge=0.170,
         match_date="2026-06-19", tag="favorite-fade"),
    dict(id=3, opened="2026-06-13", fixture="Ecuador vs Germany",
         match_prefix="KXWCGAME-26JUN25ECUGER", ticker="KXWCGAME-26JUN25ECUGER-GER",
         outcome_code="GER", outcome_label="Germany", side="no",
         entry=0.45, qty=82, fee=1.43, model_fv=0.614, net_edge=0.147,
         match_date="2026-06-25", tag="favorite-fade"),
    dict(id=4, opened="2026-06-13", fixture="Austria vs Jordan",
         match_prefix="KXWCGAME-26JUN17AUTJOR", ticker="KXWCGAME-26JUN17AUTJOR-AUT",
         outcome_code="AUT", outcome_label="Austria", side="no",
         entry=0.27, qty=101, fee=1.40, model_fv=0.430, net_edge=0.146,
         match_date="2026-06-17", tag="favorite-fade"),
]


def cost_of(p: dict) -> float:
    return round(p["qty"] * p["entry"] + p["fee"], 2)


def load() -> dict:
    if not PORTFOLIO.exists():
        sys.exit("no portfolio.json — run with --init first.")
    return json.loads(PORTFOLIO.read_text())


def save(pf: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    pf["updated_utc"] = datetime.now(timezone.utc).isoformat()
    PORTFOLIO.write_text(json.dumps(pf, indent=2))


def do_init(force: bool) -> None:
    if PORTFOLIO.exists() and not force:
        sys.exit(f"{PORTFOLIO} already exists — use --force to overwrite.")
    open_pos = []
    for s in SEED:
        p = dict(s)
        p["cost"] = cost_of(p)
        p["closing"] = None
        open_pos.append(p)
    deployed = round(sum(p["cost"] for p in open_pos), 2)
    pf = dict(bankroll_start=BANKROLL_START,
              cash=round(BANKROLL_START - deployed, 2),
              realized_pnl=0.0, open=open_pos, settled=[])
    save(pf)
    print(f"[init] seeded {len(open_pos)} open positions, deployed ${deployed:.2f}, "
          f"cash ${pf['cash']:.2f}")
    render(pf)


def do_close(prefix: str, price: float) -> None:
    pf = load()
    hit = [p for p in pf["open"] if p["match_prefix"] == prefix]
    if not hit:
        sys.exit(f"no open position with match prefix {prefix}")
    for p in hit:
        p["closing"] = price
        print(f"[close] {p['fixture']}: recorded closing {price:.2f} for {p['bet'] if 'bet' in p else p['outcome_label']}")
    save(pf)


def do_settle(prefix: str, winner: str) -> None:
    pf = load()
    hit = [p for p in pf["open"] if p["match_prefix"] == prefix]
    if not hit:
        sys.exit(f"no open position with match prefix {prefix}")
    winner = winner.upper()
    settled_today = []
    for p in hit:
        occurred = (winner == p["outcome_code"])
        bet_won = occurred if p["side"] == "yes" else (not occurred)
        payoff = round(p["qty"] * 1.0, 2) if bet_won else 0.0
        realized = round(payoff - p["cost"], 2)
        p.update(settled=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                 winner=winner, bet_won=bet_won, payoff=payoff, realized_pnl=realized)
        pf["cash"] = round(pf["cash"] + payoff, 2)
        pf["realized_pnl"] = round(pf["realized_pnl"] + realized, 2)
        pf["open"].remove(p)
        pf["settled"].append(p)
        settled_today.append(p)
        append_calib(p)
        verdict = "WON " if bet_won else "LOST"
        print(f"[settle] {p['fixture']}  {p['side'].upper()} @ {p['outcome_label']}  "
              f"winner={winner}  -> {verdict}  payoff ${payoff:.2f}  P&L {realized:+.2f}")
    save(pf)
    print(f"[book] realized P&L to date {pf['realized_pnl']:+.2f}  cash ${pf['cash']:.2f}  "
          f"equity ${equity(pf):.2f}")
    render(pf, just_settled=settled_today)


def append_calib(p: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    new = not CALIB.exists()
    with CALIB.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["settled", "match", "ticker", "outcome", "side", "model_fv",
                        "entry", "closing", "winner", "bet_won", "realized_pnl", "tag"])
        w.writerow([p["settled"], p["fixture"], p["ticker"], p["outcome_label"], p["side"],
                    f"{p['model_fv']:.4f}", f"{p['entry']:.2f}",
                    "" if p.get("closing") is None else f"{p['closing']:.2f}",
                    p["winner"], int(p["bet_won"]), f"{p['realized_pnl']:.2f}", p.get("tag", "")])


def equity(pf: dict) -> float:
    return round(pf["cash"] + sum(p["cost"] for p in pf["open"]), 2)


def render(pf: dict, just_settled: list | None = None) -> None:
    """Print paste-ready markdown for trade_log.md."""
    open_cost = round(sum(p["cost"] for p in pf["open"]), 2)
    n_set = len(pf["settled"])
    wins = sum(1 for p in pf["settled"] if p.get("bet_won"))
    wr = f"{wins}/{n_set} ({wins/n_set*100:.0f}%)" if n_set else "—"

    print("\n--- paste into trade_log.md : Portfolio summary ---")
    print(f"| As of | {date.today().isoformat()} |")
    print(f"| Starting bankroll | ${pf['bankroll_start']:.2f} |")
    print(f"| Cash | ${pf['cash']:.2f} |")
    print(f"| Open exposure (cost basis) | ${open_cost:.2f} |")
    print(f"| Realized P&L | ${pf['realized_pnl']:.2f} |")
    print(f"| Unrealized P&L | $0.00 |")
    print(f"| **Total equity** | **${equity(pf):.2f}** |")
    print(f"| Open positions | {len(pf['open'])} |")
    print(f"| Settled trades | {n_set} |")
    print(f"| Win rate (settled) | {wr} |")

    print("\n--- Open positions table ---")
    print("| # | Opened | Market | Side | Entry ¢ | Qty | Cost $ | Model FV % | Net edge ¢ | Tag |")
    print("|---|--------|--------|------|---------|-----|--------|------------|------------|-----|")
    for p in sorted(pf["open"], key=lambda x: x["id"]):
        print(f"| {p['id']} | {p['opened']} | {p['fixture']} | {p['side'].upper()} @ {p['outcome_label']} | "
              f"{p['entry']*100:.0f} | {p['qty']} | {p['cost']:.2f} | {p['model_fv']*100:.1f} | "
              f"{p['net_edge']*100:+.1f} | {p.get('tag','')} |")

    if pf["settled"]:
        print("\n--- Settled trades table ---")
        print("| # | Settled | Market | Side | Entry ¢ | Qty | Cost $ | Winner | Result | Payoff $ | Realized P&L $ |")
        print("|---|---------|--------|------|---------|-----|--------|--------|--------|----------|----------------|")
        for p in sorted(pf["settled"], key=lambda x: x["id"]):
            print(f"| {p['id']} | {p['settled']} | {p['fixture']} | {p['side'].upper()} @ {p['outcome_label']} | "
                  f"{p['entry']*100:.0f} | {p['qty']} | {p['cost']:.2f} | {p['winner']} | "
                  f"{'WON' if p['bet_won'] else 'LOST'} | {p['payoff']:.2f} | {p['realized_pnl']:+.2f} |")

    if just_settled:
        print("\n--- P&L history row(s) ---")
        for p in just_settled:
            print(f"| {p['settled']} | settled {p['fixture']} ({'win' if p['bet_won'] else 'loss'}) | "
                  f"{p['realized_pnl']:+.2f} | {equity(pf):.2f} | {p['side'].upper()} @ {p['outcome_label']} |")


def do_status() -> None:
    pf = load()
    print(f"[status] cash ${pf['cash']:.2f}  realized ${pf['realized_pnl']:+.2f}  "
          f"equity ${equity(pf):.2f}  open {len(pf['open'])}  settled {len(pf['settled'])}")
    render(pf)


def main() -> None:
    ap = argparse.ArgumentParser(description="Settle paper-trading positions and roll the bankroll.")
    ap.add_argument("--init", action="store_true", help="seed portfolio.json with the day-1 book")
    ap.add_argument("--force", action="store_true", help="allow --init to overwrite")
    ap.add_argument("--status", action="store_true", help="print the current book")
    ap.add_argument("--close", nargs=2, metavar=("MATCH_PREFIX", "PRICE"),
                    help="record the closing (kickoff) price of the side bet for CLV")
    ap.add_argument("--settle", metavar="MATCH_PREFIX", help="settle the match with this ticker prefix")
    ap.add_argument("--winner", help="regulation winner FIFA3 code, or TIE for a draw")
    args = ap.parse_args()

    if args.init:
        do_init(args.force)
    elif args.close:
        do_close(args.close[0], float(args.close[1]))
    elif args.settle:
        if not args.winner:
            sys.exit("--settle requires --winner CODE (e.g. --winner TIE)")
        do_settle(args.settle, args.winner)
    elif args.status:
        do_status()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()