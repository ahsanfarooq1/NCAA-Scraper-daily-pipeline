"""
Team lists in the "share" format, one file per sport + division:

    NCAA_Men_Teams_D1_2026-27.json   [{"team_name": "...", "data_availablity": "partial"}]

(field name spelled exactly like that - it is the agreed format.)

How a team gets in, and which division it lands in:
  * ROSTER   every team seen on the NCAA schedule this season (teams_registry, built
             during discovery) - so teams with a scheduled game but no stats yet are
             listed, as "none".
  * DIVISION ncaa.com's per-division stats lists give the home division. Teams ncaa.com has
             not listed yet are placed by their conference (conferences are single-division).
             Teams with no known conference and no ncaa.com listing (NAIA/NJCAA/small
             colleges that played an NCAA team) are left out.
  * NAME     the full name from the boxscores when the team has played, otherwise NCAA's
             short name. A team's name can therefore change from short to full after its
             first game.
  * STATUS   "partial" = the team has player stats this season, "none" = listed but no stats.
             Never "full" while the season is running.

Limit: a team with no game on the schedule yet cannot appear anywhere (the NCAA feed is
organised by game/date and has no all-teams endpoint we can use).
"""
import collections
import datetime as dt
import json
import os
import re
import time

SPORT_LABEL = {"MBB": "Men", "WBB": "Women"}
STAT_PAGE = {"MBB": ("basketball-men", 145), "WBB": ("basketball-women", 111)}
OFFICIAL_MAX_AGE_DAYS = 7
MIN_OFFICIAL_TEAMS = 100          # every real division has 200+; below this the page is not usable
SEED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_official")


def _load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path, obj, indent=None):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent, ensure_ascii=False)
    os.replace(tmp, path)


def _http_get(url, tries=4):
    from curl_cffi import requests as cr
    last = None
    for _ in range(tries):
        try:
            r = cr.get(url, impersonate="chrome", timeout=30)
            if r.status_code == 200:
                return r.text
            last = r.status_code
        except Exception as e:
            last = e
        time.sleep(2)
    raise RuntimeError(f"GET {url} failed: {last}")


def fetch_official(sport, div):
    """slug -> display name from ncaa.com's team-stats ranking pages (all pages)."""
    slug, sid = STAT_PAGE[sport]
    base = f"https://www.ncaa.com/stats/{slug}/d{div}/current/team/{sid}"
    first = _http_get(base)
    pages = [int(p) for p in re.findall(rf"/team/{sid}/p(\d+)", first)]
    teams = {}
    for p in range(1, (max(pages) if pages else 1) + 1):
        html = first if p == 1 else _http_get(f"{base}/p{p}")
        for m in re.finditer(r'<a href="/schools/([^"]+)" class="school">([^<]+)</a>', html):
            teams[m.group(1)] = m.group(2).strip()
    # ncaa.com rolls each division to the new season at a different time and shows
    # "No stats data available" until stats exist. A near-empty page is a failed fetch,
    # NOT real data - never let it overwrite a good cache.
    if len(teams) < MIN_OFFICIAL_TEAMS:
        raise RuntimeError(f"only {len(teams)} teams on {base} (page empty / not rolled over yet)")
    return teams


def official_lists(sport, ddir, season_label):
    """Cached per season folder; refreshed weekly. Falls back to the cache if ncaa.com fails."""
    out = {}
    for div in (1, 2, 3):
        path = os.path.join(ddir, f"official_{sport}_d{div}_{season_label}.json")
        cached = _load(path)
        if not cached:       # first run / no state: committed fallback snapshot
            cached = _load(os.path.join(SEED_DIR, f"official_{sport}_d{div}.json"))
            if cached:
                print(f"[TEAMS] {sport} D{div}: using the committed fallback membership snapshot")
        fresh = False
        if cached:
            try:
                age = (dt.datetime.utcnow() - dt.datetime.fromisoformat(cached["fetched_at"])).days
                fresh = age < OFFICIAL_MAX_AGE_DAYS
            except Exception:
                pass
        if not fresh:
            try:
                cached = {"fetched_at": dt.datetime.utcnow().isoformat(), "teams": fetch_official(sport, div)}
                _save(path, cached)
                print(f"[TEAMS] fetched ncaa.com {sport} D{div}: {len(cached['teams'])} teams")
            except Exception as e:
                print(f"[TEAMS] WARN ncaa.com {sport} D{div}: {e} - keeping {len((cached or {}).get('teams', {}))} cached teams")
        out[div] = (cached or {}).get("teams", {})
    return out


