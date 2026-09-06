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
    """Generate specific, actionable suggestions for the user's team"""
    squad = team_data['squad']
    starting = [p for p in squad if p['is_starting']]
    bench = [p for p in squad if not p['is_starting']]

    suggestions = []

    def calc_priority(p):
        """Lower score = should be replaced first"""
        fix = p.get('next_fixture', {})
        fdr = fix.get('difficulty', 3)
        fdr_penalty = {1: 0, 2: 5, 3: 10, 4: 20, 5: 30}.get(fdr, 10)
        status_penalty = {'i': 100, 's': 100, 'n': 100, 'd': 40}.get(p['status'], 0)
        return p['form'] * 3 + p['ep_next'] * 2 - fdr_penalty - status_penalty

    # Score every starter and bench player
    for p in starting + bench:
        p['_priority'] = calc_priority(p)

    # 1. Injured/unavailable starters — find best same-position replacement (bench first, then any squad player)
    for p in starting:
        if p['status'] in ['i', 's', 'n']:
            same_pos_bench = [b for b in bench if b['position'] == p['position']]
            same_pos_bench.sort(key=lambda x: x['_priority'], reverse=True)

            if same_pos_bench:
                best = same_pos_bench[0]
                suggestions.append({
                    'type': 'urgent',
                    'player': p['name'],
                    'message': f"{p['name']} is {p['status_text']} — start {best['name']} from your bench instead."
                })
            else:
                suggestions.append({
                    'type': 'urgent',
                    'player': p['name'],
                    'message': f"{p['name']} is {p['status_text']} — you have no bench cover, consider a transfer before the deadline."
                })

    # 2. Doubtful starters
    for p in starting:
        if p['status'] == 'd':
            suggestions.append({
                'type': 'warning',
                'player': p['name'],
                'message': f"{p['name']} is doubtful for GW{team_data['gameweek']} — check the team news before the deadline closes."
            })

    # 3. Weak starter + hard fixture, paired with a stronger bench option at same position
    for p in starting:
        if p['status'] in ['i', 's', 'n', 'd']:
            continue  # already covered above

        fix = p.get('next_fixture', {})
        if fix.get('difficulty', 3) >= 4:
            same_pos_bench = [b for b in bench if b['position'] == p['position'] and b['status'] == 'a']
            same_pos_bench.sort(key=lambda x: x['_priority'], reverse=True)

            if same_pos_bench and same_pos_bench[0]['_priority'] > p['_priority']:
                best = same_pos_bench[0]
                suggestions.append({
                    'type': 'info',
                    'player': p['name'],
                    'message': f"{p['name']} faces {fix.get('opponent','?')} (FDR {fix['difficulty']}) — bench them for {best['name']} who has an easier fixture."
                })
            else:
                suggestions.append({
                    'type': 'info',
                    'player': p['name'],
                    'message': f"{p['name']} faces a tough fixture vs {fix.get('opponent','?')} (FDR {fix['difficulty']}) — may still be worth starting if no better bench option."
                })

    # 4. In-form bench players who should replace a weaker starter at the same position
    for b in bench:
        if b['status'] != 'a' or b['form'] < 6.0:
            continue

        same_pos_starters = [s for s in starting if s['position'] == b['position']]
        same_pos_starters.sort(key=lambda x: x['_priority'])

        if same_pos_starters and b['_priority'] > same_pos_starters[0]['_priority']:
            weakest = same_pos_starters[0]
            suggestions.append({
                'type': 'tip',
                'player': b['name'],
                'message': f"{b['name']} is in great form ({b['form']}) — start them over {weakest['name']} this week."
            })

    return suggestions

def compare_to_optimal(team_data):
    """Compare user's actual team to what the algorithm would build"""
    from team_builder import build_team
    
    squad = team_data['squad']
    total_value = sum(p['price'] for p in squad)
    
    # Build an optimal team with similar budget using balanced strategy
    optimal = build_team('balanced', budget=total_value + team_data['bank'])
    
    user_ids = set(p['id'] for p in squad)
    optimal_ids = set(p['id'] for p in optimal['squad'])
    
    overlap = user_ids & optimal_ids
    missing_from_user = [p for p in optimal['squad'] if p['id'] not in user_ids]
    
    # Sort missing players by score to show best upgrades first
    missing_from_user.sort(key=lambda x: x.get('score', 0), reverse=True)
    
    return {
        'overlap_count': len(overlap),
        'total_optimal': len(optimal['squad']),
        'match_percentage': round(len(overlap) / len(optimal['squad']) * 100, 1),
        'suggested_additions': missing_from_user[:5]
    }


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