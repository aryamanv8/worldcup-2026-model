"""
29_backtest_trading_strategy.py  (Stage 3 validation — the missing piece)

Backtests the *trading strategy* (not the forecasting model) against historical
World Cups. The model has been validated as a forecaster (OOS log loss,
tournament calibration). What has never been tested is whether the entry rule —
"bet when model fair value beats the market price by >= 3c net of fees, inside
the reliable Elo zone" — would actually have *made money* at prior World Cups.

This script answers that. It reuses the EXACT live machinery:
  - fee model:        scripts/26_fee_model.py  (taker = ceil_cents(0.07*C*P*(1-P)))
  - kelly + edge gate: same formulas as paper_trading/scripts/02_price_match_markets.py
        f* = (p - a)/(1 - a);  stake = 0.25 * f* * bankroll, cap 10%, floor $5
        net_edge = p - a - fee/contracts  >= 0.03
  - one position per match (collapse correlated legs), same as select_trades()

WHAT YOU NEED TO SUPPLY (historical closing odds) — see DATA NOTE below.
  football-data.co.uk does NOT publish World Cup 1X2 CSVs (it covers domestic
  leagues only — verified June 2026). So odds are read from a local file you drop
  in data/raw/. Two accepted formats (auto-detected):
    A) generic:  columns  date, home_team, away_team, dec_home, dec_draw, dec_away
    B) football-data style: home/away team cols + decimal 1X2 odds columns
       (prefers CLOSING odds: AvgCH/AvgCD/AvgCA or B365CH/.. ; falls back to
        AvgH/AvgD/AvgA or B365H/..)

Inputs : data/processed/backtest_predictions_recalibrated.parquet  (frozen model)
         data/raw/wc_closing_odds.csv  (or --odds PATH)            (you supply)
Output : console report + reports/backtest_strategy_<stamp>.{csv,md}

Run    : uv run python scripts/29_backtest_trading_strategy.py
         uv run python scripts/29_backtest_trading_strategy.py --years 2018 2022
         uv run python scripts/29_backtest_trading_strategy.py --odds data/raw/wc.csv
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = REPO_ROOT / "data" / "processed"
PREDS = PROCESSED / "backtest_predictions_recalibrated.parquet"
FEE_MODEL_PATH = REPO_ROOT / "scripts" / "26_fee_model.py"
DEFAULT_ODDS = REPO_ROOT / "data" / "raw" / "wc_closing_odds.csv"
REPORTS = REPO_ROOT / "reports"

# ---- strategy constants (must match paper_trading/scripts/02) ----------------
NET_EDGE_MIN = 0.03          # >= 3c per contract after fees
KELLY_FRACTION = 0.25        # quarter-Kelly
POSITION_CAP = 0.10          # <= 10% of bankroll per position
MIN_STAKE = 5.00             # skip if stake < $5
BANKROLL = 500.0             # per-tournament notional (matches the live experiment)

# Reliable zone. The handoff spec says "Elo gap in (-50, +150)". Because home/away
# orientation at a neutral-site World Cup is arbitrary (the results dataset just
# names one team first), a signed window is orientation-dependent; we therefore
# gate on the ABSOLUTE Elo gap by default (|elo_diff| <= 150), which is
# orientation-robust and captures the same "not a blowout mismatch" intent.
# Override with --elo-min / --elo-max to reproduce the literal signed window.
ELO_ABS_MAX = 150.0
ELO_SIGNED = None            # if set to (lo, hi), use signed window instead

GROUP_STAGE_MATCHES = 48     # 32-team WC: 48 group matches, then 16 knockout = 64


# ============================================================ fee model import
def load_fee_model():
    spec = importlib.util.spec_from_file_location("fee_model_26", FEE_MODEL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================ staking
def kelly_stake(p: float, a: float, bankroll: float) -> tuple[float, float]:
    """f* = (p-a)/(1-a); stake = 0.25*f**bankroll capped at 10%. Returns (stake, f*)."""
    if not (0 < a < 1) or p <= a:
        return 0.0, 0.0
    f_star = (p - a) / (1 - a)
    stake = KELLY_FRACTION * f_star * bankroll
    return min(stake, POSITION_CAP * bankroll), f_star


def price_leg(model_p: float, ask: float, bankroll: float, fee_fn) -> dict | None:
    """Replicates 02_price_match_markets.price_leg for ONE side. ask in dollars."""
    if not (0 < ask < 1) or model_p <= ask:
        return None
    stake, f_star = kelly_stake(model_p, ask, bankroll)
    contracts = int(stake // ask)
    if contracts <= 0:
        return None
    fee = fee_fn(contracts, ask)
    net_edge = model_p - ask - fee / contracts
    qualifies = (net_edge >= NET_EDGE_MIN) and (stake >= MIN_STAKE)
    return {
        "qualifies": qualifies, "p": model_p, "ask": ask, "f_star": f_star,
        "net_edge": net_edge, "stake": stake, "contracts": contracts, "fee": fee,
        "total_cost": contracts * ask + fee,
        "pnl_if_win": contracts * (1 - ask) - fee,
        "pnl_if_lose": -(contracts * ask + fee),
    }


# ============================================================ name handling
def _strip(s) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s))
                   if not unicodedata.combining(c)).lower().strip()


# football-data.co.uk / common-source names  ->  martj42 names used in the parquet
ODDS_TO_MODEL = {
    "usa": "United States", "united states": "United States", "us": "United States",
    "south korea": "South Korea", "korea republic": "South Korea", "korea, south": "South Korea",
    "north korea": "North Korea", "korea dpr": "North Korea",
    "iran": "Iran", "ir iran": "Iran",
    "ivory coast": "Ivory Coast", "cote d'ivoire": "Ivory Coast",
    "czech republic": "Czech Republic", "czechia": "Czech Republic",
    "bosnia and herzegovina": "Bosnia and Herzegovina", "bosnia-herzegovina": "Bosnia and Herzegovina",
    "serbia": "Serbia", "russia": "Russia",
    "saudi arabia": "Saudi Arabia", "costa rica": "Costa Rica",
    "south africa": "South Africa", "new zealand": "New Zealand",
}


def build_crosswalk(model_names: set[str]):
    """Returns a function odds_name -> model_name (or None)."""
    stripped = {_strip(m): m for m in model_names}

    def resolve(name) -> str | None:
        if name is None or (isinstance(name, float) and math.isnan(name)):
            return None
        s = _strip(name)
        if s in ODDS_TO_MODEL and ODDS_TO_MODEL[s] in model_names:
            return ODDS_TO_MODEL[s]
        if s in stripped:
            return stripped[s]
        # last resort: prefix/startswith match (handles "Korea Rep", etc.)
        for ks, full in stripped.items():
            if ks.startswith(s) or s.startswith(ks):
                return full
        return None

    return resolve


# ============================================================ odds loading
ODDS_COL_PRIORITY = [
    ("AvgCH", "AvgCD", "AvgCA"),   # market-average closing (preferred)
    ("MaxCH", "MaxCD", "MaxCA"),   # best-available closing
    ("B365CH", "B365CD", "B365CA"),
    ("PSCH", "PSCD", "PSCA"),
    ("AvgH", "AvgD", "AvgA"),      # pre-closing fallbacks
    ("MaxH", "MaxD", "MaxA"),
    ("B365H", "B365D", "B365A"),
    ("dec_home", "dec_draw", "dec_away"),  # generic schema
]
TEAM_COL_CANDIDATES = [("HomeTeam", "AwayTeam"), ("Home", "Away"),
                       ("home_team", "away_team"), ("home", "away")]
DATE_COL_CANDIDATES = ["Date", "date", "MatchDate", "match_date"]


def load_odds(path: Path) -> pd.DataFrame:
    if not path.exists():
        _odds_missing_help(path)
        sys.exit(1)
    raw = pd.read_csv(path)
    cols = set(raw.columns)

    th = ta = None
    for h, a in TEAM_COL_CANDIDATES:
        if h in cols and a in cols:
            th, ta = h, a
            break
    if th is None:
        sys.exit(f"[odds] could not find home/away team columns in {path.name}. "
                 f"Have: {sorted(cols)[:20]}")

    oh = od = oa = which = None
    for h, d, a in ODDS_COL_PRIORITY:
        if h in cols and d in cols and a in cols:
            oh, od, oa, which = h, d, a, (h, d, a)
            break
    if oh is None:
        sys.exit(f"[odds] no recognised decimal 1X2 odds columns in {path.name}. "
                 f"Expected one of {ODDS_COL_PRIORITY}. Have: {sorted(cols)[:30]}")

    dcol = next((c for c in DATE_COL_CANDIDATES if c in cols), None)
    out = pd.DataFrame({
        "odds_home_team": raw[th], "odds_away_team": raw[ta],
        "dec_home": pd.to_numeric(raw[oh], errors="coerce"),
        "dec_draw": pd.to_numeric(raw[od], errors="coerce"),
        "dec_away": pd.to_numeric(raw[oa], errors="coerce"),
    })
    if dcol:
        out["odds_date"] = pd.to_datetime(raw[dcol], errors="coerce", dayfirst=True)
    out = out.dropna(subset=["dec_home", "dec_draw", "dec_away"]).reset_index(drop=True)
    print(f"[odds] {path.name}: {len(out)} rows, using odds cols {which}"
          f"{' (CLOSING)' if 'C' in which[0] else ' (pre-closing/generic)'}")
    return out


def devig_1x2(dh: float, dd: float, da: float) -> tuple[float, float, float]:
    """Decimal odds -> de-vigged probabilities (proportional, sum to 1)."""
    ph, pd_, pa = 1.0 / dh, 1.0 / dd, 1.0 / da
    s = ph + pd_ + pa
    return ph / s, pd_ / s, pa / s


def _odds_missing_help(path: Path) -> None:
    print(f"""
