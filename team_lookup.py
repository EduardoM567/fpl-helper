# Team Lookup - Fetch and analyze user's real FPL team
# Owner: Eduardo Maticorena

import requests
from fpl_api import get_all_players, get_player_status, get_player_photo_url

def get_current_gameweek():
    """Get the current or next gameweek number"""
    from fpl_api import get_bootstrap_data
    data = get_bootstrap_data()
    events = data['events']
    current = next((e['id'] for e in events if e['is_current']), None)
    return current or 1

def get_user_team(team_id, gameweek=None):
    """Fetch a user's real FPL squad by Team ID"""
    if gameweek is None:
        gameweek = get_current_gameweek()

    url = f'https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/'
    response = requests.get(url)

    if response.status_code != 200:
        return None

    data = response.json()
    all_players = get_all_players()
    players_by_id = {p['id']: p for p in all_players}

    squad = []
    for pick in data['picks']:
        player = players_by_id.get(pick['element'])
        if not player:
            continue

        player = dict(player)  # copy so we don't mutate the cache
        player['is_captain'] = pick['is_captain']
        player['is_vice_captain'] = pick['is_vice_captain']
        player['is_starting'] = pick['multiplier'] > 0
        player['status_text'] = get_player_status(player['status'])
        player['photo_url'] = get_player_photo_url(player.get('code'))
        squad.append(player)

    return {
        'squad': squad,
        'total_points': data['entry_history']['total_points'],
        'gameweek_points': data['entry_history']['points'],
        'rank': data['entry_history']['overall_rank'],
        'bank': data['entry_history']['bank'] / 10,
        'team_value': data['entry_history']['value'] / 10,
        'gameweek': gameweek
    }


def analyze_team(team_data):
    """Generate suggestions for the user's team"""
    squad = team_data['squad']
    starting = [p for p in squad if p['is_starting']]
    bench = [p for p in squad if not p['is_starting']]

    suggestions = []

    # Check for injured/unavailable starters
    for p in starting:
        if p['status'] in ['i', 's', 'n']:
            suggestions.append({
                'type': 'urgent',
                'player': p['name'],
                'message': f"{p['name']} is {p['status_text']} — consider transferring out before the deadline."
            })
        elif p['status'] == 'd':
            suggestions.append({
                'type': 'warning',
                'player': p['name'],
                'message': f"{p['name']} is doubtful — check news before the deadline."
            })

    # Check for hard fixtures among starters
    for p in starting:
        fix = p.get('next_fixture', {})
        if fix.get('difficulty', 3) >= 4:
            suggestions.append({
                'type': 'info',
                'player': p['name'],
                'message': f"{p['name']} faces a tough fixture vs {fix.get('opponent','?')} (FDR {fix['difficulty']}) — consider benching if you have a better option."
            })

    # Check for in-form bench players
    for p in bench:
        if p['form'] >= 6.0:
            fix = p.get('next_fixture', {})
            suggestions.append({
                'type': 'tip',
                'player': p['name'],
                'message': f"{p['name']} is in great form ({p['form']}) but benched — consider starting them over a weaker starter."
            })

    return suggestions


if __name__ == '__main__':
    team = get_user_team(5292186)
    print(f"Total points: {team['total_points']}")
    print(f"GW points: {team['gameweek_points']}")
    print(f"Team value: £{team['team_value']}m | Bank: £{team['bank']}m")
    print()
    for p in team['squad']:
        role = 'C' if p['is_captain'] else ('VC' if p['is_vice_captain'] else '')
        starting = 'START' if p['is_starting'] else 'BENCH'
        print(f"{starting} | {p['name']} {role} | {p['position']} | £{p['price']}m")
    
    print()
    print("Suggestions:")
    suggestions = analyze_team(team)
    for s in suggestions:
        print(f"[{s['type'].upper()}] {s['message']}")