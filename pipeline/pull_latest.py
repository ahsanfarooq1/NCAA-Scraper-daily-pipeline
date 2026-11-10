#!/usr/bin/env python3
r"""
Download the newest validated files from the GitHub release `ncaa-latest` into your local folders,
so Share_2026-27\ and 2026_27_data\ match what the daily pipeline published. Verifies every file's sha256
against manifest.json.

    python pipeline/pull_latest.py                       # uses the repo below
    python pipeline/pull_latest.py --repo owner/name

Where files go:
    NCAA_<Men|Women>_Teams_D<n>_<season>.json   -> Share_<season>\
    NCAA_Accumulated_Stats_*.json, manifest.json     -> <YYYY>_<YY>_data\
    Ncaa_<men|Women>_Teams_d<n>.json            -> 2024_2025_2026_data\
Works unauthenticated for a public repo; for a private repo run `gh auth login` first (uses `gh`).
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from ncaa_paths import data_dir, LEGACY_DIR

DEFAULT_REPO = "ahsanfarooq1/NCAA-Scraper-daily-pipeline"


def fetch(repo, name, dest):
    gh = shutil.which("gh") or (r"C:\Program Files\GitHub CLI\gh.exe" if os.path.exists(r"C:\Program Files\GitHub CLI\gh.exe") else None)
    url = f"https://github.com/{repo}/releases/download/ncaa-latest/{name}"
    try:
        urllib.request.urlretrieve(url, dest)
        return
    except Exception as e:
        if not gh:
            raise SystemExit(f"download failed for {name}: {e} (private repo? install/login gh)")
    d = os.path.dirname(dest)
    subprocess.run([gh, "release", "download", "ncaa-latest", "--repo", repo, "--pattern", name, "--dir", d, "--clobber"], check=True)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--repo", default=DEFAULT_REPO); a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="ncaa_latest_")
    fetch(a.repo, "manifest.json", os.path.join(tmp, "manifest.json"))
    man = json.load(open(os.path.join(tmp, "manifest.json"), encoding="utf-8"))
    year = man["season_year"]; season = man["season"]
    print(f"[PULL] published {man['generated_at_utc']} | season {season} | latest final game {man['latest_final_game_date']}")
    for name, info in sorted(man["files"].items()):
        p = os.path.join(tmp, name); fetch(a.repo, name, p)
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        if info.get("sha256") and h != info["sha256"]:
            raise SystemExit(f"checksum mismatch for {name} - not copying anything further")
        if name.startswith("NCAA_") and not name.startswith("NCAA_Accumulated"):
            dest = os.path.join(ROOT, f"Share_{year}-{(year + 1) % 100:02d}")
        elif name.startswith("Ncaa_"):
            dest = LEGACY_DIR
        else:
            dest = data_dir(year)
        os.makedirs(dest, exist_ok=True); shutil.copyfile(p, os.path.join(dest, name))
        print(f"  {name} -> {os.path.relpath(dest, ROOT)}")
    shutil.copyfile(os.path.join(tmp, "manifest.json"), os.path.join(data_dir(year), "manifest.json"))
    print(f"[PULL] done ({len(man['files'])} files)")


if __name__ == "__main__":
    main()
