import json
import os

def check_missing_contests(source_file, scraped_file, output_file):
    # Load source contests
    with open(source_file, 'r', encoding='utf-8') as f:
        source_data = json.load(f)
    
    source_ids = set()
    source_map = {} # To preserve original contest objects
    
    if isinstance(source_data, dict) and 'contests' in source_data:
        for c in source_data['contests']:
            cid = str(c['contest_id'])
            source_ids.add(cid)
            source_map[cid] = c
    elif isinstance(source_data, list):
        for c in source_data:
            cid = str(c['contest_id'])
            source_ids.add(cid)
            source_map[cid] = c
            
    print(f"Total contests in source: {len(source_ids)}")

    # Load scraped contests
    if not os.path.exists(scraped_file):
        print(f"Scraped file not found: {scraped_file}")
        scraped_ids = set()
    else:
        with open(scraped_file, 'r', encoding='utf-8') as f:
            scraped_data = json.load(f)
        
        scraped_ids = {str(c['contest_id']) for c in scraped_data if 'contest_id' in c}
        print(f"Total contests successfully scraped: {len(scraped_ids)}")

    # Find missing
    missing_ids = sorted(list(source_ids - scraped_ids))
    print(f"Total missing contests: {len(missing_ids)}")

    # Create missing list in same format as source
    missing_contests = [source_map[cid] for cid in missing_ids]
    
    output_dict = {
        "total_missing": len(missing_contests),
        "contests": missing_contests
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_dict, f, indent=2, ensure_ascii=False)
    
    print(f"Missing contests saved to: {output_file}")

if __name__ == "__main__":
    check_missing_contests(
        "season_WBB_d1_2024-2025.json",
        "Final_All_Games_Data_WBB_D1_2024_2025.json",
        "missing_contests_WBB_D1_2024_2025.json"
    )
