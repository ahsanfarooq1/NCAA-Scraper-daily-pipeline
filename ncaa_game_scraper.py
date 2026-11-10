import requests
import json
import time
import random
import os
import argparse
import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional

class NCAAGameScraper:
    """
    Scraper for NCAA game data. Takes a JSON file with contest data
    and scrapes detailed boxscores for every game, including player stats.
    """
    
    def __init__(self, output_file: str = "Final_All_Games_Data_WBB_D1_2025_2026.json"): 
        self.base_url = "https://sdataprod.ncaa.com/"
        self.output_file = output_file
        output_dir = os.path.dirname(self.output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.ncaa.com/',
        }
        
        # New verified hash for detailed player boxscores
        self.boxscore_hash = "4a7fa26398db33de3ff51402a90eb5f25acef001cca28d239fe5361315d1419a"
        self.boxscore_meta = "NCAA_GetGamecenterBoxscoreBasketballById_web"
        
        self.successful_scrapes = 0
        self.failed_scrapes = 0
        self.failed_contests = []
    
    def get_game_boxscore(self, contest_id: str) -> Optional[Dict]:
        """Fetch full boxscore including player stats."""
        extensions = {"persistedQuery": {"version": 1, "sha256Hash": self.boxscore_hash}}
        variables = {"contestId": str(contest_id), "staticTestEnv": None}
        
        url = f"{self.base_url}?meta={self.boxscore_meta}&extensions={urllib.parse.quote(json.dumps(extensions))}&variables={urllib.parse.quote(json.dumps(variables))}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                
                # Check if we have valid boxscore data despite errors
                if data.get('data') and data['data'].get('boxscore'):
                    if "errors" in data:
                        print(f" [WARN] GraphQL errors present but data available. Proceeding with partial data.")
                    return data

                if "errors" in data: 
                    # Check for the specific "null" integer error which is a known NCAA API bug
                    msg = data['errors'][0].get('message', '')
                    if "Int cannot represent non-integer value: \"null\"" in msg:
                        return {"_error_type": "DATA_ISSUE", "message": msg}
                    print(f" [API ERROR] {json.dumps(data['errors'], indent=2)}")
                    return None
                return data
            return None
        except Exception as e:
            print(f" [EXC] {e}")
            return None
    
    def scrape_all(self, contests: List[Dict], delay_range: tuple = (1.0, 2.0)):
        all_results = []
        print(f"\n[INFO] Starting to scrape {len(contests)} games...")
        
        for i, contest in enumerate(contests, 1):
            cid = str(contest['contest_id'])
            print(f"[{i}/{len(contests)}] Scraping ID: {cid}...", end=" ", flush=True)
            data = self.get_game_boxscore(cid)
            
            if data:
                if "_error_type" in data:
                    print(f"[DATA-ISSUE]", end=" ", flush=True)
                    # Fallback to basic info from the input file
                    game_data = self._create_fallback_data(contest)
                    all_results.append(game_data)
                    print("[FALLBACK-OK]")
                    self.successful_scrapes += 1
                    continue

                print("[OK]")
                self.successful_scrapes += 1
                
                # Structured data for aggregate
                game_data = self._process_game_data(cid, data)
                all_results.append(game_data)
            else:
                print("[FAIL]")
                self.failed_scrapes += 1
                self.failed_contests.append(cid)
            
            if i < len(contests):
                time.sleep(random.uniform(*delay_range))
        
        # Save aggregate
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        
        print(f"\n[SUMMARY] Success: {self.successful_scrapes} | Failed: {self.failed_scrapes}")
    def _save_results(self, all_results: List[Dict]):
        """Saves current results to output file."""
        try:
            # Save to a temporary file first to avoid corruption if interrupted during write
            temp_file = self.output_file + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(all_results, f, indent=2, ensure_ascii=False)
            
            # Atomic replace
            if os.path.exists(self.output_file):
                os.remove(self.output_file)
            os.rename(temp_file, self.output_file)
        except Exception as e:
            print(f"\n[ERROR] Failed to save results: {e}")
    def _create_fallback_data(self, contest: Dict) -> Dict:
        """Creates a basic game record when the detailed API fails."""
        return {
            "contest_id": str(contest.get('contest_id')),
            "scraped_at": datetime.now().isoformat(),
            "description": contest.get('matchup', f"{contest.get('team1')} vs {contest.get('team2')}"),
            "status": contest.get('status', 'FINAL'),
            "note": "Basic data only - Detailed boxscore failed due to NCAA API issue (null player ID/number)",
            "results": [
                {
                    "team_name": contest.get('team1'),
                    "team_short": contest.get('team1'),
                    "team_id": None,
                    "is_home": None,
                    "team_stats": {},
                    "players": []
                },
                {
                    "team_name": contest.get('team2'),
                    "team_short": contest.get('team2'),
                    "team_id": None,
                    "is_home": None,
                    "team_stats": {},
                    "players": []
                }
            ]
        }
    
    def _process_game_data(self, contest_id: str, raw_data: Dict) -> Dict:
        """Processes the raw GraphQL response into a cleaner format."""
        boxscore = raw_data.get('data', {}).get('boxscore', {})
        processed = {
            "contest_id": contest_id,
            "scraped_at": datetime.now().isoformat(),
            "description": boxscore.get('description'),
            "status": boxscore.get('period'),
            "results": []
        }
        
        teams = {str(t['teamId']): t for t in boxscore.get('teams', [])}
        team_boxscores = boxscore.get('teamBoxscore', [])
        
        for tb in team_boxscores:
            team_id = str(tb.get('teamId'))
            team_info = teams.get(team_id, {})
            
            team_entry = {
                "team_name": team_info.get('nameFull'),
                "team_short": team_info.get('nameShort'),
                "team_id": team_id,
                "is_home": team_info.get('isHome'),
                "team_stats": tb.get('teamStats', {}),
                "players": tb.get('playerStats', [])
            }
            processed["results"].append(team_entry)
            
        return processed

def load_contest_objects(filename: str) -> List[Dict]:
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        contests = data
    elif isinstance(data, dict):
        contests = data.get('contests', [])
    else:
        contests = []
    
    # Ensure they have contest_id
    return [c for c in contests if isinstance(c, dict) and 'contest_id' in c]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", nargs='?', default="season_WBB_d1_2025-2026.json", help="Input JSON file with contest IDs")
    parser.add_argument("output_file", nargs='?', default="Final_All_Games_Data_WBB_D1_2025_2026.json", help="Output JSON file for all games")
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args() 
    
    if not os.path.exists(args.input_file):
        print(f"[ERROR] Input file not found: {args.input_file}")
        return
        
    contests = load_contest_objects(args.input_file)
    if not contests:
        print("[ERROR] No contest IDs found in file.")
        return
        
    scraper = NCAAGameScraper(output_file=args.output_file)
    scraper.scrape_all(contests, delay_range=(args.delay - 0.5, args.delay + 0.5))

if __name__ == "__main__":
    main()








