# NCAA daily pipeline (no laptop needed)

Runs by itself every day on **GitHub Actions** (free tier), scrapes new NCAA basketball games,
rebuilds the stats files, **validates** them, and **publishes** them to a fixed download location.
It stops there: ingestion into Pinecone is done by the downstream process, which just downloads the
published files. Nothing here talks to Pinecone.

```
 GitHub Actions (cron, daily 06:00 UTC = 11:00 am Pakistan time)
   1. restore state      <- Release "ncaa-state"   (compressed raw boxscores from earlier runs)
   2. discover games     only the last ~5 days + any recent game not final yet (incremental)
   3. scrape boxscores   final games only; already-scraped games are skipped
   4. accumulate         NCAA_Accumulated_Stats_*  (6 files)
   5. team lists         NCAA_<Men|Women>_Teams_D<n>_<season>.json  (6 files, partial/none)
   6. validate           blocks publishing if anything looks wrong
   7. publish            -> Release "ncaa-latest"  (the 12 files + manifest.json)
   8. save state         -> Release "ncaa-state"
```

Code: `pipeline/run_daily.py` (orchestrator), `pipeline/validate.py` (quality gate),
`pipeline/share_lists.py` (team lists), `.github/workflows/ncaa_daily.yml` (schedule).
It reuses the normal scraper modules, so a manual run and the pipeline give the same results.

---

## 1. One-time setup (about 10 minutes)

1. Create a GitHub repo (private is fine) and push this `NCAA_Scraper` folder as the repo root.
   `.gitignore` already keeps the data folders, Chrome profile and logs out of git.
2. Repo **Settings -> Actions -> General -> Workflow permissions**: choose *Read and write permissions*.
3. (Optional, recommended) Seed the state with the data you already have so the first run is short:
   ```
   python pipeline/seed_state.py --season-year 2026
   gh release create ncaa-state --title "NCAA state (internal)" --notes seed --latest=false
   gh release upload ncaa-state state_seed/*.gz --clobber
   ```
   Skipping this is fine: the first run just re-scrapes the season so far.
4. (Optional) Failure alerts: add a repo secret `ALERT_WEBHOOK_URL` (Slack/Discord/Teams incoming webhook).
   GitHub also emails the repo owner when a scheduled run fails.
5. **Actions tab -> "NCAA daily pipeline" -> Run workflow.** Watch the first run. After that it runs daily.

## 2. What the downstream (Pinecone) side downloads

Release **`ncaa-latest`** always holds the newest *validated* files at stable URLs:

`https://github.com/<owner>/<repo>/releases/download/ncaa-latest/<file name>`

(private repo: use `gh release download ncaa-latest` or the GitHub API with a token.)

| File | Content |
|---|---|
| `manifest.json` | **Read first.** Run time, season, latest game date, and every file with bytes, sha256, record/team counts |
| `NCAA_Accumulated_Stats_<MBB\|WBB>_D<1-3>_<YYYY>_<YYYY>.json` | Season totals per team (`record_type: team_total`) and per player (6 files) |
| `NCAA_<Men\|Women>_Teams_D<1-3>_<YYYY>-<YY>.json` | `[{"team_name": "...", "data_availablity": "partial"\|"none"}]` (6 files) - **the lists you share**; rebuilt in the same run as the accumulated files |
| `Ncaa_<men\|Women>_Teams_d<1-3>.json` | Multi-season lists `{ "2024-2025": [...], "2025-2026": [...], "2026-2027": [...] }`; current season rebuilt from the accumulated file, older seasons carried over (6 files) |

Tip for the ingest job: compare `manifest.json -> generated_at_utc` / sha256 with what it last ingested and
only re-ingest changed files. Files are replaced in place each day; if validation fails nothing is replaced,
so the previous day's files stay available.
Release `ncaa-state` is internal (compressed raw data for resuming) - do not ingest it.

**Team lists update automatically with the accumulated files.** Both kinds of list are built inside the same run,
from the same data, so they can never be out of step; there is no separate trigger. Older seasons in the
multi-season lists come from `pipeline/seed_teams/` (committed) the first time, then from the saved state.

