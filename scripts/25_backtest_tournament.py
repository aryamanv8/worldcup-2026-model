"""
25_backtest_tournament.py

Tournament-level backtest: run the full simulator (recalibrated match model ->
Monte Carlo) on the 2010/14/18/22 World Cups and measure whether the simulated
round-progression probabilities matched what actually happened. Unlike the
match-level backtest (script 09), this exposes TOURNAMENT-level miscalibration --
specifically whether the model is too flat: under-rating eventual deep-runners
because a small per-match underconfidence compounds across seven knockout games.

Format note: 2010-2022 were 32-team (8 groups of 4 -> Round of 16 -> QF -> SF ->
Final), unlike 2026's 48-team format. So this uses a 32-team bracket, reusing the
engine's group/knockout primitives. The R16 cross-pairing is a CANONICAL
reconstruction (groups are detected from data without their real A-H letters), so
it's faithful for the calibration/flatness diagnostic but not the exact historical
bracket. Host advantage is ignored (all matches neutral) for simplicity.

What it reports
  - per WC: the actual champion's predicted champion probability and rank
  - pooled reliability: predicted vs actual frequency for each round (the
    flatness test -- if the model is compressed, high-probability favorites
    under-realize... no: favorites OVER-realize relative to the model's too-low
    probabilities, i.e. the reliability curve bends below the diagonal at the top)

Run: uv run python scripts/25_backtest_tournament.py

NOTE: this is the most reconstruction-heavy script in the project (it rebuilds
historical groups and rounds from raw match data). Built-in asserts will flag any
WC whose data doesn't fit the expected 64-match / 8-group structure.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

from wc2026.features.team_features import build_team_features
from wc2026.models.poisson import (
    filter_complete_features, pivot_to_long, prepare_design_matrix,
    fit_poisson, fit_dixon_coles_rho, predict_match_dc,
)
from wc2026.simulation.engine import (
    simulate_group, simulate_knockout_match, pair_for_next_round,
    recalibrate_score_matrix,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = PROJECT_ROOT / "data" / "processed"
N_SIMS = 10_000
SEED = 42

WORLD_CUPS = [
    ("2010", pd.Timestamp("2010-06-11"), pd.Timestamp("2010-07-11")),
    ("2014", pd.Timestamp("2014-06-12"), pd.Timestamp("2014-07-13")),
    ("2018", pd.Timestamp("2018-06-14"), pd.Timestamp("2018-07-15")),
    ("2022", pd.Timestamp("2022-11-20"), pd.Timestamp("2022-12-18")),
]
# Public facts (avoids penalty-shootout ambiguity in score data)
CHAMPIONS = {"2010": "Spain", "2014": "Germany", "2018": "France", "2022": "Argentina"}


def connected_groups(matches: pd.DataFrame) -> list[list[str]]:
    """Detect groups as connected components of the group-stage match graph."""
    adj = defaultdict(set)
    for _, m in matches.iterrows():
        a, b = str(m["home_team"]), str(m["away_team"])
        adj[a].add(b); adj[b].add(a)
    seen, comps = set(), []
    for t in adj:
        if t in seen:
            continue
        stack, comp = [t], []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x); comp.append(x)
            stack.extend(adj[x] - seen)
        comps.append(sorted(comp))
    return comps


def neutral_matrices(model, team_features, teams, rho, conf_levels, T):
    from itertools import combinations
    mats = {}
    for a, b in combinations(teams, 2):
        pred = predict_match_dc(model, team_features, a, b, rho=rho, is_neutral=True,
                                is_competitive=True, confederation_levels=conf_levels, max_goals=10)
        M = pred["score_matrix"]
        mats[(a, b)] = recalibrate_score_matrix(M.copy(), T)
        mats[(b, a)] = recalibrate_score_matrix(M.T.copy(), T)
    return mats


def simulate(groups, mats, rng):
    """One 32-team tournament -> dict of reached-round flags per team."""
    standings = {g: simulate_group(ts, mats, rng) for g, ts in groups.items()}
    gk = sorted(groups)  # group keys g0..g7
    W = [standings[g][0].team for g in gk]
    R = [standings[g][1].team for g in gk]
    advancers = set(W) | set(R)
    # canonical R16 cross-pairing
    pairs = [(W[0], R[1]), (W[2], R[3]), (W[4], R[5]), (W[6], R[7]),
             (W[1], R[0]), (W[3], R[2]), (W[5], R[4]), (W[7], R[6])]
    r16w = [simulate_knockout_match(a, b, mats, rng) for a, b in pairs]
    qfw = [simulate_knockout_match(a, b, mats, rng) for a, b in pair_for_next_round(r16w)]
    sfw = [simulate_knockout_match(a, b, mats, rng) for a, b in pair_for_next_round(qfw)]
    champ = simulate_knockout_match(sfw[0], sfw[1], mats, rng)
    return advancers, set(r16w), set(qfw), set(sfw), champ


def actual_rounds(wc_matches: pd.DataFrame):
    """Reconstruct who reached each round from the 64-match structure (by date)."""
    ms = wc_matches.sort_values("date").reset_index(drop=True)
    assert len(ms) == 64, f"expected 64 matches, got {len(ms)}"
    def teams_in(sl):
        s = set()
        for _, m in ms.iloc[sl].iterrows():
            s.add(str(m["home_team"])); s.add(str(m["away_team"]))
        return s
    return {
        "advance": teams_in(slice(48, 56)),       # 16 in R16 matches
        "reach_QF": teams_in(slice(56, 60)),       # 8
        "reach_SF": teams_in(slice(60, 62)),       # 4
        "reach_F": teams_in(slice(63, 64)),        # 2 finalists
    }


def main():
    results = pd.read_parquet(PROCESSED / "results.parquet")
    elo_history = pd.read_parquet(PROCESSED / "elo_history.parquet")
    training_matrix = pd.read_parquet(PROCESSED / "training_matrix.parquet")
    value_history = pd.read_parquet(PROCESSED / "country_value_history.parquet")
    T = 1.0
    cal = PROCESSED / "calibration.json"
    if cal.exists():
        T = float(json.loads(cal.read_text()).get("temperature", 1.0))
    print(f"Recalibration T = {T}\n")

    rng = np.random.default_rng(SEED)
    pooled = []   # (round, predicted_prob, actual 0/1) for reliability
    champ_rows = []

    for name, start, end in WORLD_CUPS:
        print(f"========== {name} ==========")
        snapshot = start - pd.Timedelta(days=1)
        train = filter_complete_features(training_matrix[training_matrix["date"] <= snapshot].copy())
        long = pivot_to_long(train)
        conf = sorted(set(long["attacker_confederation"]) | set(long["defender_confederation"]))
        X, y, _ = prepare_design_matrix(long, conf)
        model = fit_poisson(X, y)
        rho = fit_dixon_coles_rho(model, train, conf)

        wc = results[(results["tournament"] == "FIFA World Cup")
                     & (results["date"] >= start) & (results["date"] <= end)
                     ].dropna(subset=["home_score", "away_score"]).reset_index(drop=True)
        comps = connected_groups(wc.sort_values("date").head(48))
        assert len(comps) == 8 and all(len(c) == 4 for c in comps), \
            f"{name}: group reconstruction gave {[len(c) for c in comps]}"
        groups = {f"g{i}": c for i, c in enumerate(comps)}
        teams = [t for c in comps for t in c]

        feats = build_team_features(teams=teams, results=results, elo_history=elo_history,
                                    value_history=value_history, as_of=snapshot)
        mats = neutral_matrices(model, feats, teams, rho, conf, T)

        counts = defaultdict(lambda: defaultdict(int))
        for _ in range(N_SIMS):
            adv, r16w, qfw, sfw, champ = simulate(groups, mats, rng)
            for t in adv: counts[t]["advance"] += 1
            for t in r16w: counts[t]["reach_QF"] += 1
            for t in qfw: counts[t]["reach_SF"] += 1
            for t in sfw: counts[t]["reach_F"] += 1
            counts[champ]["champion"] += 1

        prob = {t: {k: counts[t][k] / N_SIMS for k in
                    ["advance", "reach_QF", "reach_SF", "reach_F", "champion"]} for t in teams}
        act = actual_rounds(wc)
        act["champion"] = {CHAMPIONS[name]}

        # champion headline
        cp = sorted(((prob[t]["champion"], t) for t in teams), reverse=True)
        champ_team = CHAMPIONS[name]
        rank = [t for _, t in cp].index(champ_team) + 1
        champ_rows.append({"wc": name, "champion": champ_team,
                           "model_champ_prob": prob[champ_team]["champion"],
                           "rank": rank, "top_prob": cp[0][0], "top_team": cp[0][1]})
        print(f"  actual champion {champ_team}: model gave {prob[champ_team]['champion']:.1%} "
              f"(rank {rank} of 32; model favorite {cp[0][1]} at {cp[0][0]:.1%})")

        for t in teams:
            for r in ["advance", "reach_QF", "reach_SF", "reach_F", "champion"]:
                pooled.append((r, prob[t][r], 1.0 if t in act[r] else 0.0))

    # ---- headline: flatness on champions ------------------------------------
    cdf = pd.DataFrame(champ_rows)
    print("\n=== Did the model back the actual champions? ===")
    print(cdf.to_string(index=False))
    print(f"\n  mean champion prob assigned to the 4 actual winners: "
          f"{cdf['model_champ_prob'].mean():.1%}")
    print(f"  actual champion was model's #1 favorite in {sum(cdf['rank']==1)}/4 WCs, "
          f"top-3 in {sum(cdf['rank']<=3)}/4")

    # ---- reliability (the compression test) ---------------------------------
    pdf = pd.DataFrame(pooled, columns=["round", "pred", "actual"])
    print("\n=== Reliability by predicted-probability bin (all rounds pooled) ===")
    print("  if the model is too flat, actual > predicted in the high bins "
          "(favorites realize more than the model said)")
    bins = [0, .05, .15, .30, .50, .75, 1.01]
    pdf["bin"] = pd.cut(pdf["pred"], bins)
    rel = pdf.groupby("bin", observed=True).agg(
        n=("actual", "size"), mean_pred=("pred", "mean"), actual_freq=("actual", "mean")).reset_index()
    rel["gap"] = rel["actual_freq"] - rel["mean_pred"]
    print(rel.to_string(index=False))

    out = PROCESSED / "tournament_backtest.parquet"
    pdf.drop(columns=["bin"]).to_parquet(out, index=False)
    print(f"\n[save] {out}")


if __name__ == "__main__":
    main() 