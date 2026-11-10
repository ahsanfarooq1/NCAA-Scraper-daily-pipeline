#!/usr/bin/env python3
"""
NCAA daily pipeline  (runs unattended on GitHub Actions, or locally).

  restore state -> discover new/changed games -> scrape final boxscores
  -> accumulate season stats -> build team lists -> write out/ + manifest.json
  -> save state

It stops BEFORE any ingestion: the finished files in --out are what the
downstream (Pinecone) ingestion picks up. See PIPELINE.md.

Exit codes: 0 ok (or off-season skip) | 2 API blocked / too many failures | 1 other error
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from ncaa_paths import data_dir                      # noqa: E402
from contest_id_fetcher import ContestIDFetcher       # noqa: E402
from ncaa_game_scraper2 import NCAAGameScraper        # noqa: E402
from ncaa_cf import CFSession, MINT_URL               # noqa: E402
import ncaa_accumulation as acc                       # noqa: E402

ALL_COMBOS = [(s, d) for s in ("MBB", "WBB") for d in (1, 2, 3)]
PIPELINE_VERSION = 1


# ----------------------------------------------------------------- helpers
def today_et() -> dt.date:
    """'Today' in US Eastern - NCAA game days follow US time."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        return (dt.datetime.utcnow() - dt.timedelta(hours=5)).date()


def season_year_for(d: dt.date) -> int:
    """2026 = the 2026-27 season. Basketball seasons start in the autumn."""
    return d.year if d.month >= 9 else d.year - 1


def in_season(d: dt.date) -> bool:
    """Basketball runs Nov 1 -> mid April. Outside that there is nothing to scrape."""
    return d.month >= 11 or d.month <= 3 or (d.month == 4 and d.day <= 15)


def parse_mdy(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%m/%d/%Y").date()


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj, indent=None):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent, ensure_ascii=False)
    os.replace(tmp, path)


# ----------------------------------------------------------------- state (gz round-trip)
STATE_PATTERNS = ("Final_All_Games_Data_", "season_", "team_registry_", "official_")


def restore_state(state_dir: str, ddir: str):
    if not state_dir or not os.path.isdir(state_dir):
        print("[STATE] no state dir - starting fresh")
        return
    n = 0
    for name in sorted(os.listdir(state_dir)):
        if not name.endswith(".gz"):
            continue
        dest = os.path.join(ddir, name[:-3])
        with gzip.open(os.path.join(state_dir, name), "rb") as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
        n += 1
    print(f"[STATE] restored {n} file(s) into {ddir}")


def save_state(state_dir: str, ddir: str):
    if not state_dir:
        return
    os.makedirs(state_dir, exist_ok=True)
    n = 0
    for name in sorted(os.listdir(ddir)):
        if name.endswith(".json") and name.startswith(STATE_PATTERNS):
            with open(os.path.join(ddir, name), "rb") as src, \
                    gzip.open(os.path.join(state_dir, name + ".gz"), "wb", compresslevel=6) as out:
                shutil.copyfileobj(src, out)
            n += 1
    print(f"[STATE] saved {n} file(s) to {state_dir}")


# ----------------------------------------------------------------- API probe
def probe_api() -> bool:
    """Fast check that the NCAA API answers this machine. A block on a data-center IP
    (GitHub runners) is the main risk of running off-laptop, so say so loudly."""
    try:
        from curl_cffi import requests as cr
        r = cr.get(MINT_URL, impersonate="chrome", timeout=30,
                   headers={"Referer": "https://www.ncaa.com/", "Origin": "https://www.ncaa.com"})
        ok = r.status_code == 200 and r.text.lstrip()[:1] == "{"
        print(f"[PROBE] NCAA API: HTTP {r.status_code} -> {'OK' if ok else 'NOT OK'}")
        if not ok:
            print(f"[PROBE] body starts: {r.text[:200]!r}")
        return ok
    except Exception as e:
        print(f"[PROBE] failed: {e}")
        return False


