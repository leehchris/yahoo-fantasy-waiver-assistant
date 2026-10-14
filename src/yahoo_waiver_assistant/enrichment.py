"""League context and historical Yahoo results, distinct from forecasts."""
from __future__ import annotations

import math
from typing import Any

from .yahoo_json import fields, integer, iter_key_values, normalize_roster


def number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def metadata(value: Any) -> dict:
    """Yahoo puts coverage metadata in a numbered '0' fragment."""
    data = fields(value)
    return {**fields(data.get('0')), **data}


def normalize_settings(payload: dict) -> dict:
    league = fields(next(iter_key_values(payload, 'league'), {}))
    settings = fields(league.get('settings'))
    categories = []
    for value in iter_key_values(settings.get('stat_categories'), 'stat'):
        stat = fields(value)
        categories.append({key: stat.get(key) for key in (
            'stat_id', 'name', 'display_name', 'position_type', 'is_only_display_stat')})
        categories[-1]['stat_id'] = str(stat['stat_id'])
    modifiers = []
    for value in iter_key_values(settings.get('stat_modifiers'), 'stat'):
        stat = fields(value)
        modifiers.append({'stat_id': str(stat['stat_id']), 'value': number(stat.get('value')),
                          # Preserve complex bonus/position rules without pretending
                          # a simple multiplication implements them.
                          'rules': {k: v for k, v in stat.items() if k not in {'stat_id', 'value'}}})
    positions = []
    for value in iter_key_values(settings.get('roster_positions'), 'roster_position'):
        position = fields(value)
        positions.append({'position': position.get('position'),
                          'count': integer(position.get('count')),
                          'is_starting_position': str(position.get('is_starting_position')) == '1'})
    return {'league_key': league.get('league_key'), 'name': league.get('name'),
            'season': integer(league.get('season')), 'current_week': integer(league.get('current_week')),
            'start_week': integer(league.get('start_week')), 'end_week': integer(league.get('end_week')),
            'scoring_type': settings.get('scoring_type', league.get('scoring_type')),
            'max_weekly_adds': integer(settings.get('max_weekly_adds')),
            'uses_faab': str(settings.get('uses_faab')) == '1',
            'waiver_type': settings.get('waiver_type'), 'waiver_rule': settings.get('waiver_rule'),
            'waiver_time': integer(settings.get('waiver_time')),
            'playoff_start_week': integer(settings.get('playoff_start_week')),
            'roster_positions': positions, 'stat_categories': categories, 'stat_modifiers': modifiers}


def normalize_league_rosters(payload: dict) -> list[dict]:
    return [normalize_roster({'team': team}) for team in iter_key_values(payload, 'team')]


def normalize_weekly_results(payload: dict, requested_week: int) -> list[dict]:
    results = []
    for value in iter_key_values(payload, 'player'):
        player = fields(value)
        stats = metadata(player.get('player_stats'))
        points = metadata(player.get('player_points'))
        for coverage in (stats, points):
            if coverage and (coverage.get('coverage_type') != 'week' or
                             integer(coverage.get('week')) != requested_week):
                raise ValueError('Yahoo returned stats for a different scoring period')
        values = {str(fields(stat)['stat_id']): number(fields(stat).get('value'))
                  for stat in iter_key_values(stats.get('stats'), 'stat')}
        results.append({'player_key': player.get('player_key'), 'week': requested_week,
                        'actual_points': number(points.get('total')),
                        'stats': values, 'source': 'yahoo_league_weekly_stats'})
    return results


def fetch_history(client, league_key: str, player_keys: list[str], weeks: list[int]) -> list[dict]:
    results = []
    for week in weeks:
        for offset in range(0, len(player_keys), 25):
            batch = player_keys[offset:offset + 25]
            rows = normalize_weekly_results(client.weekly_player_stats(league_key, batch, week), week)
            returned = [row['player_key'] for row in rows]
            if len(returned) != len(set(returned)) or set(returned) != set(batch):
                raise ValueError('Yahoo returned missing, duplicate, or unexpected historical players')
            results.extend(rows)
    return results


def acquisition_context(settings: dict, roster: dict, week: int) -> dict:
    limit = settings.get('max_weekly_adds')
    adds = roster.get('roster_adds', {})
    used = adds.get('value') if (adds.get('coverage_type') == 'week' and
                               adds.get('coverage_value') == week) else None
    # Yahoo -1 means unlimited; do not invent a finite acquisition allowance.
    remaining = max(0, limit - used) if limit is not None and limit >= 0 and used is not None else None
    return {'weekly_limit': limit, 'used': used, 'remaining': remaining,
            'unlimited': limit == -1, 'faab_balance': roster.get('faab_balance')}
