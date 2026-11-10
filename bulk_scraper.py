"""
Bulk NCAA Game Scraper

This script helps you scrape large numbers of games efficiently.
"""

import argparse
from ncaa_game_scraper import NCAAGameScraper
import json
import os


def load_contest_ids_from_file(filepath: str) -> list:
    """Load contest IDs from a text file (one per line)"""
    with open(filepath, 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]


def load_contest_ids_from_json(filepath: str, key: str = 'contest_ids') -> list:
    """Load contest IDs from a JSON file"""
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and key in data:
        return data[key]
    else:
        raise ValueError(f"Could not find contest IDs in JSON file. Expected list or dict with key '{key}'")


def scrape_by_date_range(sport: str = "basketball-women", division: str = "d1", 
                         start_date: str = None, end_date: str = None):
    """
    Scrape games within a date range
    
    NOTE: This is a placeholder. You'll need to discover the schedule/scoreboard
    GraphQL query to get contest IDs by date range.
    """
    print(f"[INFO] Scraping {sport} {division} from {start_date} to {end_date}")
    print("[WARNING] This feature requires discovering the schedule GraphQL query.")
    print("Please use the find_contest_ids.py script to discover query hashes.")
    return []


def main():
    parser = argparse.ArgumentParser(description='Bulk scrape NCAA game data')
    
    parser.add_argument('--input', '-i', type=str, 
                       help='Input file containing contest IDs (.txt or .json)')
    parser.add_argument('--output-dir', '-o', type=str, default='scraped_data',
                       help='Output directory for scraped data')
    parser.add_argument('--delay-min', type=float, default=1.0,
                       help='Minimum delay between requests (seconds)')
    parser.add_argument('--delay-max', type=float, default=3.0,
                       help='Maximum delay between requests (seconds)')
    parser.add_argument('--contest-ids', '-c', nargs='+',
                       help='Contest IDs to scrape (space-separated)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    
    args = parser.parse_args()
    
    # Determine contest IDs source
    contest_ids = []
    
    if args.input:
        if not os.path.exists(args.input):
            print(f"[ERROR] Input file not found: {args.input}")
            return
        
        if args.input.endswith('.json'):
            contest_ids = load_contest_ids_from_json(args.input)
        else:
            contest_ids = load_contest_ids_from_file(args.input)
        
        print(f"[INFO] Loaded {len(contest_ids)} contest IDs from {args.input}")
    
    elif args.contest_ids:
        contest_ids = args.contest_ids
        print(f"[INFO] Using {len(contest_ids)} contest IDs from command line")
    
    else:
        print("[ERROR] No contest IDs provided. Use --input or --contest-ids")
        parser.print_help()
        return
    
    if not contest_ids:
        print("[ERROR] No contest IDs to scrape")
        return
    
    # Create scraper and run
    print(f"\n{'='*70}")
    print(f"BULK NCAA GAME SCRAPER")
    print(f"{'='*70}")
    print(f"Contest IDs: {len(contest_ids)}")
    print(f"Output directory: {args.output_dir}")
    print(f"Delay range: {args.delay_min} - {args.delay_max} seconds")
    print(f"{'='*70}\n")
    
    scraper = NCAAGameScraper(output_dir=args.output_dir)
    scraper.scrape_multiple_games(
        contest_ids, 
        delay_range=(args.delay_min, args.delay_max)
    )
    
    print(f"\n{'='*70}")
    print(f"SCRAPING COMPLETE")
    print(f"{'='*70}")
    print(f"Check the '{args.output_dir}' directory for results")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    # If no arguments, show example usage
    import sys
    if len(sys.argv) == 1:
        print("="*70)
        print("NCAA BULK SCRAPER - USAGE EXAMPLES")
        print("="*70)
        print("""
Example 1: Scrape from a text file
    python bulk_scraper.py --input contest_ids.txt

Example 2: Scrape from JSON file
    python bulk_scraper.py --input contest_ids.json --output-dir my_games

Example 3: Scrape specific contest IDs
    python bulk_scraper.py --contest-ids 6515074 6515075 6515076

Example 4: Adjust delay between requests
    python bulk_scraper.py --input contest_ids.txt --delay-min 2 --delay-max 5

Example 5: Full command with all options
    python bulk_scraper.py \\
        --input my_games.txt \\
        --output-dir scraped_basketball \\
        --delay-min 1.5 \\
        --delay-max 3.5 \\
        --verbose

Input File Formats:

Text file (contest_ids.txt):
    6515074
    6515075
    6515076
    # Comments starting with # are ignored

JSON file (contest_ids.json):
    ["6515074", "6515075", "6515076"]

    Or:
    {
        "contest_ids": ["6515074", "6515075", "6515076"],
        "notes": "Women's basketball games from Feb 2026"
    }
""")
        print("="*70)
        print("\nRun with --help for more information")
        print("="*70)
    else:
        main()