# ----------------------------------------------------------------- discovery
def discover(fetcher, sport, div, year, today, lookback, registry, season_path, full_walk=False):
    """Incremental discovery: re-walk only the recent window, plus any recent game that
    was not final last time. Everything older is kept from the saved season file."""
    existing = {}
    data = load_json(season_path)
    if data:
        for c in data.get("contests", []):
            existing[str(c["contest_id"])] = c

    season_start = dt.date(year, 11, 1)
    start = season_start
    if existing and not full_walk:
        stale = []
        for c in existing.values():
            try:
                d = parse_mdy(c["date"])
            except Exception:
                continue
            if c.get("game_state") != "F" and d <= today and (today - d).days <= 14:
                stale.append(d)
        start = max(season_start, min([today - dt.timedelta(days=lookback)] + stale))

    days = (today - start).days + 1
    print(f"[DISCOVER] {sport} D{div}: {start} -> {today} ({max(days, 0)} day(s), "
          f"{len(existing)} known games)")
    fails = 0
    cur = start
    while cur <= today:
        ds = cur.strftime("%m/%d/%Y")
        res = fetcher.get_contests_by_date(sport, div, year, ds)
        if res is None:
            time.sleep(2)
            res = fetcher.get_contests_by_date(sport, div, year, ds)
        if res is None:
            fails += 1
            print(f"  [FAIL] {ds}")
        else:
            for c in fetcher.extract_contest_ids(res):
                existing[str(c["contest_id"])] = c
            for c in ((res.get("data") or {}).get("contests") or []):
                for t in c.get("teams", []):
                    slug = t.get("seoname")
                    if slug:
                        e = registry.setdefault(slug, {"short": t.get("nameShort"), "conf": None})
                        e["short"] = t.get("nameShort") or e["short"]
                        if t.get("conferenceSeo"):
                            e["conf"] = t["conferenceSeo"]
        cur += dt.timedelta(days=1)

    if days > 0 and fails > max(2, 0.2 * days):
        raise RuntimeError(f"discovery failed on {fails}/{days} days for {sport} D{div} - API blocked?")

    contests = sorted(existing.values(), key=lambda c: (parse_mdy(c["date"]), str(c["contest_id"])))
    fetcher.save_to_json(contests, season_path)
    return contests, fails