def build_all(year, ddir, out_dir, combos):
    season_label = f"{year}-{(year + 1) % 100:02d}"
    sports = sorted({s for s, _ in combos})
    if len(sports) < 2 or len(combos) < 6:
        print("[TEAMS] partial combo run - skipping team lists (they need all divisions)")
        return {}
    info = {}
    for sport in sports:
        registry = _load(os.path.join(ddir, f"team_registry_{sport}_{season_label}.json"), {})
        if not registry:
            print(f"[TEAMS] no team registry for {sport} yet - skipping")
            continue
        official = official_lists(sport, ddir, season_label)
        slugdiv = {s: d for d in (3, 2, 1) for s in official[d]}      # D1 wins if in several

        short2full, has_players = {}, set()
        for div in (1, 2, 3):
            final = _load(os.path.join(ddir, f"Final_All_Games_Data_{sport}_D{div}_{year}_{year + 1}.json"), [])
            for g in final:
                for r in g.get("results", []):
                    if r.get("players"):
                        short2full.setdefault(r["team_short"], r["team_name"])
                        has_players.add(r["team_name"])

        conf_votes = collections.defaultdict(collections.Counter)
        for slug, d in slugdiv.items():
            c = (registry.get(slug) or {}).get("conf")
            if c:
                conf_votes[c][d] += 1
        confdiv = {c: v.most_common(1)[0][0] for c, v in conf_votes.items()}

        buckets = {1: {}, 2: {}, 3: {}}
        left_out = 0
        for slug, e in sorted(registry.items()):
            conf = e.get("conf")
            div = confdiv.get(conf) if conf in confdiv else slugdiv.get(slug)
            if div is None:
                left_out += 1
                continue
            name = short2full.get(e["short"], e["short"])
            buckets[div][name] = {"team_name": name,
                                  "data_availablity": "partial" if name in has_players else "none"}
        for div in (1, 2, 3):
            lst = sorted(buckets[div].values(), key=lambda t: t["team_name"])
            fname = f"NCAA_{SPORT_LABEL[sport]}_Teams_D{div}_{season_label}.json"
            _save(os.path.join(out_dir, fname), lst, indent=2)
            p = sum(t["data_availablity"] == "partial" for t in lst)
            info[fname] = {"records": len(lst), "teams": len(lst), "partial": p, "none": len(lst) - p}
        print(f"[TEAMS] {sport}: wrote 3 lists ({left_out} non-NCAA/unknown teams left out)")
    return info


# ---------------------------------------------------------------- multi-season team lists
SEED_TEAMS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_teams")
HISTORY_FILES = [(sp, f"Ncaa_{lab}_Teams_d{d}.json", d)
                 for sp, lab in (("MBB", "men"), ("WBB", "Women")) for d in (1, 2, 3)]


def build_history(year, ddir, out_dir):
    """Ncaa_<men|Women>_Teams_d<n>.json = { "<season>": [ {team_name, city, state}, ... ] } for every
    season. The CURRENT season is rebuilt from today's accumulated file; earlier seasons are carried over
    unchanged (from the previous copy in the saved state, else from the committed pipeline/seed_teams)."""
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from extract_ncaa_teams import extract_ncaa_team_details
    season = f"{year}-{year + 1}"
    info = {}
    for sport, fname, div in HISTORY_FILES:
        base = _load(os.path.join(ddir, fname)) or _load(os.path.join(SEED_TEAMS_DIR, fname)) or {}
        acc = os.path.join(ddir, f"NCAA_Accumulated_Stats_{sport}_D{div}_{year}_{year + 1}.json")
        teams = extract_ncaa_team_details(acc)
        data = {k: v for k, v in base.items() if k != season}
        data[season] = teams
        data = dict(sorted(data.items()))
        _save(os.path.join(out_dir, fname), data, indent=4)
        _save(os.path.join(ddir, fname), data, indent=4)
        info[fname] = {"records": len(teams), "teams": len(teams), "seasons": list(data)}
    print(f"[TEAMS] multi-season lists: wrote {len(info)} files (current season {season})")
    return info
