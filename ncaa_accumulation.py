import json
import os
import re
import sys
from collections import defaultdict
import glob

def safe_float(value):
    """Safely convert value to float, handling strings with minutes:seconds or percentages."""
    try:
        if value is None:
            return 0.0
        if isinstance(value, str):
            value = value.replace('%', '')
            if ':' in value:
                parts = value.split(':')
                if len(parts) == 2:
                    return float(parts[0]) + float(parts[1]) / 60.0
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def calculate_percentage(made, attempted):
    if attempted == 0:
        return 0.0
    return round((made / attempted) * 100)

def calculate_ratio(num, den):
    if den == 0:
        return 0.0
    return round(num / den, 2)

def process_ncaa_file(input_file, output_file, skip_empty=True):
    """skip_empty=True ignores games whose boxscore has no player rows (not final /
    not posted yet) so they don't inflate GP. Use --keep-empty on the CLI to restore
    the old behaviour."""
    print(f"Reading {input_file}...")
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {input_file}: {e}")
        return

    # all_teams_data[team_id] = { 'team_name': name, 'players': { name: stats }, 'season_totals': stats }
    all_teams_data = {}

    skipped_empty = 0
    for contest in data:
        results = contest.get('results', [])
        if skip_empty and not any(t.get('players') for t in results):
            skipped_empty += 1
            continue
        for team_info in results:
            t_id = str(team_info.get('team_id', 'Unknown'))
            t_name = team_info.get('team_name', 'Unknown')
            
            if t_id not in all_teams_data:
                all_teams_data[t_id] = {
                    'team_name': t_name,
                    'players': defaultdict(lambda: {
                        'GP': 0, 'Min': 0.0, 'Pts': 0.0, 'FGM': 0.0, 'FGA': 0.0,
                        '3PM': 0.0, '3PA': 0.0, 'FTM': 0.0, 'FTA': 0.0, '2FGM': 0.0, '2FGA': 0.0,
                        'OReb': 0.0, 'DReb': 0.0, 'Reb': 0.0, 'Ast': 0.0, 'Stl': 0.0, 'Blk': 0.0,
                        'TO': 0.0, 'PF': 0.0, 'Chr': 0.0, 'Defl': 0.0, 'TF': 0.0,
                        'DD': 0, 'TD': 0
                    }),
                    'season_totals': {
                        'GP': 0, 'Min': 0.0, 'Pts': 0.0, 'FGM': 0.0, 'FGA': 0.0,
                        '3PM': 0.0, '3PA': 0.0, 'FTM': 0.0, 'FTA': 0.0, '2FGM': 0.0, '2FGA': 0.0,
                        'OReb': 0.0, 'DReb': 0.0, 'Reb': 0.0, 'Ast': 0.0, 'Stl': 0.0, 'Blk': 0.0,
                        'TO': 0.0, 'PF': 0.0, 'Chr': 0.0, 'Defl': 0.0, 'TF': 0.0,
                        'DD': 0, 'TD': 0
                    }
                }

            team_players = all_teams_data[t_id]['players']
            season_t = all_teams_data[t_id]['season_totals']
            
            # Use team_stats if available for the team season record, 
            # or sum players. Let's sum players to ensure consistency 
            # with individual player records.
            # But we increment the team's GP (Games Played) once per contest.
            season_t['GP'] += 1

            players = team_info.get('players', [])
            for p in players:
                first = p.get('firstName', '')
                last = p.get('lastName', '')
                p_handle = f"{first} {last}".strip()
                if not p_handle:
                    continue
                
                # Check for "Team" records in players
                if p_handle.lower() == "team":
                    continue

                stats = team_players[p_handle]
                stats['GP'] += 1
                
                # Extract stats from NCAA structure
                p_pts = safe_float(p.get('points'))
                p_min = safe_float(p.get('minutesPlayed'))
                p_fgm = safe_float(p.get('fieldGoalsMade'))
                p_fga = safe_float(p.get('fieldGoalsAttempted'))
                p_3pm = safe_float(p.get('threePointsMade'))
                p_3pa = safe_float(p.get('threePointsAttempted'))
                p_ftm = safe_float(p.get('freeThrowsMade'))
                p_fta = safe_float(p.get('freeThrowsAttempted'))
                p_oreb = safe_float(p.get('offensiveRebounds'))
                p_reb = safe_float(p.get('totalRebounds'))
                p_ast = safe_float(p.get('assists'))
                p_stl = safe_float(p.get('steals'))
                p_blk = safe_float(p.get('blockedShots'))
                p_to = safe_float(p.get('turnovers'))
                p_pf = safe_float(p.get('personalFouls'))
                
                # Calculate derived
                p_2fm = p_fgm - p_3pm
                p_2fa = p_fga - p_3pa
                p_dreb = p_reb - p_oreb
                
                # Update Player Accumulation
                stats['Min'] += p_min
                stats['Pts'] += p_pts
                stats['FGM'] += p_fgm
                stats['FGA'] += p_fga
                stats['3PM'] += p_3pm
                stats['3PA'] += p_3pa
                stats['FTM'] += p_ftm
                stats['FTA'] += p_fta
                stats['2FGM'] += p_2fm
                stats['2FGA'] += p_2fa
                stats['OReb'] += p_oreb
                stats['DReb'] += p_dreb
                stats['Reb'] += p_reb
                stats['Ast'] += p_ast
                stats['Stl'] += p_stl
                stats['Blk'] += p_blk
                stats['TO'] += p_to
                stats['PF'] += p_pf
                
                # Update Team Accumulation
                season_t['Min'] += p_min
                season_t['Pts'] += p_pts
                season_t['FGM'] += p_fgm
                season_t['FGA'] += p_fga
                season_t['3PM'] += p_3pm
                season_t['3PA'] += p_3pa
                season_t['FTM'] += p_ftm
                season_t['FTA'] += p_fta
                season_t['2FGM'] += p_2fm
                season_t['2FGA'] += p_2fa
                season_t['OReb'] += p_oreb
                season_t['DReb'] += p_dreb
                season_t['Reb'] += p_reb
                season_t['Ast'] += p_ast
                season_t['Stl'] += p_stl
                season_t['Blk'] += p_blk
                season_t['TO'] += p_to
                season_t['PF'] += p_pf
                
                # Double-Double / Triple-Double check for this game
                cats = [p_pts, p_reb, p_ast, p_stl, p_blk]
                double_digit_count = sum(1 for x in cats if x >= 10)
                if double_digit_count >= 2:
                    stats['DD'] += 1
                    season_t['DD'] += 1
                if double_digit_count >= 3:
                    stats['TD'] += 1
                    season_t['TD'] += 1

    # Final formatting
    print(f"Formatting {len(all_teams_data)} teams...")
    final_output_list = []
    
    for t_id, t_data in all_teams_data.items():
        team_name = t_data['team_name']
        
        def format_record(name, acc, record_type):
            gp = acc['GP']
            gp_calc = gp if gp > 0 else 1
            
            res = {
                'team_id': t_id,
                'team_name': team_name,
                'record_type': record_type,
                'Name': name,
                'GP': gp,
                'MPG': round(acc['Min'] / gp_calc, 1),
                'PPG': round(acc['Pts'] / gp_calc, 1),
                'DEFR': round(acc['DReb'] / gp_calc, 1),
                'OFFR': round(acc['OReb'] / gp_calc, 1),
                'RPG': round(acc['Reb'] / gp_calc, 1),
                'APG': round(acc['Ast'] / gp_calc, 1),
                'SPG': round(acc['Stl'] / gp_calc, 1),
                'BPG': round(acc['Blk'] / gp_calc, 1),
                'TPG': round(acc['TO'] / gp_calc, 1),
                'PFPG': round(acc['PF'] / gp_calc, 1),
                
                'Min': int(acc['Min']),
                'Pts': int(acc['Pts']),
                'FGM': int(acc['FGM']),
                'FGA': int(acc['FGA']),
                'FG%': calculate_percentage(acc['FGM'], acc['FGA']),
                'PPS': round(acc['Pts'] / acc['FGA'], 1) if acc['FGA'] > 0 else 0.0,
                'AFG%': calculate_percentage(acc['FGM'] + 0.5 * acc['3PM'], acc['FGA']),
                
                '3PM': int(acc['3PM']),
                '3PA': int(acc['3PA']),
                '3P%': calculate_percentage(acc['3PM'], acc['3PA']),
                'FTM': int(acc['FTM']),
                'FTA': int(acc['FTA']),
                'FT%': calculate_percentage(acc['FTM'], acc['FTA']),
                '2FGM': int(acc['2FGM']),
                '2FGA': int(acc['2FGA']),
                '2FG%': calculate_percentage(acc['2FGM'], acc['2FGA']),
                
                'OReb': int(acc['OReb']),
                'DReb': int(acc['DReb']),
                'Reb': int(acc['Reb']),
                'Ast': int(acc['Ast']),
                'Stl': int(acc['Stl']),
                'Blk': int(acc['Blk']),
                'TO': int(acc['TO']),
                'PF': int(acc['PF']),
                
                'Ast:TO': calculate_ratio(acc['Ast'], acc['TO']),
                'Stl:TO': calculate_ratio(acc['Stl'], acc['TO']),
                'Stl:PF': calculate_ratio(acc['Stl'], acc['PF']),
                'Blk:PF': calculate_ratio(acc['Blk'], acc['PF']),
                'Chr': int(acc['Chr']),
                'Defl': int(acc['Defl']),
                'TF': int(acc['TF']),
                'DD': acc['DD'],
                'TD': acc['TD']
            }
            
            # Per 40 for NCAA (MaxPreps used Per 32)
            if acc['Min'] > 0:
                res['Per_40'] = {
                    'Pts': round((acc['Pts'] / acc['Min']) * 40, 1),
                    'Reb': round((acc['Reb'] / acc['Min']) * 40, 1),
                    'Ast': round((acc['Ast'] / acc['Min']) * 40, 1),
                    'Stl': round((acc['Stl'] / acc['Min']) * 40, 1),
                    'Blk': round((acc['Blk'] / acc['Min']) * 40, 1)
                }
                # Also include Per_32 if they specifically want it to match existing schema
                res['Per_32'] = {
                    'Pts': round((acc['Pts'] / acc['Min']) * 32, 1),
                    'Reb': round((acc['Reb'] / acc['Min']) * 32, 1),
                    'Ast': round((acc['Ast'] / acc['Min']) * 32, 1),
                    'Stl': round((acc['Stl'] / acc['Min']) * 32, 1),
                    'Blk': round((acc['Blk'] / acc['Min']) * 32, 1)
                }
            else:
                res['Per_40'] = None
                res['Per_32'] = None
                
            return res

        # Add team totals
        final_output_list.append(format_record("Season Totals", t_data['season_totals'], "team_total"))
        # Add players
        for p_name, p_acc in t_data['players'].items():
            final_output_list.append(format_record(p_name, p_acc, "player"))

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_output_list, f, indent=4)
        if skip_empty and skipped_empty:
            print(f"  (ignored {skipped_empty} games with no player data - not final / not posted yet)")
        print(f"Successfully processed {input_file} -> {output_file} ({len(final_output_list)} records)")
    except Exception as e:
        print(f"Error saving {output_file}: {e}")

