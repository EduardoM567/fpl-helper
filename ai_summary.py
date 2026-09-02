# AI Player Summary
# Rule-based FPL recommendations (Claude API ready when credits available)
# Owner: Eduardo Maticorena

def get_player_summary(player):
    """Generate smart rule-based FPL recommendation"""
    fix = player.get('next_fixture', {})
    fdr = fix.get('difficulty', 3)
    form = player['form']
    ep_next = player['ep_next']
    status = player.get('status', 'a')
    price = player['price']
    transfers_in = player.get('transfers_in', 0)
    transfers_out = player.get('transfers_out', 0)
    position = player['position']
    ownership = player['selected_by']

    # Determine verdict
    if status in ['i', 'n', 's']:
        verdict = 'AVOID'
        reason = f"Currently {player.get('status_text', 'unavailable')} — not worth the risk this gameweek."
    elif form >= 7.0 and fdr <= 2:
        verdict = 'BUY'
        reason = f"Excellent form ({form}) with a very easy fixture ahead. Strong captaincy candidate."
    elif form >= 6.0 and fdr <= 3:
        verdict = 'BUY'
        reason = f"Good form ({form}) and a manageable fixture. Worth bringing in if you have the budget."
    elif form >= 5.0 and fdr <= 3:
        verdict = 'HOLD'
        reason = f"Solid performer with a decent fixture. Keep if you own them, not urgent to buy."
    elif fdr >= 5:
        verdict = 'AVOID'
        reason = f"Very tough fixture this week (FDR {fdr}/5). Consider benching or transferring out."
    elif fdr >= 4 and form < 4.0:
        verdict = 'AVOID'
        reason = f"Poor form ({form}) combined with a hard fixture (FDR {fdr}/5). Look elsewhere."
    elif form < 3.0:
        verdict = 'AVOID'
        reason = f"Out of form ({form} average). Not recommended until they show improvement."
    else:
        verdict = 'HOLD'
        reason = f"Average performer this week. Fine to hold but not a priority transfer target."

    # Add transfer trend insight
    if transfers_in > 50000:
        trend = f" Highly popular this week with {transfers_in:,} transfers in."
    elif transfers_out > 50000:
        trend = f" Many managers are selling — {transfers_out:,} transfers out this week."
    else:
        trend = ""

    # Add fixture context
    if fix.get('opponent'):
        fixture_context = f" Faces {fix['opponent']} {'at home' if fix.get('is_home') else 'away'} in GW{fix.get('gameweek', '?')}."
    else:
        fixture_context = ""

    return f"{verdict} — {reason}{fixture_context}{trend}"


def get_team_summary(squad, strategy, captain, vice_captain):
    """Generate smart rule-based team summary"""
    fix = captain.get('next_fixture', {}) if captain else {}
    home_away = 'home' if fix.get('is_home') else 'away'
    cap_fixture = f"{fix.get('opponent', '?')} ({home_away})" if fix.get('opponent') else "unknown fixture"

    total_price = sum(p['price'] for p in squad)
    avg_form = round(sum(p['form'] for p in squad) / len(squad), 1) if squad else 0
    easy_fixtures = sum(1 for p in squad if p.get('next_fixture', {}).get('difficulty', 3) <= 2)
    hard_fixtures = sum(1 for p in squad if p.get('next_fixture', {}).get('difficulty', 3) >= 4)

    strategy_desc = {
        'balanced': 'balanced approach with quality across all positions',
        'attack': 'attack-heavy strategy focusing on premium forwards and midfielders',
        'defense': 'defensive strategy targeting clean sheet points',
        'budget': 'budget-friendly approach maximizing value for money',
        'form': 'form-based strategy targeting players in the hottest streak'
    }.get(strategy, strategy)

    summary = f"This squad uses a {strategy_desc}. "
    summary += f"Average form rating of {avg_form} across the squad"

    if easy_fixtures > 5:
        summary += f" with {easy_fixtures} players facing easy fixtures this week — great for points potential."
    elif hard_fixtures > 5:
        summary += f" but {hard_fixtures} players face tough fixtures — expect a challenging gameweek."
    else:
        summary += " with a mixed set of fixtures."

    if captain:
        summary += f" {captain['name']} is the captain pick facing {cap_fixture} — "
        if fix.get('difficulty', 3) <= 2:
            summary += "an excellent choice with an easy home fixture."
        elif fix.get('difficulty', 3) >= 4:
            summary += "a risky choice given the tough fixture, consider alternatives."
        else:
            summary += "a solid choice with decent fixture difficulty."

    return summary


if __name__ == '__main__':
    from fpl_api import get_all_players, get_player_status
    players = get_all_players()
    test_player = next(p for p in players if p['name'] == 'Palmer')
    test_player['status_text'] = get_player_status(test_player['status'])
    print("Testing summary for Palmer...")
    summary = get_player_summary(test_player)
    print(summary)