#!/usr/bin/env python3
"""
Quality gate for the NCAA pipeline. Replaces the manual "verify the data" step.

  python pipeline/validate.py --out out [--prev prev/manifest.json]

Exit 0 = safe to publish. Exit 1 = do NOT publish (the previous published files stay).
Errors block publishing; warnings are printed but do not.
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SPORTS = ("MBB", "WBB")
DIVS = (1, 2, 3)
REQUIRED_ACC_KEYS = {"team_id", "team_name", "record_type", "GP", "Pts"}
SHARE_RE = re.compile(r"^NCAA_(Men|Women)_Teams_D([123])_\d{4}-\d{2}\.json$")
HIST_RE = re.compile(r"^Ncaa_(men|Women)_Teams_d([123])\.json$")


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--prev", default=None, help="previous published manifest.json")
    ap.add_argument("--max-stale-days", type=int, default=4)
    args = ap.parse_args()

    errors, warns = [], []
    mpath = os.path.join(args.out, "manifest.json")
    if not os.path.exists(mpath):
        print("[VALIDATE] FAIL: manifest.json missing")
        return 1
    man = load(mpath)
    year = man["season_year"]
    prev = load(args.prev) if args.prev and os.path.exists(args.prev) else None
    if prev and prev.get("season_year") != year:
        print(f"[VALIDATE] previous manifest is season {prev.get('season')} - new season, skipping regression checks")
        prev = None

    # 1) expected accumulated files exist, parse, and are well formed
    for sp in SPORTS:
        for d in DIVS:
            name = f"Accumulated_Stats_{sp}_D{d}_{year}_{year + 1}.json"
            path = os.path.join(args.out, name)
            if not os.path.exists(path):
                errors.append(f"{name}: missing")
                continue
            try:
                rows = load(path)
            except Exception as e:
                errors.append(f"{name}: invalid JSON ({e})")
                continue
            if not isinstance(rows, list):
                errors.append(f"{name}: top level is not a list")
                continue
            if not rows:
                if d == 1:
                    errors.append(f"{name}: empty")
                else:
                    warns.append(f"{name}: empty (division may not have started)")
                continue
            totals = {}
            seen = set()
            max_pl_gp = collections.defaultdict(int)
            for r in rows:
                miss = REQUIRED_ACC_KEYS - set(r)
                if miss:
                    errors.append(f"{name}: record missing keys {sorted(miss)}")
                    break
                key = (r["team_id"], r["record_type"], r.get("Name"))
                if key in seen:
                    errors.append(f"{name}: duplicate record {key}")
                    break
                seen.add(key)
                if r["GP"] < 0 or r["Pts"] < 0:
                    errors.append(f"{name}: negative value in {key}")
                    break
                if r["record_type"] == "team_total":
                    totals[r["team_id"]] = r["GP"]
                else:
                    max_pl_gp[r["team_id"]] = max(max_pl_gp[r["team_id"]], r["GP"])
            for tid, gp in max_pl_gp.items():
                if tid in totals and gp > totals[tid]:
                    errors.append(f"{name}: team {tid} has a player with GP {gp} > team GP {totals[tid]}")
                    break
            no_players = sum(1 for t, gp in totals.items() if gp > 0 and t not in max_pl_gp)
            if no_players:
                warns.append(f"{name}: {no_players} team(s) with games but no player rows")
            info = man["files"].get(name, {})
            if info.get("records") != len(rows):
                errors.append(f"{name}: record count differs from manifest")

    # 2) regression vs the previously published run (data only ever grows in-season)
    if prev:
        for name, p in prev.get("files", {}).items():
            cur = man["files"].get(name)
            if name.startswith("Accumulated_Stats_"):
                if cur is None:
                    errors.append(f"{name}: present in last publish, missing now")
                elif cur["records"] < p["records"]:
                    errors.append(f"{name}: records dropped {p['records']} -> {cur['records']}")
                elif cur["teams"] < p["teams"]:
                    errors.append(f"{name}: teams dropped {p['teams']} -> {cur['teams']}")

    # 3) team lists: format + each team in exactly one file per sport
    share_files = [n for n in man["files"] if SHARE_RE.match(n)]
    if not share_files:
        warns.append("no team-list files in this run")
    seen_team = {}
    for n in share_files:
        sport = SHARE_RE.match(n).group(1)
        path = os.path.join(args.out, n)
        if not os.path.exists(path):
            errors.append(f"{n}: listed in manifest but missing")
            continue
        for t in load(path):
            if set(t) != {"team_name", "data_availablity"}:
                errors.append(f"{n}: wrong fields {sorted(t)}")
                break
            if t["data_availablity"] not in ("partial", "none"):
                errors.append(f"{n}: bad data_availablity {t['data_availablity']!r}")
                break
            k = (sport, t["team_name"])
            if k in seen_team:
                errors.append(f"team {k} appears in {seen_team[k]} and {n}")
            seen_team[k] = n
    # a division that has accumulated teams must also have a non-empty team list
    for n in share_files:
        m = SHARE_RE.match(n)
        sp = "MBB" if m.group(1) == "Men" else "WBB"
        acc_name = f"Accumulated_Stats_{sp}_D{m.group(2)}_{year}_{year + 1}.json"
        if man["files"].get(n, {}).get("records", 0) == 0 and man["files"].get(acc_name, {}).get("teams", 0) > 0:
            errors.append(f"{n}: team list is EMPTY although {acc_name} has teams")
    if prev:
        for name, p in prev.get("files", {}).items():
            if SHARE_RE.match(name) and name in man["files"] and man["files"][name]["records"] < p["records"] * 0.9:
                errors.append(f"{name}: team count fell {p['records']} -> {man['files'][name]['records']}")

    # 3b) multi-season lists: current season present and non-empty, older seasons kept
    for n in [n for n in man["files"] if HIST_RE.match(n)]:
        m = HIST_RE.match(n)
        sp = "MBB" if m.group(1) == "men" else "WBB"
        path = os.path.join(args.out, n)
        if not os.path.exists(path):
            errors.append(f"{n}: listed in manifest but missing")
            continue
        h = load(path)
        cur = f"{year}-{year + 1}"
        if not isinstance(h, dict) or cur not in h:
            errors.append(f"{n}: no section for {cur}")
            continue
        acc_name = f"Accumulated_Stats_{sp}_D{m.group(2)}_{year}_{year + 1}.json"
        if not h[cur] and man["files"].get(acc_name, {}).get("teams", 0) > 0:
            errors.append(f"{n}: {cur} section EMPTY although {acc_name} has teams")
        if len(h) < 3:
            warns.append(f"{n}: only {len(h)} season section(s) (older seasons missing?)")
        for t in h[cur]:
            if set(t) != {"team_name", "city", "state"}:
                errors.append(f"{n}: wrong fields {sorted(t)}")
                break

    # 4) freshness
    latest = man.get("latest_final_game_date")
    if latest:
        age = (dt.date.fromisoformat(man["run_date_et"]) - dt.date.fromisoformat(latest)).days
        if age > args.max_stale_days:
            warns.append(f"latest final game is {age} days old ({latest}) - API stalled or no games?")
    else:
        warns.append("no final games found at all")

    # 5) pipeline health from the run itself
    for key, s in man.get("combos", {}).items():
        if s.get("discover_failures", 0):
            warns.append(f"{key}: {s['discover_failures']} schedule day(s) failed to fetch")
        if s.get("scrape_failed", 0):
            warns.append(f"{key}: {s['scrape_failed']} boxscore fetch(es) failed")
        if s.get("final_without_players", 0):
            warns.append(f"{key}: {s['final_without_players']} final game(s) still without boxscore (retried next run)")

    for w in warns:
        print(f"[VALIDATE] WARN  {w}")
    for e in errors:
        print(f"[VALIDATE] ERROR {e}")
    print(f"[VALIDATE] season {man['season']} | {len(man['files'])} files | "
          f"{len(errors)} error(s), {len(warns)} warning(s) -> {'FAIL' if errors else 'PASS'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
