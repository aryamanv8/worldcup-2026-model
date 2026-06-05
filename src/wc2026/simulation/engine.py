"""
Monte Carlo tournament simulator for the 2026 FIFA World Cup.

Three-stage pipeline:
  1. Pre-compute score matrices for every possible matchup (1,128 pairs).
  2. Simulate one tournament: group stage -> R32 -> R16 -> QF -> SF -> Final.
  3. Repeat N times, aggregate per-team round-progression probabilities.

NOTE on bracket simplifications:
- The 2026 R32 bracket has complex slot-assignment rules for the 8 best
  third-place teams. We use a simplified deterministic pairing that preserves
  structural integrity but is not FIFA-exact. See build_r32_bracket() for
  details.
- Knockout matches resolve at 90 minutes; draws go to a 50/50 coin flip
  representing extra time + penalties.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from tqdm import tqdm

from wc2026.models.poisson import predict_match_dc


GROUP_ORDER = list("ABCDEFGHIJKL")
HOST_TEAMS = {"Mexico", "Canada", "United States"}
HOST_GROUP = {"Mexico": "A", "Canada": "B", "United States": "D"}


@dataclass
class GroupStanding:
    """Tracks one team's group-stage performance."""
    team: str
    points: int = 0
    matches_played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0

    @property
    def goal_diff(self) -> int:
        return self.goals_for - self.goals_against

    def add_result(self, gf: int, ga: int) -> None:
        self.matches_played += 1
        self.goals_for += gf
        self.goals_against += ga
        if gf > ga:
            self.wins += 1
            self.points += 3
        elif gf < ga:
            self.losses += 1
        else:
            self.draws += 1
            self.points += 1


# --- Score matrix pre-computation ------------------------------------------

def precompute_score_matrices(
    fitted_model,
    team_features: pd.DataFrame,
    teams: List[str],
    rho: float,
    confederation_levels: List[str],
    groups: Dict[str, List[str]],
    max_goals: int = 10,
) -> Dict[Tuple[str, str], np.ndarray]:
    """
    Compute and cache the joint score distribution for every unordered pair
    of teams. Returns dict keyed by (team_a, team_b) where order matters:
    the matrix's row index is team_a's goals, column is team_b's goals.

    For host-country group matches, the host gets home advantage. All other
    matches (including all knockouts) are computed with is_neutral=True.
    """
    matrices: Dict[Tuple[str, str], np.ndarray] = {}

    # Determine which fixtures involve hosts (these are non-neutral)
    host_group_fixtures: set[Tuple[str, str]] = set()
    for host, group in HOST_GROUP.items():
        if host in groups[group]:
            for opp in groups[group]:
                if opp != host:
                    host_group_fixtures.add((host, opp))

    pairs = list(combinations(teams, 2))
    for team_a, team_b in tqdm(pairs, desc="  Pre-computing score matrices"):
        # Symmetric (neutral) matrix
        neutral_pred = predict_match_dc(
            fitted_model=fitted_model,
            team_features=team_features,
            home_team=team_a,
            away_team=team_b,
            rho=rho,
            is_neutral=True,
            is_competitive=True,
            confederation_levels=confederation_levels,
            max_goals=max_goals,
        )
        matrices[(team_a, team_b)] = neutral_pred["score_matrix"].copy()
        matrices[(team_b, team_a)] = neutral_pred["score_matrix"].T.copy()

        # Host-country group matches: recompute with host as the home team
        if (team_a, team_b) in host_group_fixtures:
            host_pred = predict_match_dc(
                fitted_model=fitted_model,
                team_features=team_features,
                home_team=team_a,
                away_team=team_b,
                rho=rho,
                is_neutral=False,
                is_competitive=True,
                confederation_levels=confederation_levels,
                max_goals=max_goals,
            )
            matrices[(team_a, team_b)] = host_pred["score_matrix"].copy()
            matrices[(team_b, team_a)] = host_pred["score_matrix"].T.copy()
        if (team_b, team_a) in host_group_fixtures:
            host_pred = predict_match_dc(
                fitted_model=fitted_model,
                team_features=team_features,
                home_team=team_b,
                away_team=team_a,
                rho=rho,
                is_neutral=False,
                is_competitive=True,
                confederation_levels=confederation_levels,
                max_goals=max_goals,
            )
            matrices[(team_b, team_a)] = host_pred["score_matrix"].copy()
            matrices[(team_a, team_b)] = host_pred["score_matrix"].T.copy()

    return matrices


