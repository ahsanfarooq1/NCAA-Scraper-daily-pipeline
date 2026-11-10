"""
Automated Season Contest Fetcher

Quick script to fetch ALL contest IDs for a complete season in one command.
No interactivity - just run and get all the data!
"""

from contest_id_fetcher import ContestIDFetcher
from ncaa_paths import data_dir
import os
import sys

# Make the Windows console tolerate the banner / accented names (cp1252 crashes).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def fetch_entire_season(sport_code: str = "MBB", division: int = 1, season_year: int = 2025,
                        cf_session=None):
    """
    Fetch all contests for an entire season automatically
    
    Args:
        sport_code: Sport code (MBB for Men's Basketball, WBB for Women's Basketball)
        division: Division (1, 2, or 3)
        season_year: Starting year of the season (e.g., 2025 for 2025-2026 season)
    """
    print("\n" + "="*70)
    print(f"AUTOMATED SEASON CONTEST FETCHER")
    print("="*70)
    print(f"Sport: {sport_code}")
    print(f"Division: {division}")
    print(f"Season: {season_year}-{season_year+1}")
    print("="*70 + "\n")
    
    fetcher = ContestIDFetcher(cf_session=cf_session)

    # Fetch all contests for the season
    print("Starting automated fetch...")
    print("This will take several minutes (one request per day across the season)")
    print("Please be patient...\n")
    
    contests = fetcher.get_season_contests(
        sport_code=sport_code,
        division=division,
        season_year=season_year,
        delay_range=(0.0, 0.0) if cf_session is not None else (0.5, 1.0),
        confirm=cf_session is None,  # no blocking prompt when running the CF pipeline
    )
    
    # Save results
    # Saved into the season's data folder (e.g. 2026_27_data/), not the project root.
    filename_json = os.path.join(
        data_dir(season_year),
        f"season_{sport_code}_d{division}_{season_year}-{season_year + 1}.json")
    
    fetcher.save_to_json(contests, filename_json)
    fetcher.print_summary(contests)
    
    print(f"\n{'='*70}")
    print(f"SUCCESS! Season data saved")
    print(f"{'='*70}")
    print(f"\nFile created:")
    print(f"  - {filename_json} (Full contest data)")
    print(f"\n{'='*70}")
    print(f"NEXT STEP: Scrape all the games!")
    print(f"{'='*70}")
    print(f"\nRun this command:")
    print(f'  python ncaa_game_scraper2.py "{filename_json}" <output_file>')
    print(f"\nThis will scrape all {len(contests)} games using the contest IDs from the JSON file!")
    print(f"{'='*70}\n")


def main():
    """Main function"""
    
    # Default values
    sport_code = "MBB"
    division = 1
    season_year = 2025
    
    # Cloudflare-bypass flags (anywhere on the command line)
    flags = {a.lower() for a in sys.argv[1:] if a.startswith("--")}
    use_cf = bool(flags & {"--cf", "--attach", "--headful"})
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]

    # Parse positional command line arguments
    if len(positional) > 0:
        sport_code = positional[0].upper()
    if len(positional) > 1:
        division = int(positional[1])
    if len(positional) > 2:
        season_year = int(positional[2])

    cf_session = None
    if use_cf:
        from ncaa_cf import CFSession
        cf_session = CFSession(min_interval=0.6,
                               headful="--headful" in flags,
                               attached="--attach" in flags)

    # Run
    try:
        fetch_entire_season(sport_code, division, season_year, cf_session=cf_session)
    finally:
        if cf_session is not None:
            cf_session.close()


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║           NCAA AUTOMATED SEASON CONTEST ID FETCHER                   ║
╚══════════════════════════════════════════════════════════════════════╝

USAGE:
------
  python fetch_season_contests.py [SPORT] [DIVISION] [YEAR]

EXAMPLES:
---------
  # Men's Basketball D1 for 2024-2025 season
  python fetch_season_contests.py MBB 1 2025

  # Women's Basketball D1 for 2024-2025 season
  python fetch_season_contests.py WBB 1 2025

  # Men's Basketball D2 for 2024-2025 season
  python fetch_season_contests.py MBB 2 2025

  # Use defaults (MBB D1 2025)
  python fetch_season_contests.py

PARAMETERS:
-----------
  SPORT    : MBB (Men's Basketball) or WBB (Women's Basketball)
  DIVISION : 1, 2, or 3
  YEAR     : Season year (2025 for 2024-2025 season)

WHAT THIS DOES:
---------------
1. Fetches contest IDs for every day of the season (Nov-March)
2. Saves full contest data to JSON file
3. Saves contest IDs only to TXT file (for bulk scraper)
4. Shows you the command to scrape all games

DEFAULT: MBB Division 1, Season 2024-2025

╔══════════════════════════════════════════════════════════════════════╗
""")
    
    main()
