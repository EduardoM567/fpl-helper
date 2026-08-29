# FPL Team Builder Algorithm
# Builds optimal FPL teams based on different strategies

from fpl_api import get_all_players

# FPL Rules
BUDGET = 100.0  # £100m total budget
SQUAD_SIZE = 15
MAX_PER_TEAM = 3  # Max 3 players from same club
POSITION_LIMITS = {
    'GKP': {'min': 2, 'max': 2},
    'DEF': {'min': 5, 'max': 5},
    'MID': {'min': 5, 'max': 5},
    'FWD': {'min': 3, 'max': 3},
}
STARTING_11 = {
    'GKP': 1,
    'DEF': {'min': 3, 'max': 5},
    'MID': {'min': 2, 'max': 5},
    'FWD': {'min': 1, 'max': 3},
}

def score_player(player, strategy='balanced'):
    """Score a player based on the chosen strategy"""
    
    # Base score components
    form = player['form']
    ppg = player['points_per_game']
    ep_next = player['ep_next']
    ict = player['ict_index']
    xg = player['expected_goals']
    xa = player['expected_assists']
    minutes = player['minutes']
    price = player['price']

    # Skip players with no minutes
    if minutes == 0:
        return 0

    # Skip injured/unavailable players
    if player['status'] not in ['a', 'd']:
        return 0

    if strategy == 'balanced':
        score = (
            form * 2 +
            ppg * 2 +
            ep_next * 3 +
            ict * 0.5 +
            (xg + xa) * 2
        )

    elif strategy == 'attack':
        score = (
            form * 2 +
            ppg * 1.5 +
            ep_next * 3 +
            xg * 4 +
            xa * 3 +
            ict * 0.5
        )
        # Boost forwards and attacking mids
        if player['position'] in ['FWD', 'MID']:
            score *= 1.3

    elif strategy == 'defense':
        score = (
            form * 2 +
            ppg * 2 +
            ep_next * 3 +
            player['clean_sheets'] * 3 +
            player['bonus'] * 2
        )
        # Boost defenders and goalkeepers
        if player['position'] in ['DEF', 'GKP']:
            score *= 1.3

    elif strategy == 'budget':
        # Best value for money
        if price > 0:
            score = (
                form * 2 +
                ppg * 2 +
                ep_next * 3
            ) / price
        else:
            score = 0

    elif strategy == 'form':
        score = (
            form * 4 +
            ep_next * 4 +
            ppg * 1
        )

    else:
        score = ppg + form + ep_next

    return round(score, 2)

def build_team(strategy='balanced', budget=100.0):
    """Build an optimal FPL squad based on strategy"""
    
    players = get_all_players()
    
    # Score all players
    for p in players:
        p['score'] = score_player(p, strategy)
    
    # Sort by score descending
    players.sort(key=lambda x: x['score'], reverse=True)
    
    squad = []
    team_counts = {}
    position_counts = {'GKP': 0, 'DEF': 0, 'MID': 0, 'FWD': 0}
    remaining_budget = budget
    
    for player in players:
        pos = player['position']
        team = player['team']
        price = player['price']
        
        # Check position limit
        if position_counts[pos] >= POSITION_LIMITS[pos]['max']:
            continue
        
        # Check team limit
        if team_counts.get(team, 0) >= MAX_PER_TEAM:
            continue
        
        # Check budget
        if price > remaining_budget:
            continue
        
        # Check squad size
        if len(squad) >= SQUAD_SIZE:
            break
        
        # Add player to squad
        squad.append(player)
        position_counts[pos] += 1
        team_counts[team] = team_counts.get(team, 0) + 1
        remaining_budget -= price
    
    return {
        'squad': squad,
        'total_cost': round(budget - remaining_budget, 1),
        'remaining_budget': round(remaining_budget, 1),
        'strategy': strategy,
        'position_counts': position_counts
    }

def get_captain_suggestion(squad):
    """Suggest captain and vice captain from squad"""
    outfield = [p for p in squad if p['position'] != 'GKP']
    sorted_players = sorted(outfield, key=lambda x: x['ep_next'], reverse=True)
    
    captain = sorted_players[0] if len(sorted_players) > 0 else None
    vice_captain = sorted_players[1] if len(sorted_players) > 1 else None
    
    return captain, vice_captain

if __name__ == '__main__':
    print("Building balanced team...")
    result = build_team('balanced')
    
    print(f"\nStrategy: {result['strategy'].upper()}")
    print(f"Total cost: £{result['total_cost']}m")
    print(f"Remaining budget: £{result['remaining_budget']}m")
    print(f"Squad size: {len(result['squad'])}")
    print()
    
    for pos in ['GKP', 'DEF', 'MID', 'FWD']:
        print(f"\n--- {pos} ---")
        for p in result['squad']:
            if p['position'] == pos:
                print(f"{p['name']} | {p['team']} | £{p['price']}m | Score: {p['score']} | Form: {p['form']}")
    
    captain, vice = get_captain_suggestion(result['squad'])
    print(f"\nCaptain: {captain['name']} ({captain['team']}) - xP next: {captain['ep_next']}")
    print(f"Vice Captain: {vice['name']} ({vice['team']}) - xP next: {vice['ep_next']}")