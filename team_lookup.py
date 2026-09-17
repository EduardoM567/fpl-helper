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


def analyze_team(team_data, free_transfers=1):
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

    transfers_used = 0

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
                transfers_used += 1
                cost_note = "" if transfers_used <= free_transfers else f" (costs -4 points, you have {free_transfers} free transfer{'s' if free_transfers != 1 else ''})"
                suggestions.append({
                    'type': 'urgent',
                    'player': p['name'],
                    'message': f"{p['name']} is {p['status_text']} — you have no bench cover, consider a transfer before the deadline{cost_note}."
                })

    # 2. Doubtful starters — give specific play/bench guidance based on actual percentage
    for p in starting:
        if p['status'] == 'd':
            chance = p.get('chance_of_playing_next')
            
            if chance is not None:
                same_pos_bench = [b for b in bench if b['position'] == p['position'] and b['status'] == 'a']
                same_pos_bench.sort(key=lambda x: x['_priority'], reverse=True)
                best_alt = same_pos_bench[0] if same_pos_bench else None
                
                if chance <= 25:
                    if best_alt:
                        suggestions.append({
                            'type': 'urgent',
                            'player': p['name'],
                            'message': f"{p['name']} has only a {chance}% chance of playing — bench them for {best_alt['name']} to be safe."
                        })
                    else:
                        suggestions.append({
                            'type': 'urgent',
                            'player': p['name'],
                            'message': f"{p['name']} has only a {chance}% chance of playing and you have no safe bench alternative — consider a transfer."
                        })
                elif chance <= 50:
                    if best_alt:
                        suggestions.append({
                            'type': 'warning',
                            'player': p['name'],
                            'message': f"{p['name']} is a {chance}% chance to play — risky. {best_alt['name']} on your bench is a safer starting option this week."
                        })
                    else:
                        suggestions.append({
                            'type': 'warning',
                            'player': p['name'],
                            'message': f"{p['name']} is only a {chance}% chance to play — risky, but you have no better bench option. Check team news before the deadline."
                        })
                elif chance <= 75:
                    suggestions.append({
                        'type': 'warning',
                        'player': p['name'],
                        'message': f"{p['name']} is a {chance}% chance to play — should be fine to start, but double check team news before the deadline."
                    })
                else:
                    suggestions.append({
                        'type': 'info',
                        'player': p['name'],
                        'message': f"{p['name']} is a {chance}% chance to play — likely fine to start, minor risk only."
                    })
            else:
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

def get_optimized_lineup(team_data):
    """Find the best possible starting 11 from the user's existing squad"""
    from team_builder import get_best_formation
    
    squad = team_data['squad']
    starters, bench = get_best_formation(squad)
    
    # Determine best captain from the optimized starters
    all_starters = []
    for pos_group in ['GKP', 'DEF', 'MID', 'FWD']:
        all_starters.extend(starters.get(pos_group, []))
    
    outfield = [p for p in all_starters if p['position'] != 'GKP']
    outfield.sort(key=lambda x: x['ep_next'], reverse=True)
    
    captain = outfield[0] if outfield else None
    vice_captain = outfield[1] if len(outfield) > 1 else None
    
    # Compare to their current starting 11
    current_starters = [p for p in squad if p['is_starting']]
    current_ids = set(p['id'] for p in current_starters)
    optimized_ids = set(p['id'] for p in all_starters)
    
    changes_needed = optimized_ids != current_ids
    
    return {
        'starters': starters,
        'bench': bench,
        'captain': captain,
        'vice_captain': vice_captain,
        'formation': starters.get('formation', '4-4-2'),
        'changes_needed': changes_needed
    }

def suggest_transfer(team_data, max_transfers=1, free_transfers=1):
    """
    Suggest the best transfer(s), supporting multiple transfers with point cost awareness.
    Each transfer beyond free_transfers costs -4 points.
    """
    from fpl_api import get_all_players
    from team_builder import get_best_formation
    
    squad = [dict(p) for p in team_data['squad']]  # work on copies
    bank = team_data['bank']
    
    all_players = get_all_players()
    
    def calc_score(p):
        fix = p.get('next_fixture', {})
        fdr = fix.get('difficulty', 3)
        fdr_bonus = {1: 1.3, 2: 1.15, 3: 1.0, 4: 0.85, 5: 0.7}.get(fdr, 1.0)
        return (p['form'] * 2 + p['ep_next'] * 3) * fdr_bonus
    
    transfers = []
    remaining_bank = bank
    working_squad = list(squad)
    
    for i in range(max_transfers):
        for p in working_squad:
            p['_score'] = calc_score(p)
        
        squad_ids = set(p['id'] for p in working_squad)
        starters_dict, _ = get_best_formation(working_squad)
        starting = []
        for pos in ['GKP', 'DEF', 'MID', 'FWD']:
            starting.extend(starters_dict.get(pos, []))
        
        already_swapped_out = set(t['transfer_out']['id'] for t in transfers)
        candidates_to_replace = [p for p in starting if p['id'] not in already_swapped_out]
        
        if not candidates_to_replace:
            break
        
        weakest = min(candidates_to_replace, key=lambda x: x['_score'])
        max_price = weakest['price'] + remaining_bank
        
        candidates = [
            p for p in all_players
            if p['position'] == weakest['position']
            and p['id'] not in squad_ids
            and p['price'] <= max_price
            and p['status'] == 'a'
        ]
        for p in candidates:
            p['_score'] = calc_score(p)
        candidates.sort(key=lambda x: x['_score'], reverse=True)
        
        if not candidates or candidates[0]['_score'] <= weakest['_score']:
            break
        
        best = dict(candidates[0])
        price_diff = round(best['price'] - weakest['price'], 1)
        
        transfer_number = i + 1
        cost = 0 if transfer_number <= free_transfers else 4
        
        transfers.append({
            'transfer_out': weakest,
            'transfer_in': best,
            'price_diff': price_diff,
            'point_cost': cost
        })
        
        # Apply this transfer to the working squad for the next iteration
        working_squad = [p for p in working_squad if p['id'] != weakest['id']]
        best['is_starting'] = True
        best['is_captain'] = False
        best['is_vice_captain'] = False
        working_squad.append(best)
        remaining_bank -= price_diff
    
    if not transfers:
        return None
    
    total_point_cost = sum(t['point_cost'] for t in transfers)
    
    return {
        'transfers': transfers,
        'total_point_cost': total_point_cost,
        'new_bank': round(remaining_bank, 1),
        'free_transfers_used': min(len(transfers), free_transfers),
        'paid_transfers': max(0, len(transfers) - free_transfers)
    }

