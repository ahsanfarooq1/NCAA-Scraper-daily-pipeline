# NCAA Scraper — Cloudflare / CAPTCHA Bypass

Same bypass technique as the NAIA scraper, adapted for NCAA's **JSON API**
(`https://sdataprod.ncaa.com/`) instead of HTML pages.

## How it works (3 layers, escalating)

1. **Fast path — `curl_cffi` (Chrome TLS impersonation).** Plain `requests` is
   blocked mainly by its TLS fingerprint. `curl_cffi` impersonates a real Chrome
   TLS handshake, which defeats the common block **with no browser**, as fast as
   `requests`. This is the default.
2. **Self-heal — headful Chrome.** On a real `403 / 429 / 503 / "just a moment"`
   it **lazily opens a headful Chrome** (Playwright, persistent profile so the
   clearance stays warm), passes Cloudflare (solve the box by hand if one ever
   shows), mints the `cf_clearance` cookie + exact User-Agent, hands them back to
   `curl_cffi`, and retries the **same** request — never skipping data.
3. **Browser-navigation fallback.** If the site binds `cf_clearance` to the
   browser's TLS fingerprint (so the `curl_cffi` handoff fails — the lesson from
   NAIA's PrestoSports site), it transparently fetches the JSON by **navigating
   the real browser**, which always passes.

`--attach` connects to a **real Chrome** you opened on debug port 9222 — best when
running from a data-center / VPN IP (a residential IP usually passes on its own).

> Implemented in **`ncaa_cf.py`** (`CFSession`). It is wired into
> `contest_id_fetcher.py` / `fetch_season_contests.py` (discovery) and
> `ncaa_game_scraper2.py` (boxscores) as an **opt-in** — without the flags, those
> scripts behave exactly as before (plain `requests`).

## Install (one time)

```powershell
D:\Apps\Python\python.exe -m pip install -r requirements.txt
D:\Apps\Python\python.exe -m playwright install chromium
```

## Run

```powershell
# Full season for one sport+division (discover IDs -> scrape boxscores), resume-safe:
powershell -ExecutionPolicy Bypass -File run_ncaa.ps1 -Sport MBB -Division 1 -SeasonYear 2025

# Women's D2, open a headful Chrome up-front:
powershell -ExecutionPolicy Bypass -File run_ncaa.ps1 -Sport WBB -Division 2 -Headful

# Hard-blocked IP? Use a real Chrome you solve once (opens it for you):
powershell -ExecutionPolicy Bypass -File run_ncaa.ps1 -Sport MBB -Division 1 -Attach

# Reuse an existing season_*.json (skip discovery):
powershell -ExecutionPolicy Bypass -File run_ncaa.ps1 -Sport MBB -Division 1 -SkipDiscover
```

`SeasonYear 2025` = the **2025-2026** season. Output:
`Final_All_Games_Data_{SPORT}_D{DIV}_{YEAR}_{YEAR+1}.json`.

## Using the scrapers directly (flags)

Every script takes the same opt-in flags: `--cf` (fast path + auto-heal),
`--headful` (open Chrome up-front), `--attach` (use your real Chrome on 9222).

```powershell
D:\Apps\Python\python.exe fetch_season_contests.py MBB 1 2025 --cf
D:\Apps\Python\python.exe ncaa_game_scraper2.py season_MBB_d1_2025-2026.json Final_All_Games_Data_MBB_D1_2025_2026.json --cf
```

## Notes

- **It is normal to see `cookies: (none)`** when the API is not currently
  challenging — no `cf_clearance` is needed, the fast path just works. The browser
  layer only kicks in when Cloudflare actually challenges.
- **IP matters** (same as NAIA): residential IPs pass; data-center IPs are blocked
  hardest. Scrape on a home machine; a front-end should only **read** the JSON.
- **Resume:** `ncaa_game_scraper2.py` loads existing output and only scrapes
  missing contests, auto-saving every 20 games — safe to stop/restart.