**Pull the published files onto your PC** (updates `Share_2026-27\`, `2026_27_data\`, and the multi-season lists):
`python pipeline\pull_latest.py` (checks every file's sha256 against `manifest.json`).

## 3. The validation gate (replaces the manual check)

Publishing is blocked (run fails, previous files stay) if any of these hold:
a file is missing / invalid JSON / empty (D1), a required field is missing, duplicate records,
negative numbers, a player with more games than their team, record or team counts **lower** than the
last published run, a team list with the wrong fields or a team in two division files.
Warnings (printed, not blocking): latest game older than 4 days, schedule days or boxscores that failed,
final games still without a boxscore (retried next run), teams with games but no player rows.

## 4. Behaviour you should know

- **Season window:** runs only Nov 1 - Apr 15; outside it the run exits cleanly and publishes nothing.
  The season year is picked automatically (`2026` = 2026-27), and a new `<YYYY>_<YY>_data` folder is created.
- **Only final games are scraped.** Games not played yet are never stored as empty shells.
  *This also changed the accumulation:* `ncaa_accumulation.py` now ignores games with no player rows, so a
  team no longer shows games played (GP) for a game with no stats. Use `--keep-empty` for the old behaviour.
- **Recent games are retried:** the last ~5 days are re-checked each run, so late NCAA corrections and
  late-posted boxscores are picked up.
- **Teams with no game on the schedule yet cannot be listed** (no all-teams endpoint is usable; the feed is
  organised by game/date). A team appears as `none` once it has a scheduled game, `partial` once it has stats.
- **Team lists are best-effort:** if the ncaa.com lookup fails the stats files are still published and the
  previous team lists are kept. ncaa.com's D2/D3 pages lag at the start of a season.
- **Division membership source:** ncaa.com's per-division stats pages. They roll over to the new season at different
  times (in Nov 2026 the D3 pages said "No stats data available"), so a near-empty page is treated as a failed
  fetch and the cached list is kept. `pipeline/seed_official/` holds a committed fallback snapshot (taken 2026-11-05)
  used only when there is no cache and ncaa.com returns nothing.
- **First run / lost state:** with no team registry the pipeline re-walks the whole season once (about 10 days of
  schedule requests per division in November) so every scheduled team is registered; afterwards it is incremental.
- A team list that is empty while its division has stats now **fails validation** (found during testing).
- Re-running the workflow is always safe (resume-safe, idempotent).

## 5. Main risk: the NCAA API may block GitHub's servers

The scraper was only ever run from a home connection. GitHub runners are data-center IPs, which Cloudflare
sometimes challenges. This **has not been tested from GitHub yet**; the first manual run answers it.
The pipeline's defences: Chrome-fingerprint requests (`curl_cffi`) first, then a real Chromium under a virtual
display (the same bypass used locally). A hard block shows up as `[PROBE] ... NOT OK` and a failed run with exit
code 2 - it never publishes bad data. If that happens, options that stay free: run the same code on another free
host (GitLab CI, Oracle Cloud Always-Free VM) or from a different IP; the code needs no changes, only the
scheduler differs.

## 6. Limits / cost (free tier)

- GitHub Actions: unlimited minutes on public repos; 2,000 min/month on private. Expected run time is
  minutes to tens of minutes once the state exists (estimate, to be confirmed by the first runs).
- Releases: no practical limit for this size (stats files ~20 MB; compressed raw state is well under the
  2 GB-per-file cap).
- Scheduled workflows are auto-disabled by GitHub after 60 days without repo activity; a push or manual
  run re-enables them. Cron start can be delayed by several minutes at busy times.

## 7. Run it locally (same code)

```
D:\Apps\Python\python.exe pipeline\run_daily.py --out out --state-dir state     # all 6 combos
D:\Apps\Python\python.exe pipeline\run_daily.py --combos MBB:3 --no-teams --out out
D:\Apps\Python\python.exe pipeline\validate.py --out out
```
Add `--force` outside the season window. Local runs update `2026_27_data\` as the daily job would.
