"""Load separate week-specific Yahoo captures; never extrapolate forecasts."""
from __future__ import annotations

from .forecasts import load_provider_projections
from .yahoo_ui import projection_capture_path


def attach_future_projections(snapshot: dict, lookahead: int = 2) -> dict:
    if not 0 <= lookahead <= 4:
        raise ValueError('lookahead must be between 0 and 4')
    week = snapshot['week']
    end = min(week + lookahead, snapshot['league_settings'].get('end_week') or 18)
    players = snapshot['roster']['players'] + snapshot['waivers'] + snapshot['free_agents']
    keys = {p['player_key'] for p in players}
    future = []
    coverage = []
    for target in range(week + 1, end + 1):
        path = projection_capture_path(snapshot['league_key'], target)
        warning = None
        rows = []
        if path.exists():
            try:
                rows = load_provider_projections(path, snapshot['league_key'], target, keys)
            except ValueError as exc:
                warning = str(exc)
            else:
                if any(row['source'] != 'yahoo_fantasy_ui' for row in rows):
                    rows = []
                    warning = 'Future planning requires Yahoo fantasy UI forecasts'
        else:
            rows = [row for row in snapshot.get('future_projections', [])
                    if row.get('week') == target and row.get('source') == 'yahoo_fantasy_ui'
                    and row.get('player_key') in keys]
            warning = ('Using embedded Yahoo capture; planner checks individual freshness'
                       if rows else 'No Yahoo forecast capture for this week')
        future.extend(rows)
        coverage.append({'week': target, 'captured_players': len(rows),
                         'known_players': len(keys), 'warning': warning})
    return {**snapshot, 'future_projections': future, 'future_projection_coverage': coverage}
