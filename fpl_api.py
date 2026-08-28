# FPL API Handler
# Fetches and caches data from the official FPL API

import requests
import json
import os
from datetime import datetime, timedelta

FPL_BASE_URL = 'https://fantasy.premierleague.com/api'
CACHE_FILE = 'data/fpl_cache.json'
CACHE_DURATION_HOURS = 1

def get_bootstrap_data():
    """Fetch all FPL data with caching to avoid hitting API too often"""
    
    # Check if cache exists and is fresh
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        cache_time = datetime.fromisoformat(cache['cached_at'])
        if datetime.now() - cache_time < timedelta(hours=CACHE_DURATION_HOURS):
            return cache['data']

    # Fetch fresh data
    print("Fetching fresh FPL data...")
    response = requests.get(f'{FPL_BASE_URL}/bootstrap-static/')
    response.raise_for_status()
    data = response.json()

    # Save to cache
    os.makedirs('data', exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump({'cached_at': datetime.now().isoformat(), 'data': data}, f)

    return data

def get_all_players():
    """Get all players with enriched data"""
    data = get_bootstrap_data()
    players = data['elements']
    teams = {t['id']: t['name'] for t in data['teams']}
    positions = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}

    enriched = []
    for p in players:
        if p.get('removed') or not p.get('can_select'):
            continue
        enriched.append({
            'id': p['id'],
            'name': p['web_name'],
            'full_name': f"{p['first_name']} {p['second_name']}",
            'team': teams.get(p['team'], 'Unknown'),
            'position': positions.get(p['element_type'], 'Unknown'),
            'price': p['now_cost'] / 10,
            'total_points': p['total_points'],
            'points_per_game': float(p['points_per_game'] or 0),
            'form': float(p['form'] or 0),
            'selected_by': float(p['selected_by_percent'] or 0),
            'goals': p['goals_scored'],
            'assists': p['assists'],
            'clean_sheets': p['clean_sheets'],
            'minutes': p['minutes'],
            'ict_index': float(p['ict_index'] or 0),
            'expected_goals': float(p['expected_goals'] or 0),
            'expected_assists': float(p['expected_assists'] or 0),
            'bonus': p['bonus'],
            'bps': p['bps'],
            'status': p['status'],
            'news': p['news'],
            'ep_next': float(p['ep_next'] or 0),
            'transfers_in': p['transfers_in_event'],
            'transfers_out': p['transfers_out_event'],
            'value_season': float(p['value_season'] or 0),
        })
    return enriched

def search_player(name):
    """Search for a player by name"""
    players = get_all_players()
    name_lower = name.lower()
    results = [p for p in players if name_lower in p['name'].lower() 
               or name_lower in p['full_name'].lower()]
    return results

def get_player_status(status_code):
    """Convert status code to readable text"""
    statuses = {
        'a': 'Available',
        'd': 'Doubtful',
        'i': 'Injured',
        'n': 'Not available',
        's': 'Suspended',
        'u': 'Unavailable'
    }
    return statuses.get(status_code, 'Unknown')

if __name__ == '__main__':
    # Test it
    players = get_all_players()
    print(f"Total available players: {len(players)}")
    
    # Search for a player
    results = search_player('Salah')
    for p in results:
        print(f"{p['name']} | {p['team']} | {p['position']} | £{p['price']}m | {p['total_points']}pts")