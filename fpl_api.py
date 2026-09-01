# FPL API Handler
# Fetches and caches data from the official FPL API
# Owner: Eduardo Maticorena

import requests
import json
import os
from datetime import datetime, timedelta

FPL_BASE_URL = 'https://fantasy.premierleague.com/api'
CACHE_FILE = 'data/fpl_cache.json'
CACHE_DURATION_HOURS = 1

def get_bootstrap_data():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        cache_time = datetime.fromisoformat(cache['cached_at'])
        if datetime.now() - cache_time < timedelta(hours=CACHE_DURATION_HOURS):
            return cache['data']

    print("Fetching fresh FPL data...")
    response = requests.get(f'{FPL_BASE_URL}/bootstrap-static/')
    response.raise_for_status()
    data = response.json()

    os.makedirs('data', exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump({'cached_at': datetime.now().isoformat(), 'data': data}, f)

    return data

def get_next_fixtures():
    """Get each team's next fixture with difficulty rating"""
    data = get_bootstrap_data()
    teams = {t['id']: t['name'] for t in data['teams']}

    response = requests.get(f'{FPL_BASE_URL}/fixtures/')
    response.raise_for_status()
    fixtures = response.json()

    events = data['events']
    current_gw = next((e['id'] for e in events if e['is_current']), None)
    next_gw = next((e['id'] for e in events if e['is_next']), None)
    target_gw = next_gw or current_gw

    next_fixtures = [f for f in fixtures if f['event'] == target_gw]

    team_fixtures = {}
    for f in next_fixtures:
        h_team = f['team_h']
        a_team = f['team_a']
        kickoff = f.get('kickoff_time', '')[:10] if f.get('kickoff_time') else 'TBC'

        team_fixtures[h_team] = {
            'opponent': teams.get(a_team, 'Unknown'),
            'difficulty': f['team_h_difficulty'],
            'is_home': True,
            'kickoff': kickoff,
            'gameweek': target_gw
        }
        team_fixtures[a_team] = {
            'opponent': teams.get(h_team, 'Unknown'),
            'difficulty': f['team_a_difficulty'],
            'is_home': False,
            'kickoff': kickoff,
            'gameweek': target_gw
        }

    return team_fixtures, target_gw

def get_all_players():
    data = get_bootstrap_data()
    players = data['elements']
    teams = {t['id']: t['name'] for t in data['teams']}
    team_id_map = {t['name']: t['id'] for t in data['teams']}
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
            'team_id': p['team'],
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
            'photo': p.get('photo', ''),
            'code': p.get('code', ''),
            'next_fixture': {},
            'gameweek': None,
        })

    # Add fixture data
    try:
        fixtures, target_gw = get_next_fixtures()
        for p in enriched:
            team_id = p['team_id']
            if team_id in fixtures:
                p['next_fixture'] = fixtures[team_id]
                p['gameweek'] = target_gw
    except Exception as e:
        print(f"Fixture fetch failed: {e}")

    return enriched

def search_player(name):
    players = get_all_players()
    name_lower = name.lower()
    return [p for p in players if name_lower in p['name'].lower()
            or name_lower in p['full_name'].lower()]

def get_player_status(status_code):
    statuses = {
        'a': 'Available',
        'd': 'Doubtful',
        'i': 'Injured',
        'n': 'Not available',
        's': 'Suspended',
        'u': 'Unavailable'
    }
    return statuses.get(status_code, 'Unknown')

def get_player_photo_url(code):
    """Get official FPL headshot URL"""
    if not code:
        return None
    return f"https://resources.premierleague.com/premierleague/photos/players/110x140/p{code}.png"

if __name__ == '__main__':
    players = get_all_players()
    print(f"Total available players: {len(players)}")
    for p in players[:5]:
        fix = p.get('next_fixture', {})
        print(f"{p['name']} | {p['team']} | Next: {fix.get('opponent','?')} ({'H' if fix.get('is_home') else 'A'}) | FDR: {fix.get('difficulty','?')}")