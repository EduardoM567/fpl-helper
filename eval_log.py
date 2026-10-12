#!/usr/bin/env python3
# FPL Helper - recommendation tracker
# Owner: Eduardo Maticorena
#
# Logs what the tool recommends BEFORE a gameweek deadline, then scores those
# recommendations against real FPL points once the gameweek is finished.
#
# Run from the fpl-helper folder with the venv active:
#   python3 eval_log.py snapshot 5292186 [more Team IDs] [--free 1]
#   python3 eval_log.py score
#
# Simplifications: auto-subs, chips and bench points are ignored, and the squad
# used is the one FPL reports for the latest locked gameweek.

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

import requests

FPL = 'https://fantasy.premierleague.com/api'
DB_PATH = 'data/eval_log.db'  # data/ is already in .gitignore
FORMATIONS = [(3, 4, 3), (3, 5, 2), (4, 3, 3), (4, 4, 2),
              (4, 5, 1), (5, 2, 3), (5, 3, 2), (5, 4, 1)]

def db():
    os.makedirs('data', exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        'CREATE TABLE IF NOT EXISTS snapshots ('
        'gw INTEGER, team_id INTEGER, created_at TEXT, payload TEXT, '
        'PRIMARY KEY (gw, team_id))'
    )
    return con

def xp(p):
    """Expected points, zeroed for unavailable players and scaled by playing chance."""
    if p['status'] in ('i', 's', 'n'):
        return 0.0
    chance = p.get('chance_of_playing_next')
    return p['ep_next'] * (chance / 100 if chance is not None else 1)

def baseline_transfer(team, all_players):
    """Simple rule to beat: swap the weakest starter (by expected points) for the
    highest expected-points available player at that position within budget."""
    squad_ids = {p['id'] for p in team['squad']}
    starters = [p for p in team['squad'] if p['is_starting']]
    if not starters:
        return None
    weakest = min(starters, key=xp)
    pool = [
        p for p in all_players
        if p['position'] == weakest['position']
        and p['id'] not in squad_ids
        and p['status'] == 'a'
        and p['price'] <= weakest['price'] + team['bank']
    ]
    if not pool:
        return None
    best = max(pool, key=lambda p: p['ep_next'])
    if best['ep_next'] <= xp(weakest):
        return None
    return {'out': weakest['id'], 'in': best['id'],
            'pred_gain': round(best['ep_next'] - xp(weakest), 2)}

def snapshot(team_ids, free_transfers):
    # Imported here so `score` works without the rest of the app
    from fpl_api import get_bootstrap_data, get_all_players
    from team_lookup import get_user_team, get_optimized_lineup, find_optimal_transfer_count

    events = get_bootstrap_data()['events']
    nxt = next((e for e in events if e['is_next']), None)
    if not nxt:
        print('No upcoming gameweek found.')
        return
    gw = nxt['id']
    all_players = get_all_players()
    by_id = {p['id']: p for p in all_players}
    con = db()

    for tid in team_ids:
        team = get_user_team(tid)
        if not team:
            print('Team ' + str(tid) + ': not found, skipping')
            continue

        opt = get_optimized_lineup(team)
        tool_starters = [p['id'] for pos in ('GKP', 'DEF', 'MID', 'FWD')
                         for p in opt['starters'].get(pos, [])]
        rec = find_optimal_transfer_count(team, free_transfers)['recommended']
        base = baseline_transfer(team, all_players)

        tool_transfers = [
            {'out': t['transfer_out']['id'], 'in': t['transfer_in']['id'], 'cost': t['point_cost']}
            for t in rec['transfers']
        ]
        ids = {p['id'] for p in team['squad']}
        for t in tool_transfers:
            ids |= {t['out'], t['in']}
        if base:
            ids |= {base['out'], base['in']}

        payload = {
            'names': {str(i): by_id[i]['name'] for i in ids if i in by_id},
            'squad': [{'id': p['id'], 'pos': p['position']} for p in team['squad']],
            'tool_starters': tool_starters,
            'tool_captain': opt['captain']['id'] if opt.get('captain') else None,
            'unchanged_starters': [p['id'] for p in team['squad'] if p['is_starting']],
            'unchanged_captain': next((p['id'] for p in team['squad'] if p['is_captain']), None),
            'tool_transfers': tool_transfers,
            'tool_transfer_pred': rec['net_gain'],
            'baseline_transfer': base,
        }
        con.execute(
            'INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?)',
            (gw, tid, datetime.now(timezone.utc).isoformat(), json.dumps(payload))
        )
        con.commit()

        cap_name = payload['names'].get(str(payload['tool_captain']), '?')
        print('Logged GW' + str(gw) + ' for team ' + str(tid) + ': captain ' + cap_name +
              ', ' + str(len(tool_transfers)) + ' transfer(s) suggested')

def live_points(gw):
    r = requests.get(FPL + '/event/' + str(gw) + '/live/', timeout=20)
    r.raise_for_status()
    return {e['id']: e['stats']['total_points'] for e in r.json()['elements']}