# --- Sampling --------------------------------------------------------------

def sample_score(
    score_matrix: np.ndarray,
    rng: np.random.Generator,
) -> Tuple[int, int]:
    """Sample a (home_goals, away_goals) tuple from the joint distribution."""
    flat = score_matrix.ravel()
    flat = flat / flat.sum()
    idx = rng.choice(len(flat), p=flat)
    i, j = np.unravel_index(idx, score_matrix.shape)
    return int(i), int(j)


# --- Group stage -----------------------------------------------------------

def simulate_group(
    teams: List[str],
    score_matrices: Dict[Tuple[str, str], np.ndarray],
    rng: np.random.Generator,
) -> List[GroupStanding]:
    """
    Simulate one group's 6 round-robin matches.

    Returns standings sorted by:
      1. Points (desc)
      2. Goal difference (desc)
      3. Goals scored (desc)
      4. Random tiebreak
    """
    standings = {t: GroupStanding(t) for t in teams}

    for t1, t2 in combinations(teams, 2):
        # The matrix at key (t1, t2) has t1's goals as rows, t2's as columns
        sm = score_matrices[(t1, t2)]
        g1, g2 = sample_score(sm, rng)
        standings[t1].add_result(g1, g2)
        standings[t2].add_result(g2, g1)

    ranked = sorted(
        standings.values(),
        key=lambda s: (-s.points, -s.goal_diff, -s.goals_for, rng.random()),
    )
    return ranked


# --- Best third-place selection --------------------------------------------

def best_thirds(
    group_standings: Dict[str, List[GroupStanding]],
    n: int = 8,
    rng: np.random.Generator | None = None,
) -> List[Tuple[str, GroupStanding]]:
    """
    Identify the best n third-placed teams across all groups.
    Returns list of (group_letter, GroupStanding) tuples, sorted best-first.
    """
    rng = rng or np.random.default_rng()
    thirds = [(g, standings[2]) for g, standings in group_standings.items()]
    thirds.sort(
        key=lambda x: (
            -x[1].points,
            -x[1].goal_diff,
            -x[1].goals_for,
            rng.random(),
        )
    )
    return thirds[:n]


# --- R32 bracket (simplified) ----------------------------------------------

