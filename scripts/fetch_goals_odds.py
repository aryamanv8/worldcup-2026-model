#!/usr/bin/env python3
"""
fetch_goals_odds.py  —  local Playwright scraper for WC BTTS (and O/U) closing odds

Fills data/raw/wc_goals_odds.csv for the goals-sleeve backtest (script 31) by driving
a REAL local browser (so Cloudflare/JS render normally — this only works on your Mac,
not in a cloud sandbox).

DESIGN — navigation and parsing fail independently:
  1. It opens BetExplorer's WC results pages, lets YOU clear any Cloudflare check,
     then collects every match link.
  2. For each match it matches to a row in wc_goals_odds_template.csv (by team names
     + date), opens the BTTS odds tab, and CAPTURES the rendered odds-table text to
     data/raw/goals_odds_capture.jsonl  (one JSON line per match) — this always
     happens, even if parsing fails.
  3. It ALSO best-effort parses the Average ("Ø") Yes/No odds and writes them to
     data/raw/wc_goals_odds.csv, incrementally + resumable.

So if the parse selectors are wrong for the current site version, you still have the
raw captures: send me goals_odds_capture.jsonl and I'll parse them reliably.

SETUP (one time, on your Mac):
    uv pip install playwright pandas      # or: pip install --user playwright pandas
    python -m playwright install chromium

RUN:
    # test on a handful first, watch the browser, clear any Cloudflare prompt:
    python scripts/fetch_goals_odds.py --year 2022 --limit 5
    # then the full year:
    python scripts/fetch_goals_odds.py --year 2022
    python scripts/fetch_goals_odds.py --year 2018
    # resumes automatically: rows already filled in the CSV are skipped.

NOTES
  - Headed by default so you can solve any bot check; press Enter in the terminal when
    the results page is visible and clear.
  - Polite: a short randomized delay between matches.
  - BetExplorer first (most predictable). If its BTTS tab can't be found, the raw
    capture still saves the page text for that match.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW = REPO_ROOT / "data" / "raw"
TEMPLATE = RAW / "wc_goals_odds_template.csv"
OUT_CSV = RAW / "wc_goals_odds.csv"
CAPTURE = RAW / "goals_odds_capture.jsonl"

RESULTS_URL = {
    2018: "https://www.betexplorer.com/football/world/world-cup-2018/results/",
    2022: "https://www.betexplorer.com/football/world/world-cup-2022/results/",
}

# site team name -> our (martj42) convention used in the template
NAME_FIX = {
    "usa": "united states", "korea republic": "south korea", "south korea": "south korea",
    "ir iran": "iran", "iran": "iran", "cote d'ivoire": "ivory coast",
    "czechia": "czech republic", "turkiye": "turkey", "turkey": "turkey",
    "korea dpr": "north korea",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()
    s = re.sub(r"[^a-z ]", "", s)
    return NAME_FIX.get(s, s)


def load_template() -> pd.DataFrame:
    if OUT_CSV.exists():
        df = pd.read_csv(OUT_CSV)
        print(f"[resume] {OUT_CSV.name} exists — filled rows will be skipped.")
    else:
        df = pd.read_csv(TEMPLATE)
        for c in ["over15", "under15", "btts_yes", "btts_no", "over25", "under25"]:
            if c not in df.columns:
                df[c] = ""
    df["_k"] = df.apply(lambda r: frozenset((norm(r["home_team"]), norm(r["away_team"]))), axis=1)
    return df


def parse_avg_odds(text: str):
    """Best-effort: from rendered odds-table text, return (yes, no) decimals or (None,None).
    Looks for the Average/Ø row and the first two decimal numbers on it."""
    for line in text.splitlines():
        low = line.lower()
        if "average" in low or "ø" in line or "Ø" in line:
            nums = re.findall(r"\b\d\.\d{2}\b", line)
            if len(nums) >= 2:
                return float(nums[0]), float(nums[1])
    # fallback: two plausible BTTS decimals anywhere (1.20–4.00)
    nums = [float(x) for x in re.findall(r"\b\d\.\d{2}\b", text) if 1.2 <= float(x) <= 4.0]
    if len(nums) >= 2:
        return nums[0], nums[1]
    return None, None


def append_capture(rec: dict):
    with open(CAPTURE, "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def run(year: int, limit: int, headless: bool, dump_results: bool = False):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright not installed. Run:\n"
                 "  uv pip install playwright pandas\n  python -m playwright install chromium")

    df = load_template()
    todo = df[(df["wc"] == year) & (df["btts_yes"].isna() | (df["btts_yes"].astype(str).str.strip() == ""))]
    print(f"{len(todo)} unfilled {year} matches to fetch.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_context(user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")).new_page()

        slug = f"world-cup-{year}"
        BASE = "https://www.betexplorer.com"

        def scroll_full():
            prev_h, stable = -1, 0
            for _ in range(80):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(500)
                h = page.evaluate("document.body.scrollHeight")
                if h == prev_h:
                    stable += 1
                    if stable >= 2:
                        break
                else:
                    stable = 0
                prev_h = h

        def is_match(h: str) -> bool:
            if not h or slug not in h or "results" in h or "standings" in h:
                return False
            m = re.search(r"/([A-Za-z0-9]{6,12})/?$", h)   # trailing match id
            return bool(m) and any(c.isdigit() for c in m.group(1))  # real ids contain a digit

        def harvest():
            scroll_full()
            hrefs = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.getAttribute('href'))")
            return {h for h in hrefs if is_match(h)}

        page.goto(RESULTS_URL[year], wait_until="domcontentloaded")
        input("\n>> If you see a Cloudflare/'Just a moment' check, solve it in the browser, "
              "then press Enter here to continue...\n")

        if dump_results:
            html = page.content()
            (RAW / f"results_page_{year}.html").write_text(html)
            all_hrefs = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.getAttribute('href'))")
            (RAW / f"results_links_{year}.txt").write_text("\n".join(h for h in all_hrefs if h))
            print(f"[dump] saved data/raw/results_page_{year}.html + results_links_{year}.txt")
            browser.close()
            return

        # The /results/ page only shows the FINAL-TOURNAMENT *play-offs* (16 knockout
        # matches). The 48 group games live under the other final-tournament stage(s),
        # reachable via the "?stage=..." tabs that have NO "activecountry" param (the
        # activecountry ones are confederation qualifying, not the World Cup proper).
        stage_hrefs = page.eval_on_selector_all(
            "a[href*='?stage=']", "els => els.map(e => e.getAttribute('href'))")
        final_stages = sorted({h for h in stage_hrefs
                               if h and "activecountry" not in h and "?stage=" in h})
        stage_urls = [RESULTS_URL[year]] + [
            (BASE + "/football/world/world-cup-" + str(year) + "/results/" + h
             if h.startswith("?") else (BASE + h if h.startswith("/") else h))
            for h in final_stages]
        print(f"[stages] {len(stage_urls)} stage page(s) to scan "
              f"(default play-offs + {len(final_stages)} stage tab(s))")

        match_set = set()
        for su in stage_urls:
            try:
                page.goto(su, wait_until="domcontentloaded")
                page.wait_for_timeout(800)
                found = harvest()
                print(f"  [stage] {su.split('results/')[-1] or 'play-offs'} -> {len(found)} matches")
                match_set |= found
            except Exception as e:
                print(f"  [stage-error] {su}: {e}")
        match_links = sorted(match_set)
        match_links = [h if h.startswith("http") else "https://www.betexplorer.com" + h
                       for h in match_links]
        print(f"[discover] found {len(match_links)} candidate match pages.")

        filled = 0
        for url in match_links:
            if limit and filled >= limit:
                break
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(1200)
                # find + click the BTTS tab (several possible labels)
                for sel in ("text=/both teams to score/i", "text=/BTTS/i",
                            "a:has-text('BTTS')", "[data-bookmaker] >> text=BTTS"):
                    try:
                        page.click(sel, timeout=1500)
                        break
                    except Exception:
                        continue
                page.wait_for_timeout(1500)
                body = page.inner_text("body")
                # identify teams from the page title/heading
                title = page.title()
                teams = re.split(r"\s+-\s+|\s+vs\.?\s+", title.split("|")[0])
                rec = {"url": url, "title": title,
                       "captured_utc": datetime.now().astimezone().isoformat(),
                       "odds_text_excerpt": body[:4000]}
                append_capture(rec)

                # try to match to a template row by team names
                key = None
                if len(teams) >= 2:
                    key = frozenset((norm(teams[0]), norm(teams[1])))
                rows = df.index[(df["wc"] == year) & (df["_k"] == key)].tolist() if key else []
                yes, no = parse_avg_odds(body)
                tag = "no-row-match"
                if rows:
                    i = rows[0]
                    tag = "parsed" if yes else "captured-only"
                    if yes:
                        df.at[i, "btts_yes"], df.at[i, "btts_no"] = yes, no
                        # margin sanity
                        margin = 1/yes + 1/no
                        if not (1.0 < margin < 1.20):
                            tag = f"parsed-SUSPECT-margin{margin:.2f}"
                    df.drop(columns=["_k"]).to_csv(OUT_CSV, index=False)
                print(f"  [{tag}] {title[:50]:<50} yes={yes} no={no}")
                filled += 1
                page.wait_for_timeout(int(random.uniform(800, 2000)))
            except Exception as e:
                print(f"  [error] {url}: {e}")
                append_capture({"url": url, "error": str(e)})

        browser.close()

    print(f"\nDone. CSV: {OUT_CSV}  (raw captures: {CAPTURE})")
    print("If parsing missed rows, send me goals_odds_capture.jsonl and I'll extract them.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, choices=[2018, 2022], required=True)
    ap.add_argument("--limit", type=int, default=0, help="stop after N matches (0 = all); use 5 to test")
    ap.add_argument("--headless", action="store_true", help="run without a visible window (after you trust it)")
    ap.add_argument("--dump-results", action="store_true",
                    help="diagnostic: save the rendered results page HTML + links, then exit")
    a = ap.parse_args()
    run(a.year, a.limit, a.headless, a.dump_results)
