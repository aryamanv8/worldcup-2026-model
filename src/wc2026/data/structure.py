"""
Loads the 2026 FIFA World Cup tournament structure (groups, format)
from a YAML config file.
"""
from itertools import combinations
from pathlib import Path
from typing import Any

import yaml


def load_structure(yaml_path: Path) -> dict[str, Any]:
    """Loads the full structure dict from YAML and validates basic shape."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    groups = data["groups"]

    if len(groups) != 12:
        raise ValueError(f"Expected 12 groups, got {len(groups)}: {list(groups)}")
    for letter, teams in groups.items():
        if len(teams) != 4:
            raise ValueError(f"Group {letter} has {len(teams)} teams, expected 4")

    return data


def load_groups(yaml_path: Path) -> dict[str, list[str]]:
    """Loads just the group composition: {group_letter: [team1, team2, team3, team4]}."""
    return load_structure(yaml_path)["groups"]


def all_teams(groups: dict[str, list[str]]) -> list[str]:
    """Returns a flat list of all 48 teams across all groups."""
    return [team for teams in groups.values() for team in teams]


def group_of(team: str, groups: dict[str, list[str]]) -> str:
    """Returns the group letter that a team is in. Raises if not found."""
    for letter, teams in groups.items():
        if team in teams:
            return letter
    raise KeyError(f"Team {team!r} not found in any group")


def group_fixtures(group_teams: list[str]) -> list[tuple[str, str]]:
    """All 6 unique pairings in a group of 4 (a round-robin)."""
    return list(combinations(group_teams, 2))


def all_group_fixtures(groups: dict[str, list[str]]) -> list[dict]:
    """All 72 group-stage matches (6 per group × 12 groups), annotated by group."""
    fixtures = []
    for letter, teams in groups.items():
        for t1, t2 in group_fixtures(teams):
            fixtures.append({"group": letter, "team1": t1, "team2": t2})
    return fixtures