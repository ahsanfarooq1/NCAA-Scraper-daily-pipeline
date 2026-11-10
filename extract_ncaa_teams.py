import json
import os
import re
from ncaa_paths import data_dir, LEGACY_DIR

def extract_ncaa_team_details(file_path):
    """ Extracts team_name and state from the given NCAA JSON file. City and state are kept empty. """
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return []
    
    try:
        print(f"Reading {file_path}...")
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        teams_dict = {}
        # Regex to find state in parentheses if present
        state_regex = re.compile(r'\(([^)]+)\)')
        
        for record in data:
            name = record.get('team_name')
            if name:
                # Find state in parentheses if it exists
                match = state_regex.search(name)
                state = match.group(1) if match else ""
                
                # City is always empty as per previous requests
                city = ""
                
                # Use name + state as unique ID
                unique_id = f"{name}|{state}"
                if unique_id not in teams_dict:
                    teams_dict[unique_id] = {
                        "team_name": name,
                        "city": city,
                        "state": state
                    }
                            
        # Sort by team_name
        sorted_teams = sorted(teams_dict.values(), key=lambda x: x['team_name'])
        return sorted_teams
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return []

def _acc_path(sport, div, season):
    """NCAA_Accumulated_Stats_* (current naming); older seasons may still use Accumulated_Stats_*."""
    folder = data_dir(int(season[:4]), create=False)
    tail = f"{sport}_D{div}_{season.replace('-', '_')}.json"
    new = os.path.join(folder, "NCAA_Accumulated_Stats_" + tail)
    return new if os.path.exists(new) else os.path.join(folder, "Accumulated_Stats_" + tail)


def main():
    # Team lists (Ncaa_*_Teams_d*.json) live in the legacy folder with the older seasons.
    # Add the new season string here each year (accumulated files come from that
    # season's own data folder).
    base_dir = LEGACY_DIR
    seasons = ["2024-2025", "2025-2026", "2026-2027"]

    all_configs = []
    for sport, label in (("MBB", "men"), ("WBB", "Women")):
        for div in (1, 2, 3):
            all_configs.append({
                "output": f"Ncaa_{label}_Teams_d{div}.json",
                "files": {s: _acc_path(sport, div, s) for s in seasons},
            })

    for config in all_configs:
        print(f"\n--- Generating {config['output']} ---")
        final_data = {}
        for season, file_path in config['files'].items():
            teams = extract_ncaa_team_details(file_path)
            final_data[season] = teams
            print(f"Season {season}: Found {len(teams)} teams.")

        output_path = os.path.join(base_dir, config['output'])
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=4)
        print(f"Saved to {output_path}")

if __name__ == "__main__":
    main()
