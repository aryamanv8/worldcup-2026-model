"""
Fetches and parses historical international football match results.

Source: github.com/martj42/international_results
A public mirror of the well-known Kaggle dataset 'International football
results from 1872 to date' by Mart Jürisoo. We use the GitHub mirror
because it does not require Kaggle authentication.
"""
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

BASE_URL = "https://raw.githubusercontent.com/martj42/international_results/master"

FILES = {
    "results": "results.csv",
    "shootouts": "shootouts.csv",
    "goalscorers": "goalscorers.csv",
}


def download_raw_data(raw_dir: Path) -> dict[str, Path]:
    """
    Downloads the three source CSVs into the given raw directory.

    Args:
        raw_dir: Directory to save raw CSVs. Created if it doesn't exist.

    Returns:
        Mapping of logical name -> local path on disk.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    for name, filename in tqdm(FILES.items(), desc="Downloading"):
        url = f"{BASE_URL}/{filename}"
        local_path = raw_dir / filename

        response = requests.get(url, timeout=30)
        response.raise_for_status()
        local_path.write_bytes(response.content)

        paths[name] = local_path

    return paths


def load_results(raw_dir: Path) -> pd.DataFrame:
    """
    Loads the match results CSV with typed columns.

    Columns:
        date: datetime, match date
        home_team, away_team: str, team names
        home_score, away_score: int, full-time score (no extra time / pens)
        tournament: str, competition name (e.g., 'Friendly', 'FIFA World Cup qualification')
        city, country: str, match location
        neutral: bool, whether played at a neutral venue
    """
    df = pd.read_csv(
        raw_dir / "results.csv",
        parse_dates=["date"],
        dtype={
            "home_team": "string",
            "away_team": "string",
            "tournament": "string",
            "city": "string",
            "country": "string",
            "neutral": "bool",
        },
    )
    return df


def load_shootouts(raw_dir: Path) -> pd.DataFrame:
    """
    Loads penalty shootout outcomes for matches that went to PKs.
    Important for knockout match modeling — pens are a separate stochastic
    process from open play and we'll model them separately.
    """
    return pd.read_csv(raw_dir / "shootouts.csv", parse_dates=["date"])


def load_goalscorers(raw_dir: Path) -> pd.DataFrame:
    """
    Loads goalscorer-level data: who scored, what minute, own goals, penalties.
    Useful later for player-level features and goal-timing analysis.
    """
    return pd.read_csv(raw_dir / "goalscorers.csv", parse_dates=["date"])