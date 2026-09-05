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

    # Boost genuinely elite players (high ownership + high total points = proven quality)
    if player.get('total_points', 0) >= 12 and player.get('selected_by', 0) > 20:
        score *= 1.2

    return round(score, 2)


def build_team(strategy='balanced', budget=100.0):
    players = get_all_players()

    for p in players:
        p['score'] = score_player(p, strategy)

    players.sort(key=lambda x: x['score'], reverse=True)

    # Force include top premium forward for attack strategy
    if strategy == 'attack':
        premium_fwd = [p for p in players if p['position'] == 'FWD' and p['price'] >= 12.0]
        premium_fwd.sort(key=lambda x: x['score'], reverse=True)
        if premium_fwd:
            top_fwd = premium_fwd[0]
            players.remove(top_fwd)
            players.insert(0, top_fwd)

    squad = []
    team_counts = {}
    position_counts = {'GKP': 0, 'DEF': 0, 'MID': 0, 'FWD': 0}
    spent = 0.0

    def can_add(player):
        pos = player['position']
        team = player['team']
        if position_counts[pos] >= POSITION_LIMITS[pos]['max']:
            return False
        if team_counts.get(team, 0) >= MAX_PER_TEAM:
            return False
        return True

    def add_player(player):
        nonlocal spent
        pos = player['position']
        team = player['team']
        squad.append(player)
        position_counts[pos] += 1
        team_counts[team] = team_counts.get(team, 0) + 1
        spent += player['price']

    # STEP 1: Guarantee a valid 15-player squad using cheapest eligible players first
    # This ensures we always hit exactly 2 GKP, 5 DEF, 5 MID, 3 FWD
    cheapest_first = sorted(players, key=lambda x: x['price'])
    for player in cheapest_first:
        if len(squad) >= SQUAD_SIZE:
            break
        if can_add(player):
            add_player(player)

    # STEP 2: Upgrade — try to swap in higher-scoring players within same position
    # as long as budget allows, going from best score down
    remaining = budget - spent
    best_first = sorted(players, key=lambda x: x['score'], reverse=True)

    for candidate in best_first:
        if candidate in squad:
            continue
        pos = candidate['position']

        # Find the weakest (lowest score) player in squad at this position to replace
        same_pos_in_squad = [p for p in squad if p['position'] == pos]
        if not same_pos_in_squad:
            continue
        weakest = min(same_pos_in_squad, key=lambda x: x['score'])

        if candidate['score'] <= weakest['score']:
            continue

        price_diff = candidate['price'] - weakest['price']
        if price_diff > remaining + 0.05:
            continue

        # Check team limit allows the swap
        cand_team = candidate['team']
        current_team_count = team_counts.get(cand_team, 0)
        if weakest['team'] == cand_team:
            pass  # replacing within same team, count unaffected
        elif current_team_count >= MAX_PER_TEAM:
            continue

        # Perform swap
        squad.remove(weakest)
        squad.append(candidate)
        team_counts[weakest['team']] -= 1
        team_counts[cand_team] = team_counts.get(cand_team, 0) + 1
        remaining -= price_diff
        spent += price_diff

    total_cost = round(spent, 1)
    remaining = round(budget - spent, 1)

    return {
        'squad': squad,
        'total_cost': total_cost,
        'remaining_budget': remaining,
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