def lineup_points(starters, captain, pts):
    """Sum of the 11 starters, with the captain counted a second time."""
    return sum(pts.get(i, 0) for i in starters) + pts.get(captain, 0)

def hindsight_best(squad, pts):
    """Ceiling: the best formation and captain you could have picked from these 15."""
    by_pos = {
        pos: sorted([p['id'] for p in squad if p['pos'] == pos],
                    key=lambda i: pts.get(i, 0), reverse=True)
        for pos in ('GKP', 'DEF', 'MID', 'FWD')
    }
    best = 0
    for d, m, f in FORMATIONS:
        if not by_pos['GKP'] or len(by_pos['DEF']) < d or len(by_pos['MID']) < m or len(by_pos['FWD']) < f:
            continue
        ids = by_pos['GKP'][:1] + by_pos['DEF'][:d] + by_pos['MID'][:m] + by_pos['FWD'][:f]
        total = sum(pts.get(i, 0) for i in ids) + max(pts.get(i, 0) for i in ids)
        best = max(best, total)
    return best

def score():
    r = requests.get(FPL + '/bootstrap-static/', timeout=20)
    r.raise_for_status()
    events = {e['id']: e for e in r.json()['events']}

    con = db()
    rows = con.execute('SELECT gw, team_id, payload FROM snapshots ORDER BY gw, team_id').fetchall()
    if not rows:
        print('Nothing logged yet - run a snapshot first.')
        return []

    live_cache = {}
    pending = set()
    results = []

    for gw, tid, raw in rows:
        ev = events.get(gw)
        # data_checked means FPL has finalised bonus points for the gameweek
        if not ev or not ev.get('data_checked'):
            pending.add(gw)
            continue
        if gw not in live_cache:
            live_cache[gw] = live_points(gw)
        pts = live_cache[gw]
        p = json.loads(raw)

        def nm(i):
            return p['names'].get(str(i), str(i))

        tool = lineup_points(p['tool_starters'], p['tool_captain'], pts)
        same = lineup_points(p['unchanged_starters'], p['unchanged_captain'], pts)
        best = hindsight_best(p['squad'], pts)
        cap_tool = pts.get(p['tool_captain'], 0)
        cap_you = pts.get(p['unchanged_captain'], 0)
        tr_tool = (sum(pts.get(t['in'], 0) - pts.get(t['out'], 0) for t in p['tool_transfers'])
                   - sum(t['cost'] for t in p['tool_transfers']))
        base = p['baseline_transfer']
        tr_base = (pts.get(base['in'], 0) - pts.get(base['out'], 0)) if base else 0

        results.append({'gw': gw, 'team': tid, 'tool': tool, 'unchanged': same,
                        'hindsight': best, 'cap_tool': cap_tool, 'cap_you': cap_you,
                        'tr_tool': tr_tool, 'tr_base': tr_base})

        print('GW' + str(gw) + ' | team ' + str(tid))
        print('  lineup + captain pts: tool ' + str(tool) + ' | unchanged ' + str(same) +
              ' | hindsight best ' + str(best))
        print('  captain: tool ' + nm(p['tool_captain']) + ' ' + str(cap_tool) +
              ' pts | yours ' + nm(p['unchanged_captain']) + ' ' + str(cap_you) + ' pts')
        print('  transfers: tool ' + format(tr_tool, '+d') + ' (' + str(len(p['tool_transfers'])) +
              ' suggested) | simple ep_next rule ' + format(tr_base, '+d'))

    if results:
        n = len(results)

        def avg(key):
            return sum(x[key] for x in results) / n

        print('')
        print('Averages over ' + str(n) + ' team-gameweek(s):')
        print('  lineup + captain: tool %.1f | unchanged %.1f | hindsight best %.1f'
              % (avg('tool'), avg('unchanged'), avg('hindsight')))
        print('  captain pts: tool %.1f | yours %.1f' % (avg('cap_tool'), avg('cap_you')))
        print('  transfer net pts: tool %.1f | simple ep_next rule %.1f'
              % (avg('tr_tool'), avg('tr_base')))
        print('  (small samples are mostly noise - judge this over many gameweeks)')
    if pending:
        print('Waiting on FPL to finalise points for: ' +
              ', '.join('GW' + str(g) for g in sorted(pending)))
    return results

if __name__ == '__main__':
    args = sys.argv[1:]
    if not args or args[0] not in ('snapshot', 'score'):
        print(__doc__ if __doc__ else 'Usage: eval_log.py snapshot <team ids> | score')
        sys.exit(1)
    if args[0] == 'score':
        score()
    else:
        free = 1
        rest = args[1:]
        if '--free' in rest:
            i = rest.index('--free')
            free = int(rest[i + 1])
            del rest[i:i + 2]
        ids = [int(a) for a in rest]
        if not ids:
            print('Give at least one Team ID.')
            sys.exit(1)
        snapshot(ids, free)