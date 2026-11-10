# NCAA Basketball Scraper

Collects NCAA **men's and women's basketball** data for **Divisions 1, 2 and 3**:
every game's full boxscore (team + player stats), then adds them up into season
totals/averages per team and per player.

- **Source:** NCAA's JSON GraphQL API, `https://sdataprod.ncaa.com/` (the same API ncaa.com uses).
- **Sports/divisions:** `MBB` (men) and `WBB` (women) x D1, D2, D3 = 6 combinations.
- **Season naming:** scripts use the **starting year**. `2026` = the 2026-27 season.
- **Deeper notes:** `NCAA_SCRAPER_NOTES.txt` (how it works, written July 2026) and
  `NCAA_CAPTCHA_BYPASS.md` (Cloudflare bypass details).

---

## 1. Folder layout

```
NCAA_Scraper/
├── 2026_27_data/              CURRENT season (2026-27) - all its data files
├── 2024_2025_2026_data/       Finished seasons 2024-25 and 2025-26, plus the team lists
├── Share_2026-27/             Team lists in the "share" format (see section 6)
├── individual_games/          Old per-game dump from an early run (not used by the pipeline)
├── ncaa_cf_profile/           Chrome profile used by the Cloudflare fallback (auto-managed)
├── *.py, *.ps1                Scripts (section 3)
└── README.md                  This file
```

Each season folder holds three kinds of file per sport/division:

| File | What it is |
|---|---|
| `season_<MBB\|WBB>_d<1-3>_<YYYY>-<YYYY>.json` | List of every game (contest ID, date, teams, status) found for the season |
| `Final_All_Games_Data_<MBB\|WBB>_D<1-3>_<YYYY>_<YYYY>.json` | Raw boxscore for every game (both teams, every player) |
| `NCAA_Accumulated_Stats_<MBB\|WBB>_D<1-3>_<YYYY>_<YYYY>.json` | Season totals + per-game averages per team and player (this is what you send/consume) |

`2024_2025_2026_data/` also holds `Ncaa_men_Teams_d{1,2,3}.json` and
`Ncaa_Women_Teams_d{1,2,3}.json` (unique team names per season) and `missing_contests.json`.

**Where files go is decided in one place: `ncaa_paths.py`.**
Season 2025 or earlier -> `2024_2025_2026_data/`. Season 2026 or later ->
`<YYYY>_<YY>_data/` (e.g. `2026_27_data`, `2027_28_data`), created automatically on first run.

---

## 2. How the pipeline works

```
A) DISCOVER   one API request per day (Nov 1 -> today, never future dates)
              -> season_*.json                         (contest IDs)
B) SCRAPE     one API request per contest ID
              -> Final_All_Games_Data_*.json           (boxscores)
C) ACCUMULATE add up all boxscores
              -> NCAA_Accumulated_Stats_*.json              (team_total + player records)
```

**Resume-safe.** Re-running never starts over:
- Discovery re-walks every date from Nov 1 each run (cheap) and overwrites `season_*.json`.
- Scraping keeps existing records and only fetches games that are new or still **empty**.
  A game with zero player rows is treated as "not done" and re-fetched (games scraped before
  the NCAA posted the boxscore come back empty at first).
- Discovery stops at today's date (`contest_id_fetcher.py`), so the current season never fetches the future.

**Cloudflare.** The API normally works from a home connection. `ncaa_cf.py` (`CFSession`) adds
automatic bypass layers if blocked: Chrome-fingerprint requests (`curl_cffi`), then a headful
Chrome to get clearance, then in-browser fetching. Use `-Attach` to drive a Chrome you started yourself.

---

## 3. Scripts

**Main pipeline (use these):**

