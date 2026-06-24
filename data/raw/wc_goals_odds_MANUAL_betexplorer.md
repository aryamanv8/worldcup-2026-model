# Manual pull — BTTS closing odds from BetExplorer (WC 2018/2022)

Same source and method you used for `wc_closing_odds.csv` (BetExplorer average-final
decimal odds), just a different market tab. We only need **two columns** to start:
`btts_yes` and `btts_no`. Leave everything else blank — the backtest skips blank rows.

## What to fill
Open `data/raw/wc_goals_odds_template.csv`. It already has all 128 matches with the
correct names/dates. For each match, fill only:
- `btts_yes` — average **final** decimal odds for Both Teams To Score = YES
- `btts_no`  — average final decimal odds for Both Teams To Score = NO

(Over/under columns can stay empty for now. `over_1.5` is poorly archived; BTTS is
the gate-passed line that's actually available.)

## Steps (BetExplorer)
1. Go to betexplorer.com → Football → search "World Cup 2022" (then "World Cup 2018").
2. Open the tournament's **Results** list — every match is a row.
3. Click a match to open its page. Select the **"BTTS"** odds tab (sometimes labelled
   "Both Teams to Score"). If a match has no BTTS tab, leave that row blank and move on.
4. Read the **average row** (the "Ø" / "Average" line at the bottom of the bookmaker
   list) — that's the average-final, matching how the 1X2 file was built. Take the
   **YES** and **NO** decimal numbers.
5. Put them in `btts_yes` / `btts_no` for that match's row in the template.
6. Sanity check as you go: `1/btts_yes + 1/btts_no` should be roughly 1.03–1.08
   (i.e. a 3–8% margin). If it's wildly off, you grabbed the wrong row.

## Scope to keep it light
- Do **2022 first** (64 matches, rows where `wc=2022`). That alone is enough for a
  first real P&L read. 2018 can come later.
- Even a partial fill is useful — send me whatever you've got and I'll run it.

## Faster alternative (still manual, BTTS only)
oddsportal.com has a per-competition **"BTTS" results** view that lists many matches
on one page (Results → a match → "Both Teams To Score" tab). If that's quicker for
you than clicking each BetExplorer match, use it — just keep to closing/average lines
and the same two columns.

## When done
1. Save the filled file as `data/raw/wc_goals_odds.csv` (drop the `_template`).
2. Tell me — I'll run `scripts/31_backtest_derived_strategy.py`, read the P&L +
   fragility output straight from the folder, and tell you whether the BTTS sleeve
   shows real edge. (I'll also flag any rows whose margins look off.)
