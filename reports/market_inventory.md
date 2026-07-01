# Kalshi WC market inventory — 2026-07-01 07:15 UTC

**4294 markets / 77 series discovered**; **4290 markets / 76 series** are men's-soccer-WC in scope (tiers A–D).

## By tier

| tier | meaning | series | markets |
|---|---|---:|---:|
| A | priced now | 4 | 144 |
| B | priceable — clean fit, uncovered (EDGE CANDIDATE) | 18 | 771 |
| C | priceable — needs extra modeling | 18 | 788 |
| D | out of scope (no model surface) | 36 | 2587 |
| X | excluded — not men's soccer WC | 1 | 4 |

## Tier B — edge candidates (priceable now, not yet covered)

| series | engine | model output | ~volume | example |
|---|---|---|---:|---|
| `KXMENWORLDCUP` | bracket_sim | P(team wins tournament) | 563,080,870 | Will Congo DR win the 2026 Men's World Cup? |
| `KXWC1STTIMEWIN` | bracket_sim | P(a never-won nation wins tournament) | 281,723 | Will a country with no prior World Cup victo |
| `KXWCBESTHOST` | bracket_sim | P(host X advances furthest among USA/CAN/MEX) | 442,670 | Will USA be the best performing host nation  |
| `KXWCCONTINENT` | bracket_sim | P(confederation wins) = sum of member win probs | 3,504,061 | Will South America (CONMEBOL) win the 2026 M |
| `KXWCFIFATOP10` | bracket_sim | P(a non-top-10 FIFA-ranked team reaches semis) | 389,765 | Will any country not ranked in the top 10 of |
| `KXWCFURTHESTADVANCING` | bracket_sim | P(team is furthest-advancing of its confederation) | 2,215,576 | Will Paraguay be the furthest advancing Sout |
| `KXWCGROUPWINELIM` | bracket_sim | P(>= k group winners knocked out by R32) | 624,256 | Will at least 9 group winners be knocked out |
| `KXWCGROUPWINNER` | bracket_sim | P(a team from group G wins tournament) | 731,324 | Will a team from Group L win the 2026 Men's  |
| `KXWCMOF` | goal_grid | P(a team advances in reg) = P(not draw in 90) | 8,401 | Will either team advance in Regulation Time? |
| `KXWCMOV` | goal_grid | P(named team wins in regulation) | 205,660 | Will Paraguay win in Regulation Time? |
| `KXWCNOEURSA` | bracket_sim | P(winner from outside UEFA/CONMEBOL) | 305,496 | Will the winner of the 2026 Men's FIFA World |
| `KXWCROUND` | bracket_sim | P(team reaches round R) | 14,046,156 | Will USA qualify for FIFA World Cup Semifina |
| `KXWCSCORE` | goal_grid | P(exact scoreline) from joint grid | 1,951,937 | Will the final score be Switzerland wins 5-1 |
| `KXWCSPREAD` | goal_grid | P(margin >= handicap line) | 1,172,544 | Paraguay wins by more than 2.5 goals? |
| `KXWCSTAGE` | bracket_sim | P(confederation's best team reaches exactly stage S) | 324,246 | Will the furthest stage advanced to by any A |
| `KXWCSTAGEOFELIM` | bracket_sim | P(team eliminated at stage S) | 5,090,475 | Will Ghana get eliminated in the Semifinals  |
| `KXWCTEAMH2H` | bracket_sim | P(two named teams eliminated at same stage) | 407,014 | Will Switzerland be eliminated in the same s |
| `KXWCTEAMTOTAL` | goal_grid | P(team's goals >= line) from marginal Poisson | 281,398 | Will Paraguay score over 2.5 goals? |

## Tier C — priceable with extra modeling

| series | engine | model output | ~volume | example |
|---|---|---|---:|---|
| `KXWC1H` | goal_grid_half | P(1H result) — needs half-time lambda split | 340,841 | Will Tie be the result of the 1st Half? |
| `KXWC1HBTTS` | goal_grid_half | P(both score in 1H) — needs HT split | 80,164 | Will both teams score in the 1st Half? |
| `KXWC1HSCORE` | goal_grid_half | P(1H exact score) — needs HT split | 372,672 | Will the 1st half score be Switzerland wins  |
| `KXWC1HSPREAD` | goal_grid_half | P(1H margin >= line) — needs HT split | 131,633 | Paraguay wins by more than 1.5 goals in the  |
| `KXWC1HTOTAL` | goal_grid_half | P(1H total over/under) — needs HT split | 154,153 | Over 3.5 1H goals scored? |
| `KXWC2H` | goal_grid_half | P(2H result) — needs HT split | 96,750 | Will Tie be the result of the 2nd Half? |
| `KXWC2HBTTS` | goal_grid_half | P(both score in 2H) — needs HT split | 19,318 | Will both teams score in the 2nd Half? |
| `KXWC2HSPREAD` | goal_grid_half | P(2H margin) — needs HT split | 6,483 | Paraguay wins by more than 1.5 goals in the  |
| `KXWC2HTOTAL` | goal_grid_half | P(2H total) — needs HT split | 3,793 | Over 3.5 2H goals scored? |
| `KXWC3RDPLACE` | bracket_sim_plus | P(team wins 3rd-place playoff) | 720,290 | Will USA win the third-place match at the 20 |
| `KXWCFTTS` | goal_grid | P(team scores first) — Poisson race | 95,137 | Will Paraguay record the first goal of the g |
| `KXWCGAMEGOALS` | sim_aggregate | distribution of max match goals | 7,721 | Will the highest scoring match (including re |
| `KXWCKOPENALTIES` | bracket_sim_plus | P(exactly k KO matches go to shootout) | 81,374 | Will exactly 4 matches in the Quarterfinals  |
| `KXWCMATCHUP` | bracket_sim_path | P(teams X and Y meet in round R) | 7,459 | Will Norway play Switzerland in the 2026 Men |
| `KXWCTEAMSINGAME` | bracket_sim_path | P(teams X and Y meet at any point) | 63,055 | Will USA play England in the 2026 Men's FIFA |
| `KXWCTEAMTOTALGOALS` | sim_plus_goal_grid | P(team's tournament goals >= T) | 39,410 | Will Colombia score at least 8 goals in the  |
| `KXWCTOTALGOAL` | sim_aggregate | P(all-team goal total >= T) | 435,301 | Will all teams collectively score at least 3 |
| `KXWCUSAOPPONENT` | bracket_sim_path | P(USA's round-R opponent = team Y) | 33,365 | Will the USA play Senegal in the Round of 16 |

## Tier A — priced now

- `KXWCADVANCE` — paper_trading/05_price_advance_markets.py
- `KXWCBTTS` — paper_trading/04_price_derived_markets.py
- `KXWCGAME` — paper_trading/02_price_match_markets.py
- `KXWCTOTAL` — paper_trading/04_price_derived_markets.py
