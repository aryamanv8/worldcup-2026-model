"""
Diagnostic: examine match-level predictions for suspicious groups.

For each fixture in the focus groups, prints:
  - Model lambdas (expected goals)
  - Model 1X2 probabilities
  - Elo-implied expected score (baseline)
  - Delta between model and Elo
  - Each team's "form" features for context

The aim: identify whether the model's tournament-level anomalies
(over-priced Austria/Belgium/Norway; under-priced France/Spain/England)
are driven by match-level rating errors or by structural bracket effects.

Run from the project root:
    uv run python scripts/11_diagnose_predictions.py
"""
import pickle
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from wc2026.data.structure import load_groups
from wc2026.models.poisson import predict_match_dc

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROCESSED_DIR / "models"
STRUCTURE_PATH = PROJECT_ROOT / "data" / "external" / "wc2026_structure.yaml"

FOCUS_GROUPS = ["H", "I", "J", "L"]


def elo_implied_score(elo_a: float, elo_b: float, home_adv: float = 0.0) -> float:
    """Elo-implied expected match score (1=win, 0.5=draw, 0=loss) for team A."""
    diff = elo_a - elo_b + home_adv
    return 1.0 / (1.0 + 10.0 ** (-diff / 400.0))


def model_expected_score(probs: dict) -> float:
    """Convert P(H/D/A) to expected match points (using W=1, D=0.5, L=0)."""
    return probs["home"] + 0.5 * probs["draw"]


def main() -> None:
    print("Loading model and data...")
    with open(MODELS_DIR / "poisson_v1.pkl", "rb") as f:
        bundle = pickle.load(f)
    model = bundle["model"]
    rho = bundle["dc_rho"]
    confederation_levels = bundle["confederation_levels"]

    team_features = pd.read_parquet(PROCESSED_DIR / "team_features.parquet")
    elo_latest = pd.read_parquet(PROCESSED_DIR / "elo_latest.parquet")
    elo_map = dict(zip(elo_latest["team"], elo_latest["elo"]))
    groups = load_groups(STRUCTURE_PATH)
    tournament_probs = pd.read_parquet(PROCESSED_DIR / "tournament_probs.parquet")
    tp_map = tournament_probs.set_index("team")

    for g_letter in FOCUS_GROUPS:
        teams = groups[g_letter]
        print(f"\n{'='*100}")
        print(f"GROUP {g_letter}")
        print(f"{'='*100}")

        # Team-level summary
        print(f"\n{'Team':<25} {'Elo':>6} {'GF/m':>6} {'GA/m':>6} {'WinR':>6} "
              f"{'p_win_grp':>10} {'p_advance':>10} {'p_win_tourny':>12}")
        for t in teams:
            tf = team_features[team_features["team"] == t].iloc[0]
            tp = tp_map.loc[t]
            print(f"  {t:<23} {elo_map[t]:>6.0f} "
                  f"{tf['gf_per_match_12mo']:>6.2f} {tf['ga_per_match_12mo']:>6.2f} "
                  f"{tf['win_rate_12mo']:>6.1%} "
                  f"{tp['p_win_group']:>10.1%} "
                  f"{tp['p_advance_from_group']:>10.1%} "
                  f"{tp['p_win_tournament']:>12.2%}")

        # All 6 fixtures with comparisons
        print(f"\n{'Fixture':<48} {'λ_h':>5} {'λ_a':>5} "
              f"{'M_P(H)':>7} {'M_P(D)':>7} {'M_P(A)':>7} "
              f"{'M_E':>5} {'Elo_E':>5} {'Δ':>6}")
        print("-" * 110)
        for t1, t2 in combinations(teams, 2):
            pred = predict_match_dc(
                fitted_model=model,
                team_features=team_features,
                home_team=t1,
                away_team=t2,
                rho=rho,
                is_neutral=True,
                is_competitive=True,
                confederation_levels=confederation_levels,
            )
            m_e = model_expected_score(pred["probs"])
            elo_e = elo_implied_score(elo_map[t1], elo_map[t2])
            delta = m_e - elo_e
            sign = "+" if delta > 0 else ""
            print(f"  {t1[:21]:<21} vs {t2[:21]:<21}  "
                  f"{pred['lambda_home']:5.2f} {pred['lambda_away']:5.2f}  "
                  f"{pred['probs']['home']:6.1%} {pred['probs']['draw']:6.1%} {pred['probs']['away']:6.1%}  "
                  f"{m_e:5.2f} {elo_e:5.2f}  {sign}{delta:5.2f}")

    # Headline summary: where does the model diverge most from Elo?
    print(f"\n{'='*100}")
    print("LARGEST MODEL−ELO DELTAS ACROSS ALL 48 WC TEAMS' FIXTURES")
    print(f"{'='*100}")
    print("This shows where the model rates teams meaningfully differently from raw Elo.\n")

    all_teams = [t for ts in groups.values() for t in ts]
    rows = []
    for t1, t2 in combinations(all_teams, 2):
        pred = predict_match_dc(
            fitted_model=model,
            team_features=team_features,
            home_team=t1,
            away_team=t2,
            rho=rho,
            is_neutral=True,
            is_competitive=True,
            confederation_levels=confederation_levels,
        )
        m_e = model_expected_score(pred["probs"])
        elo_e = elo_implied_score(elo_map[t1], elo_map[t2])
        rows.append({
            "team_a": t1, "team_b": t2,
            "elo_a": elo_map[t1], "elo_b": elo_map[t2],
            "model_E_a": m_e,
            "elo_E_a": elo_e,
            "delta_a": m_e - elo_e,
        })
    delta_df = pd.DataFrame(rows)

    print("Top 10 matchups where model BOOSTS team_a vs. Elo:")
    top_pos = delta_df.nlargest(10, "delta_a")
    for _, r in top_pos.iterrows():
        print(f"  {r['team_a']:<22} vs {r['team_b']:<22} "
              f"Elo {r['elo_a']:.0f} vs {r['elo_b']:.0f}  "
              f"model_E={r['model_E_a']:.2f}  Elo_E={r['elo_E_a']:.2f}  Δ=+{r['delta_a']:.2f}")

    print("\nTop 10 matchups where model SUPPRESSES team_a vs. Elo:")
    top_neg = delta_df.nsmallest(10, "delta_a")
    for _, r in top_neg.iterrows():
        print(f"  {r['team_a']:<22} vs {r['team_b']:<22} "
              f"Elo {r['elo_a']:.0f} vs {r['elo_b']:.0f}  "
              f"model_E={r['model_E_a']:.2f}  Elo_E={r['elo_E_a']:.2f}  Δ={r['delta_a']:+.2f}")


if __name__ == "__main__":
    main()