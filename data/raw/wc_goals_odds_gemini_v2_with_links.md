# Gemini prompt v2 — read these links, output the CSV

## The links (entry points that list every match + its odds)

**OddsPortal (recommended — has a clean BTTS tab per match):**
- 2022 results: https://www.oddsportal.com/football/world/world-cup-2022/results/
- 2018 results: https://www.oddsportal.com/football/world/world-cup-2018/results/
- On any match page, the BTTS market is the **"Both Teams to Score"** tab
  (URL form: append `#bts;2` to the match URL, e.g. `.../argentina-france-xxxx/#bts;2`).

**BetExplorer (same source as our 1X2 file — fallback / cross-check):**
- 2022 results: https://www.betexplorer.com/football/world/world-cup-2022/results/
- 2018 results: https://www.betexplorer.com/football/world/world-cup-2018/results/
- On any match page, open the **"BTTS"** odds tab and read the **Average ("Ø")** row.

Upload `wc_goals_odds_template.csv` (128 matches, names/dates already filled) with the
prompt below. Use a Gemini mode that can browse the web (Deep Research / with URL access).

---

## Prompt (paste into Gemini)

You are a careful sports-data researcher with web browsing enabled. I am giving you:
(1) a CSV template `wc_goals_odds_template.csv` listing all 128 matches of the 2018 and
2022 FIFA World Cups, with `wc, date, home_team, away_team` already filled and NOT to be
changed; and (2) results-page links that list every one of those matches.

Links to work from:
- OddsPortal 2022: https://www.oddsportal.com/football/world/world-cup-2022/results/
- OddsPortal 2018: https://www.oddsportal.com/football/world/world-cup-2018/results/
- (fallback) BetExplorer 2022: https://www.betexplorer.com/football/world/world-cup-2022/results/
- (fallback) BetExplorer 2018: https://www.betexplorer.com/football/world/world-cup-2018/results/

Your task: for each match in the template, **open that match's page from the links above
and read its "Both Teams to Score" (BTTS) market**, then fill two columns:
- `btts_yes` — decimal odds for BTTS = YES
- `btts_no`  — decimal odds for BTTS = NO
Prefer the **closing** line; if only an average is shown (BetExplorer "Ø" row), use that.

Rules — follow exactly:
1. **Actually open the pages. Do not answer from memory.** Navigate the results page,
   click into each match, open the BTTS tab, read the numbers off the page.
2. **Real data only.** If you cannot open a match or it has no BTTS market, leave both
   cells **blank**. Never invent, estimate, or interpolate odds. Blanks are correct.
3. **Decimal odds, dot decimal point** (e.g. `1.95`, `1.85`). Convert any fractional/
   American odds to decimal.
4. **Sanity check each pair:** `1/btts_yes + 1/btts_no` should be ~1.03–1.08 (the
   bookmaker margin). If your two numbers don't, you read the wrong row — fix or blank it.
5. **Do not change `wc`, `date`, `home_team`, `away_team`.** Match by those fields. BTTS
   is symmetric, so home/away orientation doesn't matter.
6. **Cite the page URL** you used for each match (or at least per tournament).
7. Leave `over15, under15, over25, under25` blank — I only need BTTS for now.

Work **2022 first**, then 2018. Output:
- the completed CSV (same columns, all 128 rows, blanks where you had no real data),
  ready to save as `wc_goals_odds.csv`;
- a coverage summary: how many of 128 you filled, and the source URLs;
- a list of any rows you were unsure about.

Do not put commentary inside the CSV. Begin with the 2022 matches.

---

## When Gemini returns it
Save as `data/raw/wc_goals_odds.csv` and tell me. I'll run script 31 and read the P&L +
fragility straight from the folder, and flag any rows whose margins look wrong.

> If Gemini says it can't open these pages (they're bot-protected, which is common),
> that's the signal the LLM route is exhausted — tell me and I'll either (a) have you
> paste the raw page text per match, or (b) we validate the BTTS sleeve forward on live
> 2026 results instead. Don't let it fill cells it couldn't actually read.
