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
    
    def __init__(self, output_file: str = "Final_All_Games_Data_WBB_D2_2025_2026.json",
                 cf_session=None):
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
        # Optional Cloudflare-resilient session (curl_cffi + headful fallback).
        # When None, falls back to plain requests (unchanged behaviour).
        self.cf_session = cf_session
        
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
            if self.cf_session is not None:
                response = self.cf_session.get(url, timeout=30)
            else:
                response = requests.get(url, headers=self.headers, timeout=30)
            if response is not None and response.status_code == 200:
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
    
    @staticmethod
    def _has_players(record: Dict) -> bool:
        """A record is 'done' only if it actually carries player rows. A boxscore
        scraped before the NCAA posted it is an empty shell - we must re-fetch it,
        not treat it as done (the 'empty placeholder' trap)."""
        return sum(len(t.get("players") or []) for t in record.get("results", [])) > 0

    def scrape_all(self, contests: List[Dict], delay_range: tuple = (1.0, 2.0),
                   refresh_empty: bool = True):
        # Key by contest_id so a re-fetch REPLACES an empty shell instead of
        # appending a duplicate.
        results_by_id: Dict[str, Dict] = {}

        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    for r in json.load(f):
                        results_by_id[str(r['contest_id'])] = r
                print(f"[INFO] Found {len(results_by_id)} existing records. Resuming...")
            except Exception as e:
                print(f"[WARN] Could not load existing results: {e}")
                results_by_id = {}

        # Which ids are truly done. With refresh_empty, zero-player shells are
        # NOT done and get re-scraped; without it, any existing record counts.
        if refresh_empty:
            done_ids = {cid for cid, r in results_by_id.items() if self._has_players(r)}
            empty_n = len(results_by_id) - len(done_ids)
            if empty_n:
                print(f"[INFO] {empty_n} existing records have no player data "
                      f"- will re-try them (may now be final).")
        else:
            done_ids = set(results_by_id.keys())
        self.successful_scrapes = len(done_ids)

        todo = [c for c in contests if str(c['contest_id']) not in done_ids]
        print(f"\n[INFO] {len(todo)} games to scrape ({len(done_ids)} already complete).")

        try:
            for i, contest in enumerate(todo, 1):
                cid = str(contest['contest_id'])

                print(f"[{i}/{len(todo)}] Scraping ID: {cid}...", end=" ", flush=True)
                data = self.get_game_boxscore(cid)

                if data:
                    if "_error_type" in data:
                        print(f"[DATA-ISSUE]", end=" ", flush=True)
                        # Fallback to basic info from the input file
                        results_by_id[cid] = self._create_fallback_data(contest)
                        print("[FALLBACK-OK]")
                        self.successful_scrapes += 1
                        continue

                    # Structured data for aggregate (replaces any empty shell)
                    game_data = self._process_game_data(cid, data)
                    results_by_id[cid] = game_data
                    print("[OK]" if self._has_players(game_data) else "[OK-still-empty]")
                    self.successful_scrapes += 1
                else:
                    print("[FAIL]")
                    self.failed_scrapes += 1
                    self.failed_contests.append(cid)

                # Save progress every 20 games to avoid losing data
                if self.successful_scrapes % 20 == 0:
                    self._save_results(list(results_by_id.values()))

                if i < len(todo):
                    time.sleep(random.uniform(*delay_range))
        except KeyboardInterrupt:
            print("\n[INFO] Interrupted by user. Saving progress...")

        # Save aggregate
        self._save_results(list(results_by_id.values()))

        with_players = sum(1 for r in results_by_id.values() if self._has_players(r))
        print(f"\n[SUMMARY] Total Records: {len(results_by_id)} "
              f"| With players: {with_players} | Empty: {len(results_by_id) - with_players} "
              f"| Failed this run: {self.failed_scrapes}")

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
        data_part = raw_data.get('data') or {}
        boxscore = data_part.get('boxscore') or {}
        
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
    parser.add_argument("input_file", nargs='?', default="season_WBB_d2_2025-2026.json", help="Input JSON file with contest IDs")
    parser.add_argument("output_file", nargs='?', default="Final_All_Games_Data_WBB_D2_2025_2026.json", help="Output JSON file for all games")
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--cf", action="store_true",
                        help="Use the Cloudflare-resilient session (curl_cffi + headful fallback)")
    parser.add_argument("--attach", action="store_true",
                        help="Attach to a real Chrome on a debug port (implies --cf)")
    parser.add_argument("--headful", action="store_true",
                        help="Open a headful Chrome up-front to mint clearance (implies --cf)")
    parser.add_argument("--cdp-url", default="http://localhost:9222")
    parser.add_argument("--no-refresh-empty", action="store_true",
                        help="Do NOT re-scrape existing zero-player records (default: re-scrape them)")
    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        print(f"[ERROR] Input file not found: {args.input_file}")
        return

    contests = load_contest_objects(args.input_file)
    if not contests:
        print("[ERROR] No contest IDs found in file.")
        return

    cf_session = None
    if args.cf or args.attach or args.headful:
        from ncaa_cf import CFSession
        cf_session = CFSession(min_interval=max(args.delay - 0.5, 0.5),
                               headful=args.headful, attached=args.attach,
                               cdp_url=args.cdp_url)

    scraper = NCAAGameScraper(output_file=args.output_file, cf_session=cf_session)
    # The CF session throttles internally; don't double-sleep when it's active.
    delay_range = (0.0, 0.0) if cf_session is not None else (args.delay - 0.5, args.delay + 0.5)
    try:
        scraper.scrape_all(contests, delay_range=delay_range,
                           refresh_empty=not args.no_refresh_empty)
    finally:
        if cf_session is not None:
            cf_session.close()

if __name__ == "__main__":
    main()








