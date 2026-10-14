"""Parse forecasts exported from the rendered, signed-in Yahoo Fantasy UI.

Browser access stays with the assistant's browser tools. This module does not
read cookies, automate login, submit roster changes, or call private web APIs.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .enrichment import number


def projection_capture_path(league_key: str, week: int) -> Path:
    if not re.fullmatch(r'\w+\.l\.\d+', league_key) or week < 1:
        raise ValueError('Invalid league key or scoring week')
    return Path('data/private/yahoo-projections') / f'{league_key}-week{week}.json'


def parse_yahoo_projection_page(page: dict, league_key: str, week: int) -> list[dict]:
    """Cells/headers come from read-only rendered DOM extraction.

    The roster has a separate Proj Pts column. In the player list, Fan Pts is
    projected only when the selected Stats value is exactly Week N (proj).
    Colspans and hidden edit columns must stay in the exported cell order.
    """
    url = urlparse(page['url'])
    league_id = league_key.split('.l.')[1]
    if url.scheme != 'https' or url.hostname != 'football.fantasysports.yahoo.com' or not (
            url.path == f'/f1/{league_id}' or url.path.startswith(f'/f1/{league_id}/')):
        raise ValueError('Projection page is not from the requested Yahoo league')
    results = []
    for table in page.get('tables', []):
        headers = [h['text'].strip() for h in table['headers'] for _ in range(h.get('colspan', 1))]
        if 'Proj Pts' in headers:
            match = re.search(r'roster for week (\d+)', table.get('caption', ''), re.I)
            if not match or int(match[1]) != week:
                raise ValueError('Roster projection table is for a different scoring week')
            index = headers.index('Proj Pts')
        else:
            if page.get('selected_stats') != f'Week {week} (proj)':
                raise ValueError('Player list must select the requested weekly projected stats')
            indexes = [i for i, h in enumerate(headers) if h.startswith('Fan Pts')]
            if len(indexes) != 1:
                raise ValueError('Cannot identify the Yahoo projected-points column')
            index = indexes[0]
        for row in table.get('rows', []):
            player_id = str(row['player_id'])
            if not player_id.isdigit():
                raise ValueError('Projection row lacks a Yahoo player ID')
            cells = [c['text'].strip() for c in row['cells'] for _ in range(c.get('colspan', 1))]
            if index >= len(cells):
                raise ValueError('Projection row does not align with table headers')
            points = number(cells[index])
            if points is not None:
                results.append({'player_key': f"{league_key.split('.')[0]}.p.{player_id}",
                                'projected_points': points})
    return results


def build_yahoo_projection_capture(pages: list[dict], league_key: str, week: int,
                                    generated_at: str | None = None) -> dict:
    players = {}
    for page in pages:
        for row in parse_yahoo_projection_page(page, league_key, week):
            key = row['player_key']
            if key in players and players[key]['projected_points'] != row['projected_points']:
                raise ValueError('Yahoo projection changed during capture; refresh conflicting pages')
            players[key] = row
    if not players:
        raise ValueError('No numeric Yahoo forecasts captured')
    return {'league_key': league_key, 'week': week, 'source': 'yahoo_fantasy_ui',
            'generated_at': generated_at or datetime.now(timezone.utc).isoformat(),
            'players': list(players.values()),
            'capture_context': {'method': 'rendered_yahoo_fantasy_tables', 'pages': len(pages)}}