[odds] No odds file at: {path}

  This backtest needs historical World Cup CLOSING 1X2 odds. football-data.co.uk
  does NOT carry World Cup CSVs (domestic leagues only — verified June 2026), so
  you must drop a file at the path above (or pass --odds PATH).

  Accepted formats (auto-detected):
    A) generic CSV:
         date,home_team,away_team,dec_home,dec_draw,dec_away
         2018-06-14,Russia,Saudi Arabia,1.57,3.80,7.50
    B) football-data style: HomeTeam,AwayTeam + decimal 1X2 columns
         (AvgCH/AvgCD/AvgCA closing preferred; B365H/D/A etc. accepted)

  Team names are crosswalked to the martj42 convention used in the parquet
  ("United States", "South Korea", "Iran", "Ivory Coast", ...). Unmatched names
  are reported so you can extend ODDS_TO_MODEL.
""".rstrip())


# ============================================================ tagging
def signal_tag(side: str, outcome: str, home_team: str, away_team: str,
               elo_diff: float) -> str:
    """favorite-fade / favorite-boost / neutral.
    side in {yes,no}; outcome in {home,draw,away}. Elo favorite = higher Elo team.
    Backing favorite (FOR fav or AGAINST underdog) = boost; opposite = fade;
    any draw leg = neutral."""
    if outcome == "draw":
        return "neutral"
    team = home_team if outcome == "home" else away_team
    fav = home_team if elo_diff >= 0 else away_team
    is_fav = (team == fav)
    backs_fav = (side == "yes" and is_fav) or (side == "no" and not is_fav)
    return "favorite-boost" if backs_fav else "favorite-fade"


def in_reliable_zone(elo_diff: float) -> bool:
    if ELO_SIGNED is not None:
        lo, hi = ELO_SIGNED
        return lo < elo_diff < hi
    return abs(elo_diff) <= ELO_ABS_MAX


# ============================================================ core backtest
def backtest(preds: pd.DataFrame, odds: pd.DataFrame, resolve, fee_fn) -> pd.DataFrame:
    odds = odds.copy()
    odds["m_home"] = odds["odds_home_team"].map(resolve)
    odds["m_away"] = odds["odds_away_team"].map(resolve)

    unmatched = sorted(set(
        odds.loc[odds["m_home"].isna(), "odds_home_team"].tolist()
        + odds.loc[odds["m_away"].isna(), "odds_away_team"].tolist()
    ))
    if unmatched:
        print(f"[crosswalk] {len(unmatched)} unmatched odds team name(s): {unmatched}")

    have_dates = "odds_date" in odds.columns and odds["odds_date"].notna().any()

    # index odds by unordered team pair. A pair can recur within one tournament
    # (e.g. group + third-place: England/Belgium 2018, Croatia/Morocco 2022), so
    # store ALL rows per pair and disambiguate by nearest date at lookup time.
    obyteam: dict[frozenset, list] = {}
    for _, r in odds.iterrows():
        if pd.isna(r["m_home"]) or pd.isna(r["m_away"]):
            continue
        obyteam.setdefault(frozenset((r["m_home"], r["m_away"])), []).append(r)

    rows = []
    matched = 0
    for _, m in preds.iterrows():
        key = frozenset((m["home_team"], m["away_team"]))
        cands = obyteam.get(key)
        if not cands:
            continue
        mdate = pd.Timestamp(m["date"])
        if len(cands) == 1 or not have_dates:
            o = cands[0]
        else:
            # pick the odds row whose date is closest to the prediction's date
            o = min(cands, key=lambda r: abs((pd.Timestamp(r["odds_date"]) - mdate).days)
                    if pd.notna(r["odds_date"]) else 10**6)
        # date-sanity guard: reject cross-tournament collisions (a pair that exists
        # only in a *different* World Cup's odds). Require odds within 60 days.
        if have_dates and pd.notna(o["odds_date"]):
            if abs((pd.Timestamp(o["odds_date"]) - mdate).days) > 60:
                continue
        matched += 1

        # align odds orientation to the parquet's home/away
        if o["m_home"] == m["home_team"]:
            dh, dd, da = o["dec_home"], o["dec_draw"], o["dec_away"]
        else:
            dh, dd, da = o["dec_away"], o["dec_draw"], o["dec_home"]
        q_home, q_draw, q_away = devig_1x2(dh, dd, da)

        model = {"home": m["p_home_win"], "draw": m["p_draw"], "away": m["p_away_win"]}
        market = {"home": q_home, "draw": q_draw, "away": q_away}
        actual = ("home" if m["home_score"] > m["away_score"]
                  else "away" if m["away_score"] > m["home_score"] else "draw")
        elo_diff = float(m["elo_diff"])

        # evaluate all six candidate legs (YES/NO on each outcome), keep best edge
        best = None
        for outcome in ("home", "draw", "away"):
            for side in ("yes", "no"):
                if side == "yes":
                    p, a = model[outcome], market[outcome]
                else:
                    p, a = 1.0 - model[outcome], 1.0 - market[outcome]
                leg = price_leg(p, a, BANKROLL, fee_fn)
                if leg is None:
                    continue
                cand = {**leg, "outcome": outcome, "side": side}
                if best is None or cand["net_edge"] > best["net_edge"]:
                    best = cand

        rzone = in_reliable_zone(elo_diff)
        took = bool(best and best["qualifies"] and rzone)
        rec = {
            "tournament": m["tournament"], "date": m["date"],
            "home_team": m["home_team"], "away_team": m["away_team"],
            "elo_diff": round(elo_diff, 1), "reliable_zone": rzone,
            "actual": actual,
            "p_home": round(model["home"], 4), "p_draw": round(model["draw"], 4),
            "p_away": round(model["away"], 4),
            "q_home": round(q_home, 4), "q_draw": round(q_draw, 4), "q_away": round(q_away, 4),
            "took_trade": took,
        }
        if best:
            rec.update({
                "bet_side": best["side"], "bet_outcome": best["outcome"],
                "model_p": round(best["p"], 4), "market_ask": round(best["ask"], 4),
                "net_edge": round(best["net_edge"], 4), "contracts": best["contracts"],
                "stake": round(best["stake"], 2), "fee": round(best["fee"], 2),
                "total_cost": round(best["total_cost"], 2),
            })
            if took:
                won = ((best["side"] == "yes" and actual == best["outcome"]) or
                       (best["side"] == "no" and actual != best["outcome"]))
                rec["bet_won"] = won
                rec["pnl"] = round(best["pnl_if_win"] if won else best["pnl_if_lose"], 2)
                rec["tag"] = signal_tag(best["side"], best["outcome"],
                                        m["home_team"], m["away_team"], elo_diff)
        rows.append(rec)

    print(f"[join] matched {matched}/{len(preds)} group-stage matches to odds")
    return pd.DataFrame(rows)


# ============================================================ reporting
def report(df: pd.DataFrame) -> str:
    taken = df[df["took_trade"]].copy()
    lines = []
    P = lines.append
    P("=" * 72)
    P("  HISTORICAL TRADING-STRATEGY BACKTEST")
    P("=" * 72)
    P(f"  group-stage matches evaluated : {len(df)}")
    P(f"  matches in reliable zone      : {int(df['reliable_zone'].sum())}")
    P(f"  qualifying trades taken       : {len(taken)}")
    if taken.empty:
        P("\n  No qualifying trades. Strategy never fired on this sample.")
        P("  (Either the market was efficient vs the model, or the reliable-zone /")
        P("   3c-edge filters are too strict for these odds.)")
        return "\n".join(lines)

    staked = taken["total_cost"].sum()
    pnl = taken["pnl"].sum()
    wins = int(taken["bet_won"].sum())
    P(f"  win rate                      : {wins}/{len(taken)} = {wins/len(taken):.1%}")
    P(f"  total staked (cost basis)     : ${staked:.2f}")
    P(f"  total P&L                     : ${pnl:+.2f}")
    P(f"  ROI on staked                 : {pnl/staked:+.1%}")
    P(f"  mean net edge claimed         : {taken['net_edge'].mean()*100:+.1f}c")
    pnls = taken["pnl"].values
    if len(pnls) > 1 and pnls.std(ddof=1) > 0:
        P(f"  per-trade Sharpe-equivalent   : {pnls.mean()/pnls.std(ddof=1):+.2f}")

    P("\n  --- by signal tag ---")
    for tag, g in taken.groupby("tag"):
        P(f"  {tag:<16} n={len(g):>3}  win={g['bet_won'].mean():.0%}  "
          f"P&L=${g['pnl'].sum():+8.2f}  ROI={g['pnl'].sum()/g['total_cost'].sum():+.1%}")

    P("\n  --- by tournament ---")
    for t, g in taken.groupby("tournament"):
        P(f"  {t:<8} n={len(g):>3}  win={g['bet_won'].mean():.0%}  P&L=${g['pnl'].sum():+8.2f}")

    # calibration: do the bets' model probabilities match realized win rate?
    P("\n  --- calibration of taken bets (model_p vs realized win) ---")
    bins = [0, 0.4, 0.5, 0.6, 0.7, 1.01]
    taken["_b"] = pd.cut(taken["model_p"], bins)
    for b, g in taken.groupby("_b", observed=True):
        P(f"  model_p {str(b):<14} n={len(g):>3}  mean_p={g['model_p'].mean():.3f}  "
          f"realized={g['bet_won'].mean():.3f}")
    return "\n".join(lines)


# ============================================================ main
def main():
    global ELO_ABS_MAX, ELO_SIGNED, BANKROLL
    ap = argparse.ArgumentParser(description="Backtest the WC trading strategy on prior World Cups.")
    ap.add_argument("--odds", default=str(DEFAULT_ODDS), help="path to historical odds CSV")
    ap.add_argument("--years", nargs="+", default=["2018", "2022"],
                    help="tournament years to include (default 2018 2022)")
    ap.add_argument("--bankroll", type=float, default=BANKROLL)
    ap.add_argument("--elo-abs-max", type=float, default=ELO_ABS_MAX,
                    help="reliable zone |elo_diff| ceiling (default 150)")
    ap.add_argument("--elo-min", type=float, default=None,
                    help="signed reliable-zone lower bound (use with --elo-max to reproduce handoff's -50..150)")
    ap.add_argument("--elo-max", type=float, default=None)
    args = ap.parse_args()

    BANKROLL = args.bankroll
    ELO_ABS_MAX = args.elo_abs_max
    if args.elo_min is not None and args.elo_max is not None:
        ELO_SIGNED = (args.elo_min, args.elo_max)
        print(f"[zone] signed Elo window ({args.elo_min}, {args.elo_max})")
    else:
        print(f"[zone] absolute Elo window |elo_diff| <= {ELO_ABS_MAX}")

    if not PREDS.exists():
        sys.exit(f"missing {PREDS}")
    preds = pd.read_parquet(PREDS)
    preds = preds[preds["tournament"].astype(str).isin([str(y) for y in args.years])].copy()
    preds["date"] = pd.to_datetime(preds["date"])

    # group stage = first 48 matches per tournament by date (knockouts follow a gap)
    gp = []
    for t, g in preds.groupby("tournament"):
        g = g.sort_values("date")
        grp = g.head(GROUP_STAGE_MATCHES)
        kn = g.iloc[GROUP_STAGE_MATCHES:]
        boundary = grp["date"].max()
        ko_start = kn["date"].min() if len(kn) else None
        print(f"[group] {t}: {len(grp)} group matches (last {boundary.date()}), "
              f"knockouts start {ko_start.date() if ko_start is not None else 'n/a'}")
        gp.append(grp)
    preds = pd.concat(gp, ignore_index=True)

    odds = load_odds(Path(args.odds))
    resolve = build_crosswalk(set(preds["home_team"]) | set(preds["away_team"]))
    fee = load_fee_model()

    df = backtest(preds, odds, resolve, fee.taker_fee)
    text = report(df)
    print("\n" + text)

    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = REPORTS / f"backtest_strategy_{stamp}.csv"
    md_path = REPORTS / f"backtest_strategy_{stamp}.md"
    df.to_csv(csv_path, index=False)
    md_path.write_text(f"# Strategy backtest {stamp}\n\n```\n{text}\n```\n")
    print(f"\n[out] {csv_path}\n[out] {md_path}")


if __name__ == "__main__":
    main()
