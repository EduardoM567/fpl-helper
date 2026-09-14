# FPL Helper - Flask Web App
# Owner: Eduardo Maticorena
import os
from flask import Flask, render_template, request, jsonify
from fpl_api import get_all_players, search_player, get_player_status, get_player_photo_url
from team_builder import build_team, get_captain_suggestion

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search')
def search():
    query = request.args.get('q', '')
    if not query or len(query) < 1:
        return jsonify([])
    results = search_player(query)
    for p in results:
        p['status_text'] = get_player_status(p['status'])
        p['photo_url'] = get_player_photo_url(p.get('code'))
    return jsonify(results[:20])

@app.route('/player/<int:player_id>')
def player_detail(player_id):
    from ai_summary import get_player_summary
    players = get_all_players()
    player = next((p for p in players if p['id'] == player_id), None)
    if not player:
        return jsonify({'error': 'Player not found'}), 404
    player['status_text'] = get_player_status(player['status'])
    player['photo_url'] = get_player_photo_url(player.get('code'))
    player['ai_summary'] = get_player_summary(player)
    return jsonify(player)

@app.route('/build-team', methods=['POST'])
def build_team_route():
    from team_builder import get_best_formation
    from ai_summary import get_team_summary
    data = request.get_json()
    strategy = data.get('strategy', 'balanced')
    budget = float(data.get('budget', 100.0))

    if strategy not in ['balanced', 'attack', 'defense', 'budget', 'form']:
        return jsonify({'error': 'Invalid strategy'}), 400

    result = build_team(strategy, budget)
    captain, vice = get_captain_suggestion(result['squad'])

    for p in result['squad']:
        p['status_text'] = get_player_status(p['status'])
        p['photo_url'] = get_player_photo_url(p.get('code'))

    starters, bench = get_best_formation(result['squad'])
    result['captain'] = captain
    result['vice_captain'] = vice
    result['starters'] = starters
    result['bench'] = bench
    result['ai_summary'] = get_team_summary(result['squad'], strategy, captain, vice)

    return jsonify(result)

@app.route('/top-players')
def top_players():
    position = request.args.get('position', 'all')
    sort_by = request.args.get('sort', 'form')
    limit = int(request.args.get('limit', 20))

    players = get_all_players()

    if position != 'all':
        players = [p for p in players if p['position'] == position.upper()]

    valid_sorts = ['form', 'total_points', 'points_per_game',
                   'ep_next', 'ict_index', 'selected_by']
    if sort_by not in valid_sorts:
        sort_by = 'form'

    players.sort(key=lambda x: x[sort_by], reverse=True)

    for p in players[:limit]:
        p['status_text'] = get_player_status(p['status'])
        p['photo_url'] = get_player_photo_url(p.get('code'))

    return jsonify(players[:limit])

@app.route('/deadline')
def get_deadline():
    from fpl_api import get_bootstrap_data
    data = get_bootstrap_data()
    events = data['events']
    next_gw = next((e for e in events if e['is_next']), None)
    current_gw = next((e for e in events if e['is_current']), None)
    target = next_gw or current_gw
    if not target:
        return jsonify({'error': 'No deadline found'})
    return jsonify({
        'gameweek': target['id'],
        'name': target['name'],
        'deadline': target['deadline_time']
    })

@app.route('/transfers')
def transfer_suggestions():
    from ai_summary import get_player_summary
    players = get_all_players()
    
    # Top transfers in
    transfers_in = sorted(players, key=lambda x: x['transfers_in'], reverse=True)[:5]
    # Top differentials - high form low ownership
    differentials = [p for p in players if p['selected_by'] < 10 and p['form'] > 4.0]
    differentials = sorted(differentials, key=lambda x: x['form'], reverse=True)[:5]

    for p in transfers_in + differentials:
        p['status_text'] = get_player_status(p['status'])
        p['photo_url'] = get_player_photo_url(p.get('code'))
        p['ai_summary'] = get_player_summary(p)

    return jsonify({
        'transfers_in': transfers_in,
        'differentials': differentials
    })

@app.route('/my-team/<int:team_id>')
def my_team(team_id):
    from team_lookup import get_user_team, analyze_team
    
    free_transfers = int(request.args.get('free_transfers', 1))
    team_data = get_user_team(team_id)
    if not team_data:
        return jsonify({'error': 'Team not found. Check your Team ID.'}), 404
    
    suggestions = analyze_team(team_data, free_transfers)
    team_data['suggestions'] = suggestions
    
    return jsonify(team_data)

