
import json
import os

season_file = r"d:\Kinetic Intellegence\NCAA_Scraper\season_WBB_d2_2025-2026.json"
final_file = r"d:\Kinetic Intellegence\NCAA_Scraper\Final_All_Games_Data_WBB_D2_2025_2026.json"

def verify():
    if not os.path.exists(season_file):
        print(f"Season file not found: {season_file}")
        return
    
    with open(season_file, 'r', encoding='utf-8') as f:
        season_data = json.load(f)
    
    contests = season_data.get('contests', [])
    season_ids = {str(c['contest_id']) for c in contests}
    
    print(f"Total contests in season file: {len(season_ids)}")
    
    if not os.path.exists(final_file):
        print(f"Final file not found: {final_file}")
        missing_ids = season_ids
    else:
        with open(final_file, 'r', encoding='utf-8') as f:
            try:
                final_data = json.load(f)
                final_ids = {str(r['contest_id']) for r in final_data}
            except json.JSONDecodeError:
                print("Error decoding final file. It might be empty or corrupted.")
                final_ids = set()
        
        print(f"Total contests in final file: {len(final_ids)}")
        
        missing_ids = season_ids - final_ids
        print(f"Missing contests: {len(missing_ids)}")
    
    if missing_ids:
        # Save missing IDs to a temporary file for the scraper
        with open('missing_contests.json', 'w', encoding='utf-8') as f:
            # Reconstruct contest objects for the scraper
            missing_contests = [c for c in contests if str(c['contest_id']) in missing_ids]
            json.dump(missing_contests, f, indent=2)
        print(f"Saved {len(missing_contests)} missing contests to missing_contests.json")
    else:
        print("No missing contests found.")

if __name__ == "__main__":
    verify()