def main():
    # Look in every season data folder (see ncaa_paths.py); each Accumulated_Stats
    # file is written NEXT TO its Final_All_Games_Data input.
    from ncaa_paths import all_data_dirs
    directories = all_data_dirs()

    # Optional filter tokens on the command line, e.g. "2025_2026" to do only
    # the 2025-26 season, or "MBB" to do only men's. Multiple tokens are ANDed.
    skip_empty = "--keep-empty" not in sys.argv
    filters = [a for a in sys.argv[1:] if not a.startswith("-")]

    # Only the canonical data files: Final_All_Games_Data_{MBB|WBB}_D{1,2,3}_{YYYY}_{YYYY}.json
    # (excludes .bak / .tmp / any other stray matches).
    canonical = re.compile(r"^Final_All_Games_Data_(MBB|WBB)_D[123]_\d{4}_\d{4}\.json$")

    input_files = sorted(
        f for d in directories
        for f in glob.glob(os.path.join(d, "Final_All_Games_Data_*.json"))
        if canonical.match(os.path.basename(f))
        and all(tok in os.path.basename(f) for tok in filters)
    )

    if not input_files:
        print(f"No matching Final_All_Games_Data_*.json files in {directories}"
              + (f" for filter {filters}" if filters else ""))
        return

    print(f"Found {len(input_files)} file(s) to process"
          + (f" (filter: {' '.join(filters)})" if filters else "") + ":")
    for f in input_files:
        print(f"  - {os.path.basename(f)}")

    for infile in input_files:
        filename = os.path.basename(infile)
        # Create output filename: replace 'Final_All_Games_Data' with 'Accumulated_Stats'
        outname = filename.replace("Final_All_Games_Data", "Accumulated_Stats")
        outfile = os.path.join(os.path.dirname(infile), outname)
        process_ncaa_file(infile, outfile, skip_empty=skip_empty)

if __name__ == "__main__":
    main()
