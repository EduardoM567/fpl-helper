# FPL Team Builder Algorithm
# Owner: Eduardo Maticorena

from fpl_api import get_all_players

BUDGET = 100.0
SQUAD_SIZE = 15
MAX_PER_TEAM = 3
POSITION_LIMITS = {
    'GKP': {'min': 2, 'max': 2},
    'DEF': {'min': 5, 'max': 5},
    'MID': {'min': 5, 'max': 5},
    'FWD': {'min': 3, 'max': 3},
}

def score_player(player, strategy='balanced'):
    form = player['form']
    ppg = player['points_per_game']
    ep_next = player['ep_next']
    ict = player['ict_index']
    xg = player['expected_goals']
    xa = player['expected_assists']
    minutes = player['minutes']

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
        if player['position'] in ['DEF', 'GKP']:
            score *= 1.3
    elif strategy == 'budget':
        if player['price'] > 0:
            score = (form * 2 + ppg * 2 + ep_next * 3) / player['price']
        else:
            score = 0
    elif strategy == 'form':
        score = form * 4 + ep_next * 4 + ppg * 1
    else:
        score = ppg + form + ep_next

    # Fixture difficulty modifier
    fixture = player.get('next_fixture', {})
    fdr = fixture.get('difficulty', 3)
    fdr_multiplier = {1: 1.25, 2: 1.15, 3: 1.0, 4: 0.9, 5: 0.8}.get(fdr, 1.0)
    score *= fdr_multiplier

    # Home advantage bonus
    if fixture.get('is_home'):
        score *= 1.05

    return round(score, 2)


def build_team(strategy='balanced', budget=100.0):
    players = get_all_players()

    for p in players:
        p['score'] = score_player(p, strategy)

    players.sort(key=lambda x: x['score'], reverse=True)

    # Budget allocation per position based on strategy
    budget_split = {
        'balanced': {'GKP': 10.0, 'DEF': 27.0, 'MID': 38.0, 'FWD': 25.0},
        'attack':   {'GKP': 9.0,  'DEF': 25.0, 'MID': 34.0, 'FWD': 32.0},
        'defense':  {'GKP': 11.0, 'DEF': 33.0, 'MID': 30.0, 'FWD': 26.0},
        'budget':   {'GKP': 9.0,  'DEF': 24.0, 'MID': 35.0, 'FWD': 22.0},
        'form':     {'GKP': 9.0,  'DEF': 25.0, 'MID': 38.0, 'FWD': 25.0},
    }
    alloc = budget_split.get(strategy, budget_split['balanced'])

    squad = []
    team_counts = {}
    position_counts = {'GKP': 0, 'DEF': 0, 'MID': 0, 'FWD': 0}
    pos_budget = {pos: alloc[pos] for pos in alloc}
    pos_spent = {'GKP': 0.0, 'DEF': 0.0, 'MID': 0.0, 'FWD': 0.0}

    # First pass — pick best players within position budgets
    for player in players:
        if len(squad) >= SQUAD_SIZE:
            break
        pos = player['position']
        team = player['team']
        price = player['price']

        if position_counts[pos] >= POSITION_LIMITS[pos]['max']:
            continue
        if team_counts.get(team, 0) >= MAX_PER_TEAM:
            continue
        if pos_spent[pos] + price > pos_budget[pos] + 0.05:
            continue

        squad.append(player)
        position_counts[pos] += 1
        team_counts[team] = team_counts.get(team, 0) + 1
        pos_spent[pos] += price

    # Calculate remaining budget after first pass
    total_spent = sum(pos_spent.values())
    remaining = budget - total_spent

    # Second pass — fill missing positions using remaining budget
    for player in players:
        if len(squad) >= SQUAD_SIZE:
            break
        if player in squad:
            continue
        pos = player['position']
        team = player['team']
        price = player['price']

        if position_counts[pos] >= POSITION_LIMITS[pos]['max']:
            continue
        if team_counts.get(team, 0) >= MAX_PER_TEAM:
            continue
        if price > remaining + 0.05:
            continue

        squad.append(player)
        position_counts[pos] += 1
        team_counts[team] = team_counts.get(team, 0) + 1
        remaining -= price

    total_cost = round(budget - remaining, 1)

    return {
        'squad': squad,
        'total_cost': total_cost,
        'remaining_budget': round(remaining, 1),
        'strategy': strategy,
        'position_counts': position_counts
    }


def get_captain_suggestion(squad):
    outfield = [p for p in squad if p['position'] != 'GKP']
    sorted_players = sorted(outfield, key=lambda x: x['ep_next'], reverse=True)
    captain = sorted_players[0] if sorted_players else None
    vice_captain = sorted_players[1] if len(sorted_players) > 1 else None
    return captain, vice_captain

def get_best_formation(squad):
    """
    Pick the best starting 11 from the squad using valid FPL formations.
    Valid formations must have 1 GKP, 3-5 DEF, 2-5 MID, 1-3 FWD.
    """
    gkp = [p for p in squad if p['position'] == 'GKP']
    defenders = sorted([p for p in squad if p['position'] == 'DEF'], key=lambda x: x['ep_next'], reverse=True)
    mids = sorted([p for p in squad if p['position'] == 'MID'], key=lambda x: x['ep_next'], reverse=True)
    fwds = sorted([p for p in squad if p['position'] == 'FWD'], key=lambda x: x['ep_next'], reverse=True)

    # Valid formations: DEF-MID-FWD
    formations = [
        (3, 5, 2), (3, 4, 3),
        (4, 5, 1), (4, 4, 2), (4, 3, 3),
        (5, 4, 1), (5, 3, 2), (5, 2, 3),
    ]

    best_starters = None
    best_score = -1

    for d, m, f in formations:
        if len(defenders) < d or len(mids) < m or len(fwds) < f:
            continue

        starters = (
            gkp[:1] +
            defenders[:d] +
            mids[:m] +
            fwds[:f]
        )

        if len(starters) != 11:
            continue

        score = sum(p['ep_next'] for p in starters)
        if score > best_score:
            best_score = score
            best_starters = {
                'GKP': gkp[:1],
                'DEF': defenders[:d],
                'MID': mids[:m],
                'FWD': fwds[:f],
                'formation': f'{d}-{m}-{f}'
            }

    if not best_starters:
        # Fallback to 4-4-2
        best_starters = {
            'GKP': gkp[:1],
            'DEF': defenders[:4],
            'MID': mids[:4],
            'FWD': fwds[:2],
            'formation': '4-4-2'
        }

    # Bench = everyone not in starters
    starter_ids = set(p['id'] for group in best_starters.values() if isinstance(group, list) for p in group)
    bench = [p for p in squad if p['id'] not in starter_ids]

    return best_starters, bench


if __name__ == '__main__':
    result = build_team('balanced')
    print(f"Squad size: {len(result['squad'])}")
    print(f"Positions: {result['position_counts']}")
    print(f"Cost: £{result['total_cost']}m | Bank: £{result['remaining_budget']}m")
    for pos in ['GKP', 'DEF', 'MID', 'FWD']:
        print(f"\n--- {pos} ---")
        for p in result['squad']:
            if p['position'] == pos:
                fix = p.get('next_fixture', {})
                print(f"{p['name']} | {p['team']} | £{p['price']}m | Score: {p['score']} | Next: {fix.get('opponent','?')} FDR:{fix.get('difficulty','?')}")