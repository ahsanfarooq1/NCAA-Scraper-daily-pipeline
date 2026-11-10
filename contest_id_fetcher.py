"""
NCAA Contest ID Fetcher

Fetch contest IDs by date, date range, or entire season using NCAA's GraphQL API.
Save results to JSON for use with the scraper.
"""

import requests
import json
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time
import random


class ContestIDFetcher:
    """
    Fetch contest IDs from NCAA API
    """
    
    def __init__(self, cf_session=None):
        self.base_url = "https://sdataprod.ncaa.com/"
        # Optional Cloudflare-resilient session; None = plain requests (unchanged).
        self.cf_session = cf_session

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.ncaa.com/',
            'Origin': 'https://www.ncaa.com'
        }
        
        # GraphQL query hash for getting contests
        self.contests_query_hash = "7287cda610a9326931931080cb3a604828febe6fe3c9016a7e4a36db99efdb7c"
        
        # Sport codes
        self.sport_codes = {
            'mens_basketball': 'MBB',
            'womens_basketball': 'WBB',
            'football': 'MFB',
        }
    
    def get_contests_by_date(self, sport_code: str = "MBB", division: int = 1, 
                            season_year: int = 2025, date_str: str = None) -> Optional[Dict]:
        """
        Fetch contests for a specific date
        
        Args:
            sport_code: Sport code (MBB, WBB, MFB, etc.)
            division: Division (1, 2, or 3)
            season_year: Season year (2025 for 2024-2025 season)
            date_str: Date in MM/DD/YYYY format (e.g., "02/09/2026")
            
        Returns:
            Dictionary containing contests data or None if failed
        """
        if date_str is None:
            date_str = datetime.now().strftime("%m/%d/%Y")
        
        # Parse date to get month
        date_obj = datetime.strptime(date_str, "%m/%d/%Y")
        month = date_obj.month
        
        # Build variables
        variables = {
            "sportCode": sport_code,
            "division": division,
            "seasonYear": season_year,
            "month": month,
            "contestDate": date_str,
            "week": None
        }
        
        extensions = {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": self.contests_query_hash
            }
        }
        
        # Build URL
        url = f"{self.base_url}?meta=GetContests_web&extensions={urllib.parse.quote(json.dumps(extensions))}&queryName=GetContests_web&variables={urllib.parse.quote(json.dumps(variables))}"
        
        try:
            if self.cf_session is not None:
                response = self.cf_session.get(url, timeout=30)
            else:
                response = requests.get(url, headers=self.headers, timeout=30)

            if response is not None and response.status_code == 200:
                data = response.json()
                return data
            else:
                code = response.status_code if response is not None else "no-response"
                print(f"[ERROR] Request failed: {code}")
                if response is not None:
                    print(f"Response: {response.text[:200]}")
                return None
                
        except Exception as e:
            print(f"[ERROR] Exception: {str(e)}")
            return None
    
    def extract_contest_ids(self, contests_data: Dict) -> List[Dict]:
        """
        Extract contest IDs and metadata from contests data
        
        Returns:
            List of dictionaries with contest info
        """
        contest_info = []
        
        contests = contests_data.get('data', {}).get('contests', [])
        
        for contest in contests:
            info = {
                'contest_id': contest.get('contestId'),
                'date': contest.get('startDate'),
                'time': contest.get('startTime'),
                'game_state': contest.get('gameState'),
                'status': contest.get('statusCodeDisplay'),
                'url': contest.get('url'),
            }
            
            # Add team info
            teams = contest.get('teams', [])
            if len(teams) >= 2:
                info['team1'] = teams[0].get('nameShort', '')
                info['team2'] = teams[1].get('nameShort', '')
                info['matchup'] = f"{info['team1']} vs {info['team2']}"
            
            contest_info.append(info)
        
        return contest_info
    
    def get_contests_for_date_range(self, sport_code: str = "MBB", division: int = 1,
                                   season_year: int = 2025, start_date: str = None, 
                                   end_date: str = None, delay_range: tuple = (0.5, 1.5)) -> List[Dict]:
        """
        Fetch contests for a date range
        
        Args:
            sport_code: Sport code (MBB, WBB, etc.)
            division: Division (1, 2, or 3)
            season_year: Season year
            start_date: Start date in MM/DD/YYYY format
            end_date: End date in MM/DD/YYYY format
            delay_range: Tuple of (min, max) seconds to wait between requests
            
        Returns:
            List of contest info dictionaries
        """
        if start_date is None:
            start_date = datetime.now().strftime("%m/%d/%Y")
        if end_date is None:
            end_date = start_date
        
        start_dt = datetime.strptime(start_date, "%m/%d/%Y")
        end_dt = datetime.strptime(end_date, "%m/%d/%Y")
        
        all_contests = []
        current_dt = start_dt
        
        print(f"\n{'='*70}")
        print(f"Fetching contests from {start_date} to {end_date}")
        print(f"Sport: {sport_code}, Division: {division}, Season: {season_year}")
        print(f"{'='*70}\n")
        
        total_days = (end_dt - start_dt).days + 1
        day_count = 0
        
        while current_dt <= end_dt:
            day_count += 1
            date_str = current_dt.strftime("%m/%d/%Y")
            
            print(f"[{day_count}/{total_days}] Fetching contests for {date_str}...", end=" ")
            
            contests_data = self.get_contests_by_date(
                sport_code=sport_code,
                division=division,
                season_year=season_year,
                date_str=date_str
            )
            
            if contests_data:
                contest_info = self.extract_contest_ids(contests_data)
                all_contests.extend(contest_info)
                print(f"[OK] Found {len(contest_info)} games")
            else:
                print(f"[FAIL] No data")
            
            # Move to next day
            current_dt += timedelta(days=1)
            
            # Delay to avoid rate limiting (except for last request)
            if current_dt <= end_dt:
                delay = random.uniform(*delay_range)
                time.sleep(delay)
        
        print(f"\n{'='*70}")
        print(f"Total contests found: {len(all_contests)}")
        print(f"{'='*70}\n")
        
        return all_contests
    
    def get_season_contests(self, sport_code: str = "MBB", division: int = 1,
                           season_year: int = 2025, delay_range: tuple = (0.5, 1.5),
                           confirm: bool = True) -> List[Dict]:
        """
        Fetch all contests for an entire season
        
        This will fetch contests for the typical season period:
        - Men's Basketball: November through March
        - Women's Basketball: November through March
        
        Args:
            sport_code: Sport code (MBB, WBB, etc.)
            division: Division (1, 2, or 3)
            season_year: Starting year of the season (e.g., 2025 for 2025-2026 season)
            delay_range: Delay between requests
            
        Returns:
            List of contest info dictionaries
        """
        print(f"\n{'='*70}")
        print(f"FETCHING ENTIRE SEASON")
        print(f"{'='*70}")
        print(f"Sport: {sport_code}")
        print(f"Division: {division}")
        print(f"Season Year: {season_year}")
        print(f"\nThis will fetch contests from November {season_year} to March {season_year + 1}")
        print(f"{'='*70}\n")
        
        # Define season date ranges based on sport
        if sport_code in ['MBB', 'WBB']:
            # Basketball season: November to March
            start_date = f"11/01/{season_year}"
            end_date = f"03/31/{season_year + 1}"
        elif sport_code == 'MFB':
            # Football season: August to January
            start_date = f"08/01/{season_year}"
            end_date = f"01/31/{season_year + 1}"
        else:
            # Default: 6 months
            start_date = f"11/01/{season_year}"
            end_date = f"04/30/{season_year + 1}"
        
        # Never fetch future dates (current season in progress): clamp to today.
        _today = datetime.now()
        if datetime.strptime(end_date, "%m/%d/%Y") > _today:
            end_date = _today.strftime("%m/%d/%Y")

        print(f"Date range: {start_date} to {end_date}")
        print("\nNote: The NCAA API uses the starting year as the seasonYear.")
        if confirm:
            input("\nPress Enter to start fetching (this may take several minutes)...")
        
        return self.get_contests_for_date_range(
            sport_code=sport_code,
            division=division,
            season_year=season_year,
            start_date=start_date,
            end_date=end_date,
            delay_range=delay_range
        )
    
    def save_to_json(self, contests: List[Dict], filename: str = "contest_ids.json"):
        """Save contest IDs to JSON file"""
        output = {
            'total_contests': len(contests),
            'generated_at': datetime.now().isoformat(),
            'contests': contests
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"[OK] Saved {len(contests)} contests to {filename}")
    
    def save_contest_ids_only(self, contests: List[Dict], filename: str = "contest_ids_only.txt"):
        """Save just the contest IDs to a text file (for use with bulk scraper)"""
        with open(filename, 'w') as f:
            for contest in contests:
                f.write(f"{contest['contest_id']}\n")
        
        print(f"[OK] Saved {len(contests)} contest IDs to {filename}")
    
    def print_summary(self, contests: List[Dict]):
        """Print summary of fetched contests"""
        print(f"\n{'='*70}")
        print(f"CONTEST SUMMARY")
        print(f"{'='*70}")
        print(f"Total Contests: {len(contests)}")
        
        # Group by status
        status_counts = {}
        for contest in contests:
            status = contest.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"\nBy Status:")
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")
        
        # Show sample games
        print(f"\nSample Games (first 10):")
        for i, contest in enumerate(contests[:10], 1):
            print(f"  {i}. {contest.get('matchup', 'Unknown')} - {contest.get('date')} ({contest.get('status')})")
        
        if len(contests) > 10:
            print(f"  ... and {len(contests) - 10} more")
        
        print(f"{'='*70}\n")


