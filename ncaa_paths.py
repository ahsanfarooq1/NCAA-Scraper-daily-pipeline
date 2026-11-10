"""
Single source of truth for where NCAA data files live.

  2024_2025_2026_data/   seasons 2024-25 and 2025-26 (legacy, finished)
  2026_27_data/          season 2026-27 (current)
  <YYYY>_<YY>_data/      every future season, created automatically
                         (e.g. 2027_28_data for the 2027-28 season)

`season_year` is the STARTING year (2026 = the 2026-27 season), the same
convention the NCAA API and run_ncaa.ps1 use.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEGACY_DIR = os.path.join(BASE_DIR, "2024_2025_2026_data")


def data_dir(season_year: int, create: bool = True) -> str:
    """Folder that holds season_*, Final_All_Games_Data_* and Accumulated_Stats_*
    files for the given season."""
    if season_year <= 2025:
        path = LEGACY_DIR
    else:
        path = os.path.join(BASE_DIR, f"{season_year}_{(season_year + 1) % 100:02d}_data")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def all_data_dirs():
    """Every existing data folder (legacy + each <YYYY>_<YY>_data)."""
    dirs = [LEGACY_DIR] if os.path.isdir(LEGACY_DIR) else []
    for name in sorted(os.listdir(BASE_DIR)):
        full = os.path.join(BASE_DIR, name)
        if os.path.isdir(full) and name.endswith("_data") and full not in dirs \
                and name[:4].isdigit():
            dirs.append(full)
    return dirs
