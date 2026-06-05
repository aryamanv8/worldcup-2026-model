"""
Confederation mapping for the 48 teams qualified for the 2026 World Cup.
Used as a categorical feature in the match-level model to capture any
systematic inter-confederation calibration bias in our Elo ratings.
"""

CONFEDERATIONS: dict[str, str] = {
    # UEFA (Europe) - 16 teams
    "Spain": "UEFA",
    "England": "UEFA",
    "France": "UEFA",
    "Germany": "UEFA",
    "Portugal": "UEFA",
    "Netherlands": "UEFA",
    "Belgium": "UEFA",
    "Croatia": "UEFA",
    "Switzerland": "UEFA",
    "Norway": "UEFA",
    "Sweden": "UEFA",
    "Austria": "UEFA",
    "Czech Republic": "UEFA",
    "Scotland": "UEFA",
    "Bosnia and Herzegovina": "UEFA",
    "Turkey": "UEFA",

    # CONMEBOL (South America) - 6 teams
    "Brazil": "CONMEBOL",
    "Argentina": "CONMEBOL",
    "Uruguay": "CONMEBOL",
    "Colombia": "CONMEBOL",
    "Ecuador": "CONMEBOL",
    "Paraguay": "CONMEBOL",

    # CONCACAF (North/Central America + Caribbean) - 6 teams
    "United States": "CONCACAF",
    "Mexico": "CONCACAF",
    "Canada": "CONCACAF",
    "Haiti": "CONCACAF",
    "Panama": "CONCACAF",
    "Curaçao": "CONCACAF",

    # CAF (Africa) - 9 teams
    "Morocco": "CAF",
    "Senegal": "CAF",
    "Egypt": "CAF",
    "Ivory Coast": "CAF",
    "Cape Verde": "CAF",
    "Algeria": "CAF",
    "Ghana": "CAF",
    "Tunisia": "CAF",
    "South Africa": "CAF",
    "DR Congo": "CAF",

    # AFC (Asia) - 9 teams
    "Japan": "AFC",
    "South Korea": "AFC",
    "Iran": "AFC",
    "Iraq": "AFC",
    "Saudi Arabia": "AFC",
    "Australia": "AFC",
    "Uzbekistan": "AFC",
    "Qatar": "AFC",
    "Jordan": "AFC",

    # OFC (Oceania) - 1 team
    "New Zealand": "OFC",
}


def confederation_of(team: str) -> str:
    """Returns the confederation code for a team, or 'OTHER' if not mapped."""
    return CONFEDERATIONS.get(team, "OTHER")