def main():
    """Main function with interactive menu"""
    fetcher = ContestIDFetcher()
    
    print("\n" + "="*70)
    print("NCAA CONTEST ID FETCHER")
    print("="*70)
    print("\nWhat would you like to do?")
    print("\n1. Fetch contests for a specific date")
    print("2. Fetch contests for a date range")
    print("3. Fetch contests for entire season (RECOMMENDED)")
    print("4. Exit")
    
    choice = input("\nEnter your choice (1-4): ").strip()
    
    if choice == "1":
        # Single date
        print("\n" + "-"*70)
        sport = input("Enter sport code (MBB/WBB) [default: MBB]: ").strip() or "MBB"
        division = int(input("Enter division (1/2/3) [default: 1]: ").strip() or "1")
        season_year = int(input("Enter season year [default: 2025]: ").strip() or "2025")
        date_str = input("Enter date (MM/DD/YYYY) [default: today]: ").strip()
        
        if not date_str:
            date_str = datetime.now().strftime("%m/%d/%Y")
        
        print(f"\nFetching contests for {date_str}...")
        data = fetcher.get_contests_by_date(sport, division, season_year, date_str)
        
        if data:
            contests = fetcher.extract_contest_ids(data)
            fetcher.print_summary(contests)
            
            save = input("Save to file? (y/n): ").strip().lower()
            if save == 'y':
                filename = f"contests_{sport}_{date_str.replace('/', '-')}.json"
                fetcher.save_to_json(contests, filename)
                fetcher.save_contest_ids_only(contests, filename.replace('.json', '.txt'))
        
    elif choice == "2":
        # Date range
        print("\n" + "-"*70)
        sport = input("Enter sport code (MBB/WBB) [default: MBB]: ").strip() or "MBB"
        division = int(input("Enter division (1/2/3) [default: 1]: ").strip() or "1")
        season_year = int(input("Enter season year [default: 2025]: ").strip() or "2025")
        start_date = input("Enter start date (MM/DD/YYYY): ").strip()
        end_date = input("Enter end date (MM/DD/YYYY): ").strip()
        
        contests = fetcher.get_contests_for_date_range(
            sport, division, season_year, start_date, end_date
        )
        
        fetcher.print_summary(contests)
        
        save = input("Save to file? (y/n): ").strip().lower()
        if save == 'y':
            filename = f"contests_{sport}_{start_date.replace('/', '-')}_to_{end_date.replace('/', '-')}.json"
            fetcher.save_to_json(contests, filename)
            fetcher.save_contest_ids_only(contests, filename.replace('.json', '.txt'))
    
    elif choice == "3":
        # Entire season
        print("\n" + "-"*70)
        sport = input("Enter sport code (MBB/WBB) [default: MBB]: ").strip() or "MBB"
        division = int(input("Enter division (1/2/3) [default: 1]: ").strip() or "1")
        season_year = int(input("Enter season year [default: 2025]: ").strip() or "2025")
        
        contests = fetcher.get_season_contests(sport, division, season_year)
        
        fetcher.print_summary(contests)
        
        # Auto-save for season
        filename = f"season_{sport}_d{division}_{season_year-1}-{season_year}.json"
        fetcher.save_to_json(contests, filename)
        fetcher.save_contest_ids_only(contests, filename.replace('.json', '.txt'))
        
        print(f"\n{'='*70}")
        print(f"NEXT STEP: Use these contest IDs with the scraper!")
        print(f"{'='*70}")
        print(f"\nRun this command to scrape all games:")
        print(f"  python bulk_scraper.py --input {filename.replace('.json', '.txt')}")
        print(f"{'='*70}\n")
    
    elif choice == "4":
        print("\nGoodbye!")
    
    else:
        print("\nInvalid choice!")


if __name__ == "__main__":
    main()
