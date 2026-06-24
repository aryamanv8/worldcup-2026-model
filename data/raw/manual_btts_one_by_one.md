# One-by-one BTTS capture (fallback for matches the scraper missed)

Use this only for the specific matches I tell you are still missing. ~10 seconds each.

1. Open the match on BetExplorer (search the two team names, open the match page).
2. Click the **BTTS** odds tab so the table is visible.
3. Open the browser console: **F12** (or Cmd+Option+J in Chrome) → **Console** tab.
4. Paste this snippet and press Enter:

```js
(() => {
  const t = document.title.split(' - ');
  const home = (t[0]||'').trim(), away = (t[1]||'').trim();
  const rows = [...document.querySelectorAll('tr')];
  const avg = rows.find(r => /average|Ø/i.test(r.textContent));
  const nums = avg ? (avg.textContent.match(/\d\.\d{2}/g) || []) : [];
  const line = `${home},${away},${nums[0]||''},${nums[1]||''}`;
  console.log('%c' + line, 'font-size:14px;color:green');
  try { copy(line); console.log('(copied to clipboard)'); } catch(e) {}
})();
```

5. It prints (and copies) a line like:  `Argentina,Croatia,2.00,1.78`
   That's `home,away,btts_yes,btts_no`.
6. Paste those lines back to me — as many as you've got, in one block. I'll map the
   names to our template, drop them into `data/raw/wc_goals_odds.csv`, and check every
   margin. You don't need to edit the CSV yourself.

If the snippet prints empty numbers, the BTTS tab wasn't fully loaded — click it again
and re-run. If a match has no BTTS market at all, skip it (a blank row is fine).