@app.route('/my-team/<int:team_id>/compare')
def compare_team(team_id):
    from team_lookup import get_user_team, compare_to_optimal
    
    team_data = get_user_team(team_id)
    if not team_data:
        return jsonify({'error': 'Team not found'}), 404
    
    comparison = compare_to_optimal(team_data)
    return jsonify(comparison)
    
@app.route('/find-replacement/<int:player_id>')
def find_replacement(player_id):
    players = get_all_players()
    target = next((p for p in players if p['id'] == player_id), None)
    
    if not target:
        return jsonify({'error': 'Player not found'}), 404
    
    # Find same-position players within a reasonable budget range
    budget_flex = 2.0
    candidates = [
        p for p in players 
        if p['position'] == target['position'] 
        and p['id'] != player_id
        and p['price'] <= target['price'] + budget_flex
        and p['status'] in ['a', 'd']
    ]
    
    # Score by form + fixture difficulty
    for p in candidates:
        fix = p.get('next_fixture', {})
        fdr = fix.get('difficulty', 3)
        fdr_bonus = {1: 1.3, 2: 1.15, 3: 1.0, 4: 0.85, 5: 0.7}.get(fdr, 1.0)
        p['replacement_score'] = (p['form'] * 2 + p['ep_next'] * 3) * fdr_bonus
    
    candidates.sort(key=lambda x: x['replacement_score'], reverse=True)
    
    for p in candidates[:5]:
        p['status_text'] = get_player_status(p['status'])
        p['photo_url'] = get_player_photo_url(p.get('code'))
    
    return jsonify({
        'target': target,
        'alternatives': candidates[:5]
    })

@app.route('/my-team/<int:team_id>/optimize')
def optimize_team(team_id):
    from team_lookup import get_user_team, get_optimized_lineup
    
    team_data = get_user_team(team_id)
    if not team_data:
        return jsonify({'error': 'Team not found'}), 404
    
    optimized = get_optimized_lineup(team_data)
    return jsonify(optimized)

@app.route('/my-team/<int:team_id>/suggest-transfer')
def suggest_transfer_route(team_id):
    from team_lookup import get_user_team, suggest_transfer
    
    team_data = get_user_team(team_id)
    if not team_data:
        return jsonify({'error': 'Team not found'}), 404
    
    transfer = suggest_transfer(team_data)
    if not transfer:
        return jsonify({'message': 'Your current lineup is already optimal — no beneficial transfer found!'})
    
    return jsonify(transfer)

@app.route('/my-team/<int:team_id>/chips')
def chips_status(team_id):
    from team_lookup import get_user_team, get_chip_status, suggest_chip_timing
    
    chip_status = get_chip_status(team_id)
    if chip_status is None:
        return jsonify({'error': 'Team not found'}), 404
    
    team_data = get_user_team(team_id)
    chip_suggestions = suggest_chip_timing(team_data, chip_status)
    
    return jsonify({
        'chips': chip_status,
        'suggestions': chip_suggestions
    })

@app.route('/my-team/<int:team_id>/preview-transfer')
def preview_transfer(team_id):
    from team_lookup import get_user_team, suggest_transfer, get_optimized_lineup
    
    team_data = get_user_team(team_id)
    if not team_data:
        return jsonify({'error': 'Team not found'}), 404
    
    transfer = suggest_transfer(team_data)
    if not transfer:
        return jsonify({'message': 'No transfer needed — already optimal'})
    
    # Build the hypothetical new squad
    new_squad = [p for p in team_data['squad'] if p['id'] != transfer['transfer_out']['id']]
    incoming = dict(transfer['transfer_in'])
    incoming['is_starting'] = True
    incoming['is_captain'] = False
    incoming['is_vice_captain'] = False
    new_squad.append(incoming)
    
    hypothetical_team = dict(team_data)
    hypothetical_team['squad'] = new_squad
    
    optimized = get_optimized_lineup(hypothetical_team)
    
    return jsonify({
        'transfer': transfer,
        'optimized_lineup': optimized
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=False, host='0.0.0.0', port=port)