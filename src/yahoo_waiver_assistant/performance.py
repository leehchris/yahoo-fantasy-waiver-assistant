"""Historical comparisons use Yahoo's retained weekly projections, never estimates."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

from .enrichment import fetch_history, number
from .lineups import RESERVE_SLOTS
from .yahoo_json import normalize_roster
from .yahoo_ui import parse_yahoo_projection_page


def history_path(team_key: str) -> Path:
    from .yahoo_json import league_key_from_team
    league_key_from_team(team_key)
    return Path('data/private/yahoo-history') / f'{team_key}.json'


def import_history(pages: list[dict], team_key: str, league_key: str, current_week: int) -> dict:
    """Accept only completed-week roster DOM exports for the specified team."""
    rows = {}
    for page in pages:
        week = page.get('week')
        if type(week) is not int or not 1 <= week < current_week:
            raise ValueError('Historical projections require a completed week')
        path = urlparse(page['url']).path.rstrip('/')
        base = f"/f1/{league_key.split('.l.')[1]}/{team_key.split('.t.')[1]}"
        if path not in {base, base + '/team'}:
            raise ValueError('Historical page is for a different team')
        if any('Proj Pts' not in [h['text'].strip() for h in t['headers']] for t in page.get('tables', [])):
            raise ValueError('Historical import requires roster projection columns')
        for row in parse_yahoo_projection_page(page, league_key, week):
            key = (week, row['player_key'])
            if key in rows and rows[key]['projected_points'] != row['projected_points']:
                raise ValueError('Conflicting historical projections')
            rows[key] = {**row, 'week': week}
    if not rows:
        raise ValueError('No historical projections found')
    return {'team_key': team_key, 'league_key': league_key,
            'source': 'yahoo_historical_roster_ui',
            'captured_at': datetime.now(timezone.utc).isoformat(), 'players': list(rows.values())}


def fetch_season(client, snapshot: dict, capture: dict | None = None) -> dict:
    settings = snapshot['league_settings']
    weeks = range(settings.get('start_week') or 1, settings.get('current_week') or snapshot['week'])
    rosters = []
    actuals = []
    for week in weeks:
        roster = normalize_roster(client.roster(snapshot['team_key'], week=week))
        if roster.get('team_key') != snapshot['team_key'] or roster.get('week') != week:
            raise ValueError('Historical roster team/week mismatch')
        keys = [p['player_key'] for p in roster['players']]
        if len(keys) != len(set(keys)):
            raise ValueError('Duplicate historical roster players')
        rosters.append({'week': week, 'players': roster['players']})
        if keys:
            actuals.extend(fetch_history(client, snapshot['league_key'], keys, [week]))
    return {'team_key': snapshot['team_key'], 'league_key': snapshot['league_key'],
            'rosters': rosters, 'actuals': actuals, 'projection_capture': capture}


def load_history(team_key: str, path: Path | None = None) -> dict | None:
    path = path or history_path(team_key)
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else None


def build_performance(season: dict, current_keys: set[str] | None = None) -> dict:
    capture = season.get('projection_capture')
    projections = {}
    expected = {(r['week'], p['player_key']) for r in season['rosters'] for p in r['players']}
    if len({r['week'] for r in season['rosters']}) != len(season['rosters']):
        raise ValueError('Duplicate historical roster week')
    if capture:
        if (capture.get('team_key') != season['team_key'] or capture.get('league_key') != season['league_key']
                or capture.get('source') != 'yahoo_historical_roster_ui'):
            raise ValueError('Historical projection source/team/league mismatch')
        for row in capture['players']:
            key = (row['week'], row['player_key'])
            value = number(row.get('projected_points'))
            if type(row['week']) is not int or key not in expected or value is None or key in projections:
                raise ValueError('Invalid or duplicate historical projection')
            projections[key] = value
    actuals = {}
    for row in season['actuals']:
        key = (row['week'], row['player_key'])
        if key in actuals:
            raise ValueError('Duplicate historical result')
        actuals[key] = number(row.get('actual_points'))
    players = {}
    weekly = []
    for roster in season['rosters']:
        week = roster['week']
        starters = []
        for p in roster['players']:
            key = (week, p['player_key'])
            a, f = actuals.get(key), projections.get(key)
            slot = p.get('selected_position')
            if p.get('week') not in {None, week}:
                raise ValueError('Historical selected position week mismatch')
            if slot is None:
                raise ValueError('Historical selected position is missing')
            if slot not in RESERVE_SLOTS | {'BN'}:
                starters.append({'actual': a, 'projected': f})
            item = players.setdefault(p['player_key'], {'player_key': p['player_key'], 'name': p['name'],
                'current_roster': current_keys is not None and p['player_key'] in current_keys, 'weeks': []})
            if a is not None and f is not None and f > 0 and slot not in RESERVE_SLOTS:
                item['weeks'].append({'week': week, 'actual': a, 'projected': f, 'slot': slot})
        complete = bool(starters) and all(r['actual'] is not None and r['projected'] is not None for r in starters)
        actual = sum(r['actual'] for r in starters) if starters and all(r['actual'] is not None for r in starters) else None
        projected = sum(r['projected'] for r in starters) if complete else None
        weekly.append({'week': week, 'actual': actual, 'projected': projected,
                       'delta': actual - projected if complete else None,
                       'missing_starter_comparisons': sum(r['actual'] is None or r['projected'] is None for r in starters)})
    for p in players.values():
        rows = p['weeks']
        p.update(sample_weeks=len(rows), actual=sum(r['actual'] for r in rows),
                 projected=sum(r['projected'] for r in rows), misses=sum(r['actual'] < r['projected'] for r in rows))
        p['delta'] = p['actual'] - p['projected'] if rows else None
        p['percent_shortfall'] = 100 * (1 - p['actual'] / p['projected']) if rows else None
        zeros = [r for r in rows if r['actual'] == 0]
        p['zero_point_weeks'] = [r['week'] for r in zeros]
        p['zero_shortfall'] = sum(r['projected'] for r in zeros)
        p['delta_excluding_zeros'] = sum(r['actual'] - r['projected'] for r in rows if r['actual'] != 0)
        # A transparent screen, not a statistical significance or drop rule.
        p['repeated_shortfall'] = (len(rows) >= 3 and p['misses'] / len(rows) >= .6
                                  and p['percent_shortfall'] >= 20)
    complete = bool(weekly) and all(r['delta'] is not None for r in weekly)
    return {'team_key': season['team_key'], 'weekly': weekly,
            'season_delta': sum(r['delta'] for r in weekly) if complete else None,
            'comparison_complete': complete, 'projection_captured_at': capture.get('captured_at') if capture else None,
            'players': sorted(players.values(), key=lambda p: p['delta'] if p['delta'] is not None else float('inf')),
            'limitations': ['Player comparisons cover weeks on this roster, including bench; positive projections only.',
                'Zero-point games are identified, but injury/inactive causes are not inferred.',
                'Yahoo retained historical forecasts are retrospective captures, not independently archived pregame forecasts.',
                'Repeated-shortfall screen: at least 3 comparable weeks, 60% misses and 20% aggregate shortfall; not a drop recommendation.']}


def render_performance(report: dict) -> str:
    lines = ['# Season performance', '', 'Missing historical forecasts remain unknown.', '',
             '| Week | Actual | Projected | Difference |', '|---|---:|---:|---:|']
    fmt = lambda v: 'Unknown' if v is None else f'{v:.2f}'
    for r in report['weekly']:
        lines.append(f"| {r['week']} | {fmt(r['actual'])} | {fmt(r['projected'])} | {fmt(r['delta'])} |")
    lines += ['', f"Season difference: {fmt(report['season_delta'])}.", '',
              '## Current players (weeks on your roster)', '',
              '| Player | Weeks | Actual | Projected | Difference | Misses | Zero weeks | Repeated shortfall |',
              '|---|---:|---:|---:|---:|---:|---|---|']
    for p in report['players']:
        if not p['current_roster']:
            continue
        name = p['name'].replace('|', '\\|').replace('\n', ' ')
        lines.append(f"| {name} | {p['sample_weeks']} | {fmt(p['actual']) if p['sample_weeks'] else 'Unknown'} | "
                     f"{fmt(p['projected']) if p['sample_weeks'] else 'Unknown'} | {fmt(p['delta'])} | {p['misses']} | "
                     f"{', '.join(map(str, p['zero_point_weeks'])) or 'None'} | {'Review' if p['repeated_shortfall'] else '—'} |")
    lines += ['', '## Zero-point context', '']
    for p in report['players']:
        if p['current_roster'] and p['zero_point_weeks']:
            name = p['name'].replace('|', '\\|').replace('\n', ' ')
            lines.append(f"- {name}: difference excluding zero-point games **{p['delta_excluding_zeros']:+.2f}** points.")
    lines += ['', '## Limits', ''] + ['- ' + x for x in report['limitations']]
    return '\n'.join(lines) + '\n'
