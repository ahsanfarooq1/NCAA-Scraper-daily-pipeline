#!/usr/bin/env python3
"""
Optional one-time helper: package the data you already have on your laptop as the pipeline's
starting state, so the first GitHub run only fetches what is new instead of the whole season.

    python pipeline/seed_state.py --season-year 2026          # writes ./state_seed/*.gz
    gh release create ncaa-state --title "NCAA state (internal)" --notes "seed" --latest=false
    gh release upload ncaa-state state_seed/*.gz --clobber
"""
import argparse, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from ncaa_paths import data_dir
from run_daily import save_state

ap = argparse.ArgumentParser()
ap.add_argument("--season-year", type=int, default=2026)
ap.add_argument("--out", default=os.path.join(ROOT, "state_seed"))
a = ap.parse_args()
save_state(a.out, data_dir(a.season_year, create=False))