def build_r32_bracket(
    group_winners: Dict[str, str],
    group_runners_up: Dict[str, str],
    best_thirds_list: List[Tuple[str, GroupStanding]],
) -> List[Tuple[str, str]]:
    """
    Simplified R32 pairing — NOT FIFA-exact.

    Structure preserved:
      - 12 group winners advance
      - 12 group runners-up advance
      - 8 best third-place teams advance
      - 8 matches are winner-vs-third
      - 4 matches are winner-vs-runnerup
      - 4 matches are runnerup-vs-runnerup
      - No same-group rematches

    Pairing rule used:
      - Winners A-H face the 8 best thirds (in order of third-place quality)
      - Winners I-L face runners-up A-D
      - Runners-up E-L pair among themselves consecutively
      - When this would cause a same-group rematch, swap with the next slot
    """
    winners_in_order = [group_winners[g] for g in GROUP_ORDER]
    runners_in_order = [group_runners_up[g] for g in GROUP_ORDER]
    third_teams = [s.team for _, s in best_thirds_list]
    third_groups = [g for g, _ in best_thirds_list]

    team_to_group: Dict[str, str] = {}
    for g in GROUP_ORDER:
        team_to_group[group_winners[g]] = g
        team_to_group[group_runners_up[g]] = g
    for g, s in best_thirds_list:
        team_to_group[s.team] = g

    pairings: List[Tuple[str, str]] = []

    # 8 W vs T matches: winners A-H paired with thirds 1-8.
    # Swap any same-group rematches with the next available third.
    paired_thirds = list(third_teams)  # mutable copy
    for i in range(8):
        w = winners_in_order[i]
        # Find first third not from same group as winner
        for j, t in enumerate(paired_thirds):
            if team_to_group[t] != team_to_group[w]:
                pairings.append((w, t))
                paired_thirds.pop(j)
                break
        else:
            # All remaining thirds are from same group as w — shouldn't happen
            # in practice but handle gracefully
            pairings.append((w, paired_thirds.pop(0)))

    # 4 W vs R matches: winners I-L paired with runners-up A-D
    # Swap any same-group rematches
    available_runners = list(runners_in_order)
    for i in range(8, 12):
        w = winners_in_order[i]
        for j, r in enumerate(available_runners):
            if team_to_group[r] != team_to_group[w]:
                pairings.append((w, r))
                available_runners.pop(j)
                break
        else:
            pairings.append((w, available_runners.pop(0)))

    # 4 R vs R matches: pair remaining 8 runners-up
    while len(available_runners) >= 2:
        r1 = available_runners.pop(0)
        for j, r2 in enumerate(available_runners):
            if team_to_group[r1] != team_to_group[r2]:
                pairings.append((r1, r2))
                available_runners.pop(j)
                break
        else:
            pairings.append((r1, available_runners.pop(0)))

    assert len(pairings) == 16, f"Expected 16 R32 pairings, got {len(pairings)}"
    return pairings


# --- Knockout matches -------------------------------------------------------

def simulate_knockout_match(
    team_a: str,
    team_b: str,
    score_matrices: Dict[Tuple[str, str], np.ndarray],
    rng: np.random.Generator,
) -> str:
    """
    Simulate one knockout match. Returns the winner's name.
    If draw at 90 min, simulate ET/penalties as a 50/50.
    """
    sm = score_matrices[(team_a, team_b)]
    g_a, g_b = sample_score(sm, rng)
    if g_a > g_b:
        return team_a
    elif g_b > g_a:
        return team_b
    else:
        return team_a if rng.random() < 0.5 else team_b


def pair_for_next_round(advancers: List[str]) -> List[Tuple[str, str]]:
    """Bracket pairing: adjacent winners advance to face each other."""
    return [(advancers[i], advancers[i + 1]) for i in range(0, len(advancers), 2)]


# --- One full tournament simulation ----------------------------------------

@dataclass
class TournamentResult:
    """Per-team round-by-round progression."""
    group_position: Dict[str, int] = field(default_factory=dict)
    won_group: Dict[str, bool] = field(default_factory=dict)
    reached_R32: Dict[str, bool] = field(default_factory=dict)
    reached_R16: Dict[str, bool] = field(default_factory=dict)
    reached_QF: Dict[str, bool] = field(default_factory=dict)
    reached_SF: Dict[str, bool] = field(default_factory=dict)
    reached_F: Dict[str, bool] = field(default_factory=dict)
    won_tournament: Dict[str, bool] = field(default_factory=dict)