# ----------------------------------------------------------------- scrape
def scrape(cf, contests, final_path, max_fail_frac):
    final = [c for c in contests if c.get("game_state") == "F"]
    scraper = NCAAGameScraper(output_file=final_path, cf_session=cf)
    scraper.scrape_all(final, delay_range=(0.0, 0.0), refresh_empty=True)

    # Drop empty shells left by older runs for games that are not final: they carry
    # no data and would be re-created every time. Final-but-empty games are KEPT so
    # they are retried (and counted in the manifest).
    final_ids = {str(c["contest_id"]) for c in final}
    records = load_json(final_path, [])
    kept, dropped = [], 0
    for r in records:
        has_players = scraper._has_players(r)
        if has_players or str(r.get("contest_id")) in final_ids:
            kept.append(r)
        else:
            dropped += 1
    if dropped:
        save_json(final_path, kept, indent=2)
        print(f"[CLEAN] removed {dropped} empty record(s) for games that are not final")

    with_players = sum(1 for r in kept if scraper._has_players(r))
    final_wo_players = sum(1 for r in kept if not scraper._has_players(r))
    failed = scraper.failed_scrapes
    if final and failed > max(3, max_fail_frac * len(final)):
        raise RuntimeError(f"{failed}/{len(final)} boxscore fetches failed - API blocked?")
    return {"games_final": len(final), "games_with_players": with_players,
            "final_without_players": final_wo_players, "scrape_failed": failed}


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ROOT, "out"), help="folder for the finished files")
    ap.add_argument("--state-dir", default=None, help="folder with *.gz state to restore/save")
    ap.add_argument("--season-year", type=int, default=None, help="starting year (default: auto)")
    ap.add_argument("--combos", default=None, help="e.g. MBB:1,WBB:3 (default: all 6)")
    ap.add_argument("--lookback-days", type=int, default=5)
    ap.add_argument("--interval", type=float, default=0.6, help="min seconds between API requests")
    ap.add_argument("--max-fail-frac", type=float, default=0.10)
    ap.add_argument("--force", action="store_true", help="run even outside Nov 1 - Apr 15")
    ap.add_argument("--no-teams", action="store_true", help="skip the team-list step")
    ap.add_argument("--no-probe", action="store_true")
    args = ap.parse_args()

    today = today_et()
    year = args.season_year or season_year_for(today)
    season_label = f"{year}-{(year + 1) % 100:02d}"
    os.makedirs(args.out, exist_ok=True)
    for stale in ("manifest.json", "SKIPPED"):
        p = os.path.join(args.out, stale)
        if os.path.exists(p):
            os.remove(p)

    print(f"[RUN] NCAA pipeline v{PIPELINE_VERSION} | today(ET)={today} | season {season_label}")
    if not in_season(today) and not args.force:
        print("[RUN] off-season (outside Nov 1 - Apr 15) - nothing to do. Use --force to override.")
        open(os.path.join(args.out, "SKIPPED"), "w").write("off-season\n")
        return 0

    combos = ALL_COMBOS
    if args.combos:
        combos = [(c.split(":")[0].upper(), int(c.split(":")[1])) for c in args.combos.split(",")]

    ddir = data_dir(year)
    restore_state(args.state_dir, ddir)
    if not args.no_probe and not probe_api():
        print("[PROBE] continuing - the session will escalate (browser fallback) if needed")

    cf = CFSession(min_interval=args.interval)
    fetcher = ContestIDFetcher(cf_session=cf)
    stats, files = {}, {}
    try:
        registries = {}
        full_walk_sports = {sp for sp in {s for s, _ in combos}
                            if not os.path.exists(os.path.join(ddir, f"team_registry_{sp}_{season_label}.json"))}
        if full_walk_sports:
            print(f"[RUN] no team registry for {sorted(full_walk_sports)} - full-season discovery walk this run")
        for sport, div in combos:
            key = f"{sport}_D{div}"
            reg_path = os.path.join(ddir, f"team_registry_{sport}_{season_label}.json")
            # No team registry yet (first run / state lost): re-walk the WHOLE season once so every
            # team that has appeared on the schedule is registered, not just recent ones.
            reg = registries.setdefault(sport, load_json(reg_path, {}))
            season_path = os.path.join(ddir, f"season_{sport}_d{div}_{year}-{year + 1}.json")
            final_path = os.path.join(ddir, f"Final_All_Games_Data_{sport}_D{div}_{year}_{year + 1}.json")
            acc_name = f"Accumulated_Stats_{sport}_D{div}_{year}_{year + 1}.json"
            acc_path = os.path.join(ddir, acc_name)

            contests, dfails = discover(fetcher, sport, div, year, today, args.lookback_days, reg, season_path,
                                       full_walk=sport in full_walk_sports)
            sstats = scrape(cf, contests, final_path, args.max_fail_frac)
            if not os.path.exists(final_path):
                save_json(final_path, [])
            acc.process_ncaa_file(final_path, acc_path, skip_empty=True)
            shutil.copyfile(acc_path, os.path.join(args.out, acc_name))

            data = load_json(acc_path, [])
            teams = [r for r in data if r.get("record_type") == "team_total"]
            sstats.update({"discover_failures": dfails, "contests_known": len(contests),
                           "teams": len(teams), "records": len(data)})
            stats[key] = sstats
            files[acc_name] = {"records": len(data), "teams": len(teams)}
            for sp, r in registries.items():
                save_json(os.path.join(ddir, f"team_registry_{sp}_{season_label}.json"), r, indent=1)
            print(f"[DONE] {key}: {sstats}")
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        save_state(args.state_dir, ddir)     # keep the progress made so far
        return 2
    finally:
        cf.close()

    if not args.no_teams:
        try:
            from share_lists import build_all
            share = build_all(year, ddir, args.out, [c for c in combos])
            for name, info in share.items():
                files[name] = info
        except Exception as e:      # team lists are best-effort: never block the stats files
            print(f"[WARN] team-list step failed, keeping previous lists: {e}")

    # latest game date seen in final data
    latest = None
    for sport, div in combos:
        for c in (load_json(os.path.join(ddir, f"season_{sport}_d{div}_{year}-{year + 1}.json"), {}) or {}).get("contests", []):
            if c.get("game_state") == "F":
                try:
                    d = parse_mdy(c["date"])
                    latest = d if latest is None or d > latest else latest
                except Exception:
                    pass

    for name in list(files):
        path = os.path.join(args.out, name)
        if os.path.exists(path):
            files[name]["bytes"] = os.path.getsize(path)
            files[name]["sha256"] = sha256(path)
    manifest = {
        "pipeline_version": PIPELINE_VERSION,
        "generated_at_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "run_date_et": today.isoformat(),
        "season": season_label,
        "season_year": year,
        "latest_final_game_date": latest.isoformat() if latest else None,
        "files": files,
        "combos": stats,
    }
    save_json(os.path.join(args.out, "manifest.json"), manifest, indent=2)
    save_state(args.state_dir, ddir)
    print(f"[RUN] finished. {len(files)} file(s) + manifest.json in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