def find_optimal_transfer_count(team_data, free_transfers=1, max_to_try=3):
    """
    Try different numbers of transfers and recommend the one with the best 
    net benefit (score improvement minus point cost).
    """
    results = []
    
    for n in range(0, max_to_try + 1):
        if n == 0:
            results.append({
                'num_transfers': 0,
                'net_gain': 0,
                'total_point_cost': 0,
                'transfers': []
            })
            continue
        
        suggestion = suggest_transfer(team_data, max_transfers=n, free_transfers=free_transfers)
        if not suggestion or len(suggestion['transfers']) < n:
            break
        
        # Estimate gain: sum of (incoming ep_next - outgoing ep_next) across all transfers
        gain = sum(
            t['transfer_in']['ep_next'] - t['transfer_out']['ep_next']
            for t in suggestion['transfers']
        )
        net_gain = round(gain - suggestion['total_point_cost'], 2)
        
        results.append({
            'num_transfers': n,
            'net_gain': net_gain,
            'total_point_cost': suggestion['total_point_cost'],
            'transfers': suggestion['transfers'],
            'new_bank': suggestion['new_bank']
        })
    
    # Pick the option with the highest net gain
    best = max(results, key=lambda x: x['net_gain'])
    
    return {
        'recommended': best,
        'all_options': results
    }

def get_chip_status(team_id):
    """Check which chips a user has used and which are still available"""
    import requests
    
    response = requests.get(f'https://fantasy.premierleague.com/api/entry/{team_id}/history/')
    if response.status_code != 200:
        return None
    
    data = response.json()
    used_chips = data.get('chips', [])
    
    chip_names = {
        'wildcard': 'Wildcard',
        'freehit': 'Free Hit',
        'bboost': 'Bench Boost',
        '3xc': 'Triple Captain'
    }
    
    # Determine current half of season (chips reset after GW19)
    current_gw = get_current_gameweek()
    half = 1 if current_gw <= 19 else 2
    
    used_this_half = {}
    for chip in used_chips:
        chip_gw = chip['event']
        chip_half = 1 if chip_gw <= 19 else 2
        if chip_half == half:
            used_this_half[chip['name']] = chip['event']
    
    status = []
    for chip_key, chip_label in chip_names.items():
        status.append({
            'key': chip_key,
            'label': chip_label,
            'used': chip_key in used_this_half,
            'used_gw': used_this_half.get(chip_key)
        })
    
    return status


def suggest_chip_timing(team_data, chip_status):
    """Suggest whether now is a good time to use available chips"""
    suggestions = []
    squad = team_data['squad']
    starting = [p for p in squad if p['is_starting']]
    
    for chip in chip_status:
        if chip['used']:
            continue
        
        if chip['key'] == '3xc':
            # Check if captain has a great fixture
            outfield = [p for p in starting if p['position'] != 'GKP']
            if outfield:
                best = max(outfield, key=lambda x: x['ep_next'])
                fix = best.get('next_fixture', {})
                if fix.get('difficulty', 3) <= 2 and best['form'] >= 6.0:
                    suggestions.append({
                        'chip': 'Triple Captain',
                        'recommendation': f"Good week to consider — {best['name']} has an easy fixture (FDR {fix['difficulty']}) and strong form ({best['form']})."
                    })
        
        elif chip['key'] == 'bboost':
            bench = [p for p in squad if not p['is_starting']]
            bench_score = sum(p['form'] for p in bench)
            if bench_score >= 15:
                suggestions.append({
                    'chip': 'Bench Boost',
                    'recommendation': f"Your bench has strong combined form ({round(bench_score,1)}) — could be worth using Bench Boost this week."
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