def simulate_one_tournament(
    groups: Dict[str, List[str]],
    score_matrices: Dict[Tuple[str, str], np.ndarray],
    rng: np.random.Generator,
) -> TournamentResult:
    """One full tournament simulation, group stage through final."""
    # Group stage
    group_standings = {g: simulate_group(teams, score_matrices, rng)
                       for g, teams in groups.items()}

    group_winners = {g: standings[0].team for g, standings in group_standings.items()}
    group_runners_up = {g: standings[1].team for g, standings in group_standings.items()}
    best_thirds_list = best_thirds(group_standings, n=8, rng=rng)
    advancing_thirds = {s.team for _, s in best_thirds_list}

    all_R32_teams = set(group_winners.values()) | set(group_runners_up.values()) | advancing_thirds

    # R32
    r32_pairings = build_r32_bracket(group_winners, group_runners_up, best_thirds_list)
    r16_teams = [simulate_knockout_match(a, b, score_matrices, rng)
                 for a, b in r32_pairings]

    # R16
    r16_pairings = pair_for_next_round(r16_teams)
    qf_teams = [simulate_knockout_match(a, b, score_matrices, rng)
                for a, b in r16_pairings]

    # QF
    qf_pairings = pair_for_next_round(qf_teams)
    sf_teams = [simulate_knockout_match(a, b, score_matrices, rng)
                for a, b in qf_pairings]

    # SF
    sf_pairings = pair_for_next_round(sf_teams)
    finalists = [simulate_knockout_match(a, b, score_matrices, rng)
                 for a, b in sf_pairings]

    # Final
    champion = simulate_knockout_match(finalists[0], finalists[1], score_matrices, rng)

    # Build result
    result = TournamentResult()
    for g, standings in group_standings.items():
        for rank, s in enumerate(standings):
            result.group_position[s.team] = rank + 1
            result.won_group[s.team] = (rank == 0)

    all_teams_flat = [t for teams in groups.values() for t in teams]
    for t in all_teams_flat:
        result.reached_R32[t] = (t in all_R32_teams)
        result.reached_R16[t] = (t in r16_teams)
        result.reached_QF[t] = (t in qf_teams)
        result.reached_SF[t] = (t in sf_teams)
        result.reached_F[t] = (t in finalists)
        result.won_tournament[t] = (t == champion)

    return result


# --- Multi-simulation aggregation -------------------------------------------

def run_simulations(
    n_sims: int,
    groups: Dict[str, List[str]],
    score_matrices: Dict[Tuple[str, str], np.ndarray],
    seed: int = 42,
) -> pd.DataFrame:
    """
    Run N tournament simulations and aggregate per-team probabilities.

    Returns a DataFrame with one row per team, columns:
      team, p_win_group, p_advance_from_group (= p_reach_R32),
      p_reach_R16, p_reach_QF, p_reach_SF, p_reach_F, p_win_tournament
    """
    rng = np.random.default_rng(seed)

    # Counters
    counters: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for _ in tqdm(range(n_sims), desc="  Simulating tournaments"):
        result = simulate_one_tournament(groups, score_matrices, rng)
        for team, won in result.won_group.items():
            if won:
                counters[team]["win_group"] += 1
        for team, reached in result.reached_R32.items():
            if reached:
                counters[team]["reach_R32"] += 1
        for team, reached in result.reached_R16.items():
            if reached:
                counters[team]["reach_R16"] += 1
        for team, reached in result.reached_QF.items():
            if reached:
                counters[team]["reach_QF"] += 1
        for team, reached in result.reached_SF.items():
            if reached:
                counters[team]["reach_SF"] += 1
        for team, reached in result.reached_F.items():
            if reached:
                counters[team]["reach_F"] += 1
        for team, won in result.won_tournament.items():
            if won:
                counters[team]["win_tournament"] += 1

    all_teams = [t for teams in groups.values() for t in teams]
    rows = []
    for team in all_teams:
        c = counters[team]
        rows.append({
            "team": team,
            "p_win_group": c["win_group"] / n_sims,
            "p_advance_from_group": c["reach_R32"] / n_sims,
            "p_reach_R16": c["reach_R16"] / n_sims,
            "p_reach_QF": c["reach_QF"] / n_sims,
            "p_reach_SF": c["reach_SF"] / n_sims,
            "p_reach_F": c["reach_F"] / n_sims,
            "p_win_tournament": c["win_tournament"] / n_sims,
        })

    return pd.DataFrame(rows).sort_values("p_win_tournament", ascending=False).reset_index(drop=True)