| Script | Purpose |
|---|---|
| `run_ncaa.ps1` | Launcher for ONE sport+division: discover -> scrape. Params: `-Sport MBB/WBB -Division 1/2/3 -SeasonYear 2026 [-Attach] [-Headful] [-SkipDiscover] [-Delay 1.0]` |
| `run_2026_all.ps1` | Runs `run_ncaa.ps1` for all 6 combinations for 2026-27 (log: `run_2026_all.log`) |
| `fetch_season_contests.py` | Stage A: discovery for a season |
| `contest_id_fetcher.py` | Discovery engine (GraphQL calls, date ranges, end date clamped to today) |
| `ncaa_game_scraper2.py` | Stage B: boxscore scraper (resume-safe, refreshes empty games) |
| `ncaa_accumulation.py` | Stage C: builds `NCAA_Accumulated_Stats_*` next to each `Final_All_Games_Data_*` |
| `extract_ncaa_teams.py` | Builds the `Ncaa_*_Teams_d*.json` lists (one section per season) |
| `ncaa_cf.py` | Cloudflare-resilient HTTP session |
| `ncaa_paths.py` | Decides which data folder each season uses |
| `start_chrome_debug_ncaa.ps1` | Opens a debug Chrome (port 9222) for `-Attach` mode; rarely needed |

**Older / diagnostic scripts (not part of the normal run):** `ncaa_game_scraper.py` (older scraper,
no resume), `bulk_scraper.py`, `data_analyzer.py`, `check_contest.py`, `check_schedule.py`,
`find_meta.py`, `find_missing_d3.py`, `verify_missing.py`.

---

## 4. Everyday use

**Python:** use `D:\Apps\Python\python.exe` (Python 3.13). It has the dependencies
(`curl_cffi`, `playwright`, `requests`, `beautifulsoup4`). The default `python` on this PC does NOT,
and `.venv` here is broken. `run_ncaa.ps1` finds the right Python by itself.
New machine: `pip install -r requirements.txt` then `python -m playwright install chromium`.

**Refresh the current season (e.g. once a week)** - run from the `NCAA_Scraper` folder:

```powershell
powershell -ExecutionPolicy Bypass -File run_2026_all.ps1          # discover + scrape all 6
$env:PYTHONUTF8=1; D:\Apps\Python\python.exe ncaa_accumulation.py 2026_2027   # rebuild accumulated files
```

Then check the `[SUMMARY]` lines in `run_2026_all.log`: total records should rise and `Empty` should drop
(`Empty` = games not final yet; they fill in on the next run).

**One combination only:**
`powershell -ExecutionPolicy Bypass -File run_ncaa.ps1 -Sport WBB -Division 2 -SeasonYear 2026`
(add `-SkipDiscover` to reuse the existing `season_*.json`).

**Accumulation filters:** `ncaa_accumulation.py` takes optional words that must appear in the file name,
e.g. `2026_2027`, `MBB`, `WBB_D1`. With none it processes every season folder.

**Refresh the team lists after accumulating:** `D:\Kinetic Intellegence\All Scrapers\NCAA_Scraper> D:\Apps\Python\python.exe extract_ncaa_teams.py`.

---

## 5. Starting a new season (e.g. 2027-28)

1. Run with `-SeasonYear 2027`; the folder `2027_28_data/` is created automatically.
2. Copy `run_2026_all.ps1` to a new file and change `2026` to `2027` (or loop it yourself).
3. Accumulate with filter `2027_2028`.
4. In `extract_ncaa_teams.py` add `"2027-2028"` to the `seasons` list.

If the NCAA changes its API, the GraphQL "persisted query" hashes in `contest_id_fetcher.py`
(schedule) and `ncaa_game_scraper2.py` (boxscore) are what to update.

---

## 6. Team lists

**`Ncaa_*_Teams_d*.json`** (in `2024_2025_2026_data/`): `{ "<season>": [ {team_name, city, state}, ... ] }`.
Built from the accumulated files, so a team only appears once it has played. Each division's list also
contains **non-division opponents** (e.g. a D2 school that played a D1 team shows in the D1 list), and
`city`/`state` are empty.

