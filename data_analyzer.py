"""
NCAA Data Analyzer

Analyze and extract insights from scraped NCAA game data.
"""

import json
import os
from typing import List, Dict
from datetime import datetime


class NCAADataAnalyzer:
    """Analyze scraped NCAA game data"""
    
    def __init__(self, data_dir: str = "scraped_data"):
        self.data_dir = data_dir
        self.games = []
    
    def load_all_games(self):
        """Load all individual game files from the data directory"""
        self.games = []
        
        if not os.path.exists(self.data_dir):
            print(f"[ERROR] Directory not found: {self.data_dir}")
            return
        
        for filename in os.listdir(self.data_dir):
            if filename.startswith('game_') and filename.endswith('.json'):
                filepath = os.path.join(self.data_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        game_data = json.load(f)
                        self.games.append(game_data)
                except Exception as e:
                    print(f"[WARNING] Could not load {filename}: {e}")
        
        print(f"[INFO] Loaded {len(self.games)} games")
    
    def load_combined_file(self, filepath: str):
        """Load from a combined all_games_*.json file"""
        with open(filepath, 'r') as f:
            self.games = json.load(f)
        print(f"[INFO] Loaded {len(self.games)} games from {filepath}")
    
    def get_team_stats_summary(self, team_name: str = None):
        """Get aggregated statistics for a team across all games"""
        stats = {
            'games_played': 0,
            'total_points': 0,
            'total_rebounds': 0,
            'total_assists': 0,
            'total_turnovers': 0,
            'total_steals': 0,
            'total_blocks': 0,
            'field_goals_made': 0,
            'field_goals_attempted': 0,
            'three_points_made': 0,
            'three_points_attempted': 0,
        }
        
        for game in self.games:
            boxscore = game.get('data', {}).get('boxscore', {})
            teams = boxscore.get('teams', [])
            team_boxscores = boxscore.get('teamBoxscore', [])
            
            for i, team in enumerate(teams):
                if team_name is None or team_name.lower() in team.get('nameShort', '').lower():
                    if i < len(team_boxscores):
                        team_stats = team_boxscores[i].get('teamStats', {})
                        
                        stats['games_played'] += 1
                        stats['total_rebounds'] += int(team_stats.get('totalRebounds', 0))
                        stats['total_assists'] += int(team_stats.get('assists', 0))
                        stats['total_turnovers'] += int(team_stats.get('turnovers', 0))
                        stats['total_steals'] += int(team_stats.get('steals', 0))
                        stats['total_blocks'] += int(team_stats.get('blockedShots', 0))
                        
                        fg_made = int(team_stats.get('fieldGoalsMade', 0))
                        fg_att = int(team_stats.get('fieldGoalsAttempted', 0))
                        stats['field_goals_made'] += fg_made
                        stats['field_goals_attempted'] += fg_att
                        
                        three_made = int(team_stats.get('threePointsMade', 0))
                        three_att = int(team_stats.get('threePointsAttempted', 0))
                        stats['total_points'] += (fg_made * 2) + three_made + int(team_stats.get('freeThrowsMade', 0))
                        stats['three_points_made'] += three_made
                        stats['three_points_attempted'] += three_att
        
        # Calculate averages
        if stats['games_played'] > 0:
            stats['avg_points'] = stats['total_points'] / stats['games_played']
            stats['avg_rebounds'] = stats['total_rebounds'] / stats['games_played']
            stats['avg_assists'] = stats['total_assists'] / stats['games_played']
            stats['avg_turnovers'] = stats['total_turnovers'] / stats['games_played']
            stats['fg_percentage'] = (stats['field_goals_made'] / stats['field_goals_attempted'] * 100) if stats['field_goals_attempted'] > 0 else 0
            stats['three_pt_percentage'] = (stats['three_points_made'] / stats['three_points_attempted'] * 100) if stats['three_points_attempted'] > 0 else 0
        
        return stats
    
    def get_all_teams(self) -> List[str]:
        """Get a list of all unique teams in the dataset"""
        teams = set()
        for game in self.games:
            boxscore = game.get('data', {}).get('boxscore', {})
            for team in boxscore.get('teams', []):
                teams.add(team.get('nameShort', ''))
        return sorted(list(teams))
    
    def get_game_summaries(self) -> List[Dict]:
        """Get a summary of all games"""
        summaries = []
        
        for game in self.games:
            boxscore = game.get('data', {}).get('boxscore', {})
            teams = boxscore.get('teams', [])
            team_boxscores = boxscore.get('teamBoxscore', [])
            
            if len(teams) >= 2 and len(team_boxscores) >= 2:
                # Calculate scores
                team1_stats = team_boxscores[0].get('teamStats', {})
                team2_stats = team_boxscores[1].get('teamStats', {})
                
                team1_score = calculate_score(team1_stats)
                team2_score = calculate_score(team2_stats)
                
                summary = {
                    'contest_id': boxscore.get('contestId'),
                    'description': boxscore.get('description'),
                    'status': boxscore.get('period'),
                    'sport': boxscore.get('sportCode'),
                    'team1': teams[0].get('nameShort'),
                    'team2': teams[1].get('nameShort'),
                    'team1_score': team1_score,
                    'team2_score': team2_score,
                    'winner': teams[0].get('nameShort') if team1_score > team2_score else teams[1].get('nameShort')
                }
                summaries.append(summary)
        
        return summaries
    
    def print_analysis(self, team_name: str = None):
        """Print comprehensive analysis"""
        print("\n" + "="*70)
        print("NCAA GAME DATA ANALYSIS")
        print("="*70)
        
        print(f"\nTotal Games: {len(self.games)}")
        
        # All teams
        teams = self.get_all_teams()
        print(f"Total Unique Teams: {len(teams)}")
        print(f"Teams: {', '.join(teams[:10])}" + ("..." if len(teams) > 10 else ""))
        
        # Game summaries
        summaries = self.get_game_summaries()
        print(f"\n{'='*70}")
        print("GAME SUMMARIES")
        print("="*70)
        
        for summary in summaries[:10]:  # Show first 10
            print(f"\n{summary['description']}")
            print(f"  {summary['team1']}: {summary['team1_score']}")
            print(f"  {summary['team2']}: {summary['team2_score']}")
            print(f"  Winner: {summary['winner']} ({summary['status']})")
        
        if len(summaries) > 10:
            print(f"\n... and {len(summaries) - 10} more games")
        
        # Team-specific analysis
        if team_name:
            print(f"\n{'='*70}")
            print(f"TEAM ANALYSIS: {team_name}")
            print("="*70)
            
            stats = self.get_team_stats_summary(team_name)
            
            if stats['games_played'] > 0:
                print(f"\nGames Played: {stats['games_played']}")
                print(f"\nAverages:")
                print(f"  Points: {stats['avg_points']:.1f}")
                print(f"  Rebounds: {stats['avg_rebounds']:.1f}")
                print(f"  Assists: {stats['avg_assists']:.1f}")
                print(f"  Turnovers: {stats['avg_turnovers']:.1f}")
                print(f"\nShooting:")
                print(f"  FG%: {stats['fg_percentage']:.1f}%")
                print(f"  3PT%: {stats['three_pt_percentage']:.1f}%")
                print(f"\nTotals:")
                print(f"  Total Points: {stats['total_points']}")
                print(f"  Total Rebounds: {stats['total_rebounds']}")
                print(f"  Total Assists: {stats['total_assists']}")
            else:
                print(f"No games found for team: {team_name}")
        
        print("\n" + "="*70)
    
    def export_to_csv(self, output_file: str = "ncaa_games.csv"):
        """Export game summaries to CSV"""
        summaries = self.get_game_summaries()
        
        if not summaries:
            print("[ERROR] No data to export")
            return
        
        import csv
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=summaries[0].keys())
            writer.writeheader()
            writer.writerows(summaries)
        
        print(f"[OK] Exported {len(summaries)} games to {output_file}")


