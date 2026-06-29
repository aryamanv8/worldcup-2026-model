#!/usr/bin/env python3
"""
32_live_knockout_sim.py  —  LIVE knockout probabilities (exact bracket DP)

Replaces the stale pre-tournament Monte-Carlo sim for the knockout phase. Once the
bracket is fixed (group stage over), reach-round and champion probabilities are an
EXACT dynamic program over the single-elimination tree — no Monte-Carlo noise, and
eliminated teams automatically get 0%.

WHY (2026-06-28 review): `tournament_probs.parquet` is the frozen 2026-06-11 sim;
it still gives knocked-out teams non-zero reach probs (it suggested Scotland to reach
R16 at a 1¢ market). This recomputes them live.

TWO PARTS, cleanly separated so the math is testable without the model:
  1. bracket_reach_probs(bracket, pwin)  — PURE: given the ordered list of teams in
     the bracket and a pairwise P(A beats B) table, returns each team's
     P(reach R16/QF/SF/F/champion). Verified by --selftest (no model needed).
  2. model wiring (Mac only) — builds `pwin` from the frozen match model's score
     matrices: P(A beats B in a knockout tie) = P(A win in reg) + P(draw)*shootout,
     shootout split defaulting to 0.5 (knockout shootouts ~ coin flip).

INPUT  : data/processed/knockout_bracket.json  — the actual bracket, IN BRACKET ORDER:
           {"rounds": ["R16","QF","SF","F","champion"],
            "r32_order": ["South Africa","Canada","Brazil","Japan", ... 32 teams]}
         Adjacent pairs (0,1),(2,3)… are the R32 matches; the winners of (0,1) and
         (2,3) meet next, etc. Assemble it from the Kalshi fixtures as the markets
         open (see scripts/assemble_bracket helper / the review notes), and verify
         it against the official bracket before trusting champion numbers.
OUTPUT : data/processed/tournament_probs_live.parquet (+ a readable .md), and a
         continent-win breakdown (sum of champion probs by confederation).

Run (Mac): uv run python scripts/32_live_knockout_sim.py
Test     : python scripts/32_live_knockout_sim.py --selftest   # DP only, no model
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = REPO_ROOT / "data" / "processed"
BRACKET = PROCESSED / "knockout_bracket.json"
OUT_PARQUET = PROCESSED / "tournament_probs_live.parquet"
OUT_MD = REPO_ROOT / "reports" / "knockout_live_probs.md"
ROUND_LABELS = ["reach_R16", "reach_QF", "reach_SF", "reach_F", "champion"]


def bracket_reach_probs(bracket: list[str], pwin: dict) -> dict:
    """
    EXACT reach-round probabilities over a single-elimination bracket.

    bracket : list of N=2^k teams in bracket order. Adjacent pairs are round-1 ties.
    pwin    : pwin[(a, b)] = P(a beats b) in a tie. Must be defined for every pair
              that can meet; pwin[(a,b)] + pwin[(b,a)] == 1.

    Returns {team: [P(reach round 2), P(reach round 3), ..., P(champion)]} where the
    rounds correspond to ROUND_LABELS for a 32-team bracket.

    Method: `alive[t]` = P(team t has reached the current round's match). Each round,
    a team advances by beating exactly one opponent drawn from its mirror block; the
    opponent is there with prob `alive[o]`, and the events are mutually exclusive
    across opponents in the block, so we sum  alive[t]*alive[o]*pwin[t,o].
    """
    n = len(bracket)
    assert n & (n - 1) == 0 and n >= 2, f"bracket size must be a power of 2, got {n}"
    pos = {t: i for i, t in enumerate(bracket)}
    alive = {t: 1.0 for t in bracket}   # all teams have "reached" their round-1 match
    out = {t: [] for t in bracket}

    block = 1  # current match groups each span `block` teams per side
    while block < n:
        new_alive = {}
        for t in bracket:
            i = pos[t]
            # opponents are the teams in the sibling block of width `block`
            base = (i // block) * block
            sib_base = base + block if (i // block) % 2 == 0 else base - block
            opps = bracket[sib_base: sib_base + block]
            p_adv = alive[t] * sum(alive[o] * pwin[(t, o)] for o in opps)
            new_alive[t] = p_adv
        alive = new_alive
        for t in bracket:
            out[t].append(alive[t])
        block *= 2
    return out


# ----------------------------------------------------------------------------- model
def _pairwise_from_model(bracket, shootout=0.5):
    """Mac-only: P(a beats b in a tie) for every orderable pair, from the frozen model."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    import pickle
    from wc2026.models.poisson import predict_match_dc          # type: ignore
    from wc2026.simulation.engine import recalibrate_score_matrix  # type: ignore
    bundle = pickle.load(open(PROCESSED / "models" / "poisson_v1.pkl", "rb"))
    model, rho, conf = bundle["model"], bundle["dc_rho"], bundle["confederation_levels"]
    feats = pd.read_parquet(PROCESSED / "team_features.parquet")
    T = float(json.loads((PROCESSED / "calibration.json").read_text()).get("temperature", 1.0))

    def grid(a, b):
        pred = predict_match_dc(model, feats, a, b, rho, is_neutral=True,
                                is_competitive=True, confederation_levels=conf, max_goals=12)
        return recalibrate_score_matrix(pred["score_matrix"], T)

    pwin = {}
    teams = list(dict.fromkeys(bracket))
    for a in teams:
        for b in teams:
            if a == b or (a, b) in pwin:
                continue
            g = grid(a, b)
            p_home = float(np.tril(g, -1).sum())
            p_draw = float(np.trace(g))
            p_away = float(np.triu(g, 1).sum())
            s = p_home + p_draw + p_away
            p_home, p_draw, p_away = p_home / s, p_draw / s, p_away / s
            pa = p_home + p_draw * shootout       # a wins in reg, or draw then shootout
            pwin[(a, b)] = pa
            pwin[(b, a)] = 1.0 - pa
    return pwin


def _continent_breakdown(champ: dict) -> dict:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    try:
        from wc2026.data.confederations import confederation_of  # type: ignore
    except Exception:
        return {}
    by = {}
    for team, p in champ.items():
        c = confederation_of(team) or "Unknown"
        by[c] = by.get(c, 0.0) + p
    return dict(sorted(by.items(), key=lambda kv: -kv[1]))


def run(shootout: float) -> int:
    if not BRACKET.exists():
        print(f"[skip] {BRACKET.name} missing — create it from the actual R32 fixtures "
              f"in bracket order (see docstring). Live sim not run.")
        return 0
    b = json.loads(BRACKET.read_text())
    bracket = b.get("r32_order", [])
    if len(bracket) != 32:
        print(f"[skip] bracket has {len(bracket)}/32 teams — incomplete, so champion "
              f"numbers would be wrong. Fill r32_order (in bracket order) and re-run. "
              f"Live sim not run.")
        return 0
    pwin = _pairwise_from_model(bracket, shootout)
    reach = bracket_reach_probs(bracket, pwin)

    rows = []
    for t in bracket:
        d = {"team": t}
        d.update(dict(zip(ROUND_LABELS, reach[t])))
        rows.append(d)
    df = pd.DataFrame(rows).sort_values("champion", ascending=False)
    df.to_parquet(OUT_PARQUET, index=False)

    champ = dict(zip(df["team"], df["champion"]))
    cont = _continent_breakdown(champ)

    lines = ["# Live knockout probabilities", "",
             f"Source: actual bracket ({len(bracket)} teams) + frozen match model, "
             f"exact DP, shootout split {shootout}.", "",
             "## Champion / reach-round (top 16)", "",
             "| team | R16 | QF | SF | Final | Champion |", "|---|---|---|---|---|---|"]
    for _, r in df.head(16).iterrows():
        lines.append(f"| {r['team']} | {r['reach_R16']:.0%} | {r['reach_QF']:.0%} | "
                     f"{r['reach_SF']:.0%} | {r['reach_F']:.0%} | {r['champion']:.1%} |")
    lines += ["", "## Continent to win (sum of champion probs)", "",
              "| confederation | P(win) |", "|---|---|"]
    for c, p in cont.items():
        lines.append(f"| {c} | {p:.1%} |")
    lines += ["", f"_Champion probs sum to {df['champion'].sum():.3f} (should be ~1.0). "
              f"Eliminated teams should be absent / ~0%._"]
    OUT_MD.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nWrote {OUT_PARQUET} and {OUT_MD}")
    return 0


def _selftest() -> int:
    # 8-team bracket, all ties 50/50 -> every team champion prob = 1/8, reach_QF=1/2.
    teams = [f"T{i}" for i in range(8)]
    pwin = {(a, b): 0.5 for a in teams for b in teams if a != b}
    reach = bracket_reach_probs(teams, pwin)   # rounds: QF, SF, champion (8-team)
    champ = {t: reach[t][-1] for t in teams}
    assert all(abs(champ[t] - 1/8) < 1e-9 for t in teams), champ
    assert abs(reach["T0"][0] - 0.5) < 1e-9, reach["T0"]   # reach round 2 = win first tie
    assert abs(sum(champ.values()) - 1.0) < 1e-9

    # asymmetric: T0 beats everyone w.p. 0.9, others 50/50 among themselves.
    pwin2 = {}
    for a in teams:
        for b in teams:
            if a == b: continue
            pwin2[(a, b)] = 0.9 if a == "T0" else (0.1 if b == "T0" else 0.5)
    r2 = bracket_reach_probs(teams, pwin2)
    champ2 = {t: r2[t][-1] for t in teams}
    assert champ2["T0"] == max(champ2.values()) and champ2["T0"] > 0.5, champ2
    assert abs(sum(champ2.values()) - 1.0) < 1e-9, sum(champ2.values())
    print(f"[selftest] 8-team uniform: champion=1/8 each OK; "
          f"strong-team champion={champ2['T0']:.3f} (>0.5) OK; probs sum to 1.")
    print("[selftest] bracket DP verified.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shootout", type=float, default=0.5,
                    help="P(win | tie goes to ET/penalties); 0.5 = coin flip")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    raise SystemExit(_selftest() if a.selftest else run(a.shootout))