**`Share_2026-27/`** (a copy also exists in `..\Updated_NCAA_Scraper\Share_2026-27\`): six flat files
`NCAA_<Men|Women>_Teams_D<1-3>_2026-27.json` in the format
`[{"team_name": "...", "data_availablity": "partial"}]` (field spelled exactly like that).
- `partial` = team has 2026-27 stats; `none` = no data; never `full` while the season is running.
- Each team appears in exactly one file. Home division was assigned from ncaa.com's division stats lists,
  using each team's conference to place teams ncaa.com hadn't listed yet.
- Non-NCAA opponents (NAIA, NJCAA, small colleges) were left out.
- Built 2026-11-06 from data through Nov 5, so D2/D3 are far from complete and there are no `none`
  entries yet. Next step discussed: use ncaa.com's D2/D3 team lists as the roster so teams with no games
  yet appear as `none`. Not done.

---

## 7. Known gotchas

- **ncaa.com stats pages lag by division.** In Nov 2026 the D1 "current" pages showed 2026-27, but D2 and D3
  still showed the final 2025-26 numbers, so they can't be used to count 2026-27 teams yet.
- **stats.ncaa.org blocks automated access** (Access Denied, even in a normal Chrome), so it is not used.
- **Same team name can be in several division files** of the raw lists (cross-division games). Do not assume
  a name in `Ncaa_*_Teams_d1.json` is a D1 team.
- **Empty games** are normal for games not yet final; they are retried automatically.
- Windows console + accented team names: scripts/launcher set UTF-8 (`PYTHONUTF8=1`); set it yourself if you run a script directly.
- Do not run two scrapes writing the same output file at once.

---

## 8. Client-confirmed teams to watch (checked 2026-11-07)

The client confirmed the **Southern Athletic Association (SAA)** is **NCAA Division III**. Its nine members
must appear in the D3 accumulated files and D3 team lists once they have played:
Berry College, Centre College, Maryville College (TN), Millsaps College, Oglethorpe University,
Rhodes College, Sewanee: The University of the South, Southwestern University (TX), Trinity University (TX).

**Check result (data scraped Nov 5, 2026):**
- All nine are on ncaa.com's D3 lists (men's and women's), under the slugs `berry`, `centre`, `maryville-tn`,
  `millsaps`, `oglethorpe`, `rhodes`, `sewanee`, `southwestern-tx`, `trinity-tx`. So they are D3, not missing.
- Only **Berry (M+W), Centre (M) and Oglethorpe (W)** were in our accumulated files / team lists, each with 1 game
  (an early game against a D1 team, so they also showed up in the D1 lists). The `Share_2026-27` D3 files already list them as D3.
- The other schools were absent only because **they had no completed game by the Nov 5 scrape**. The accumulated files,
  team lists and Share files are all built from games already played, so a team appears only after its first game
  is scraped. Their schedule is already published in the API (Nov 7 onward; Sewanee men Nov 13, Southwestern women Nov 21).
- Some played Nov 5-6, after the last scrape (e.g. Centre W, Sewanee W, Trinity TX M), so the next refresh adds them.

**What to do:** nothing special. The normal weekly refresh (section 4) discovers D3 games automatically
(`division=3`), so these schools will appear in `NCAA_Accumulated_Stats_*_D3_2026_2027.json` after their first game.
Re-run `extract_ncaa_teams.py` afterwards to update the team lists.

**Known limitation:** teams with no games yet cannot appear in any team list or Share file. A roster built from
ncaa.com's D3 team list (which would show them as `"none"`) has been proposed but is **not implemented**.
Until then, use this section to verify that SAA schools show up after they play.

Do not confuse these with similarly named schools: "Maryville University of Saint Louis" is D2, and
"Southwestern Christ." / "Trinity Baptist" are non-NCAA (excluded from the Share files).

---

## 9. Automated daily pipeline (no laptop)

Since 2026-11-10 the whole flow can run unattended on GitHub Actions: scrape -> accumulate -> validate ->
publish to a GitHub Release, stopping before any Pinecone ingestion. Everything about it (setup, what the
downstream job downloads, the validation rules, risks, limits) is in **`PIPELINE.md`**.
Code: `pipeline/` and `.github/workflows/ncaa_daily.yml`. Note that `ncaa_accumulation.py` now ignores games
with no player rows (so GP is not inflated); `--keep-empty` restores the old behaviour.
