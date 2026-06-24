# Gemini prompt — fetch WC 2018/2022 totals + BTTS closing odds

Copy everything in the box below into Gemini. Upload (or paste) the file
`wc_goals_odds_template.csv` alongside it. Use a Gemini mode with web access /
Deep Research so it can pull from real historical-odds sites rather than memory.

---

You are a careful sports-data researcher. I am giving you a CSV template
(`wc_goals_odds_template.csv`) with 128 rows — every match of the 2018 and 2022
FIFA World Cups. The columns `wc, date, home_team, away_team` are already filled and
**must not be changed**. Your job is to fill in six odds columns for each match
using REAL historical bookmaker data:

- `over15`  — decimal closing odds for OVER 1.5 total goals
- `under15` — decimal closing odds for UNDER 1.5 total goals
- `btts_yes`— decimal closing odds for BOTH TEAMS TO SCORE = YES
- `btts_no` — decimal closing odds for BOTH TEAMS TO SCORE = NO
- `over25`  — decimal closing odds for OVER 2.5 total goals
- `under25` — decimal closing odds for UNDER 2.5 total goals

Rules — follow exactly:

1. **Use real, sourced data only.** Pull from reputable historical-odds archives
   such as oddsportal.com, betexplorer.com, or football-data archives. Prefer the
   market **closing** line (kickoff); if only an average/pre-match line is
   available, use that and note it.
2. **Never invent or estimate odds.** If you cannot find a real value for a cell,
   leave it **blank**. A blank cell is correct and useful; a guessed number is
   harmful. Do not fill a cell just to be complete.
3. **Decimal odds only**, using a dot decimal point (e.g. `1.73`, `2.10`). Convert
   any fractional/American odds you find to decimal. Over/under and BTTS are
   two-outcome markets, so each pair (e.g. `over15`+`under15`) should be two decimal
   numbers greater than 1.0 whose implied probabilities sum to a bit more than 1
   (the bookmaker margin) — sanity-check this.
4. **Keep team names and dates exactly as given.** Do not rename "United States",
   "South Korea", "Iran", "Ivory Coast", "Turkey", etc. Match rows by the
   (date, home_team, away_team) already in the template. If a row's home/away are
   reversed on your source, keep MY orientation and map the odds accordingly (note:
   over/under and BTTS are symmetric, so orientation doesn't change them).
5. **Cite your sources.** For each tournament (or each source site you used), give
   me the URL(s) so I can verify. If a particular match's odds came from a different
   source, note it.
6. **Flag low-confidence rows.** After the table, list any matches where you were
   unsure or had to use a non-closing line.

Output:

- Return the **completed CSV** with the same columns and all 128 rows, ready to save
  as `wc_goals_odds.csv`. Keep blanks where you had no real data.
- Then a short **coverage summary**: how many of the 128 matches you filled for each
  market, and your source URLs.

Do not summarize the matches or add commentary inside the CSV — just the data. Begin.

---

## After Gemini returns the data

1. Save its CSV as `data/raw/wc_goals_odds.csv` (same folder as this prompt).
2. Spot-check 3–4 rows against the cited source — LLMs can still get odds wrong even
   when told not to. If many cells look invented (e.g. suspiciously round, or
   over15/under15 implying <1.0 or >1.3 total probability), don't trust it.
3. Tell me it's saved and I'll run `scripts/31_backtest_derived_strategy.py` and read
   the P&L + fragility output directly from the folder.

> Reality check: even a good prompt can't make an LLM reliable on exact historical
> odds. If Gemini's coverage is thin or looks fabricated, the better path is
> downloading directly from oddsportal/betexplorer match pages — I can write that
> step-by-step instead.