def calculate_score(team_stats: Dict) -> int:
    """Calculate total score from team stats"""
    fg_made = int(team_stats.get('fieldGoalsMade', 0))
    three_made = int(team_stats.get('threePointsMade', 0))
    ft_made = int(team_stats.get('freeThrowsMade', 0))
    
    # Points = (FG - 3PT)*2 + 3PT*3 + FT
    two_pointers = fg_made - three_made
    return (two_pointers * 2) + (three_made * 3) + ft_made


def main():
    """Example usage"""
    analyzer = NCAADataAnalyzer(data_dir="ncaa_games_data")
    
    # Load data
    analyzer.load_all_games()
    
    if len(analyzer.games) == 0:
        print("\n[INFO] No games found. Run the scraper first!")
        print("Example: python ncaa_game_scraper.py")
        return
    
    # Print analysis
    analyzer.print_analysis()
    
    # If you want team-specific analysis, uncomment:
    # analyzer.print_analysis(team_name="UNI")
    
    # Export to CSV
    analyzer.export_to_csv("ncaa_analysis.csv")
    
    print("\n" + "="*70)
    print("USAGE EXAMPLES")
    print("="*70)
    print("""
1. Analyze specific team:
    analyzer = NCAADataAnalyzer("ncaa_games_data")
    analyzer.load_all_games()
    analyzer.print_analysis(team_name="UNI")

2. Get team statistics:
    stats = analyzer.get_team_stats_summary("South Dakota")
    print(f"Average points: {stats['avg_points']:.1f}")

3. Export to CSV:
    analyzer.export_to_csv("my_games.csv")

4. Load from combined file:
    analyzer.load_combined_file("all_games_20260209_164824.json")
    analyzer.print_analysis()
""")


if __name__ == "__main__":
    main()
