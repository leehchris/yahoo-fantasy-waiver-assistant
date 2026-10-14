from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .yahoo_json import (discovery_summary, league_key_from_team,
                         normalize_players, normalize_roster, normalize_transactions)
from .enrichment import (normalize_settings, normalize_league_rosters,
                         fetch_history, acquisition_context)
from .forecasts import recent_results_estimate, load_provider_projections
from .yahoo_ui import projection_capture_path
from .future_forecasts import attach_future_projections


def resolve_team(client, team_key: str | None = None) -> str:
    if team_key:
        league_key_from_team(team_key)
        return team_key
    keys = discovery_summary(client.discover_nfl_teams())["team_keys"]
    if not keys:
        raise ValueError("No teams discovered; provide --team-key")
    # NFL game keys increase each season; never silently choose between leagues.
    latest = max(int(key.split(".")[0]) for key in keys)
    current = [key for key in keys if int(key.split(".")[0]) == latest]
    if len(current) != 1:
        raise ValueError("Multiple teams in the latest season; provide --team-key")
    return current[0]


def available_all(client, league_key: str, status: str) -> list[dict]:
    result = []
    seen = set()
    start = 0
    while True:
        page = normalize_players(client.available_players(
            league_key, status=status, start=start, count=25), status)
        if not page:
            return result
        keys = [player["player_key"] for player in page]
        if any(not key or key in seen for key in keys) or len(set(keys)) != len(keys):
            raise ValueError("Yahoo returned duplicate or missing player keys during pagination")
        seen.update(keys)
        result.extend(page)
        start += len(page)


def create_snapshot(client, team_key: str | None = None, week: int | None = None,
                    history_weeks: int = 4, projections_file: Path | None = None,
                    lookahead: int = 2) -> dict:
    if not 0 <= history_weeks <= 8:
        raise ValueError('history_weeks must be between 0 and 8')
    team_key = resolve_team(client, team_key)
    league_key = league_key_from_team(team_key)
    started = datetime.now(timezone.utc).isoformat()
    settings = normalize_settings(client.league_settings(league_key))
    if settings['league_key'] != league_key:
        raise ValueError('Yahoo returned settings for a different league')
    current_week = settings['current_week']
    week = week if week is not None else current_week
    if week is None or not 1 <= week <= (settings['end_week'] or 18):
        raise ValueError('Cannot resolve a valid NFL scoring week')
    payload = {"schema_version": 2, "capture_started_at": started,
               "team_key": team_key, "league_key": league_key, 'week': week,
               'league_settings': settings,
               "roster": normalize_roster(client.roster(team_key, week=week)),
               'league_rosters': normalize_league_rosters(client.league_rosters(league_key, week)),
               "waivers": available_all(client, league_key, "W"),
               "free_agents": available_all(client, league_key, "FA"),
               "transactions": normalize_transactions(client.transactions(league_key))}
    players = {p['player_key']: p for p in payload['roster']['players'] + payload['waivers'] + payload['free_agents']}
    # Never include current/future scoring periods in a recent-results forecast.
    last_complete = min(week - 1, (current_week or week) - 1)
    weeks = list(range(max(settings['start_week'] or 1, last_complete - history_weeks + 1), last_complete + 1))
    history = fetch_history(client, league_key, list(players), weeks)
    payload['recent_results'] = history
    captured = datetime.now(timezone.utc).isoformat()
    payload['captured_at'] = captured
    payload['recent_estimates'] = [recent_results_estimate(p, history, week, captured) for p in players.values()]
    payload['projections'] = [{'player_key': key, 'week': week, 'projected_points': None,
                               'source': 'yahoo_projection_missing', 'captured_at': None,
                               'confidence': 'Unspecified', 'sample_weeks': [],
                               'limitations': ['Current Yahoo projected points have not been captured.']}
                              for key in players]
    projection_warning = None
    default_capture = projection_capture_path(league_key, week)
    if projections_file is None and default_capture.exists():
        try:
            load_provider_projections(default_capture, league_key, week, set(players))
        except ValueError as exc:
            projection_warning = str(exc)
        else:
            projections_file = default_capture
    if projections_file:
        imported = {p['player_key']: p for p in load_provider_projections(
            projections_file, league_key, week, set(players))}
        payload['projections'] = [imported.get(p['player_key'], p) for p in payload['projections']]
    payload['acquisitions'] = acquisition_context(settings, payload['roster'], week)
    payload['data_quality'] = {
        'yahoo_projections_available': any(p['source'] == 'yahoo_fantasy_ui' for p in payload['projections']),
        'yahoo_api_projections_available': False,
        'projection_warning': projection_warning,
        'projection_note': 'Yahoo rejected the projected-stats option during live verification. '
                           'Yahoo projected points are captured from signed-in rendered league pages. '
                           'Missing Yahoo projections stay null; recent estimates are separate diagnostics.',
        'history_weeks': weeks,
        'projected_players': sum(p['projected_points'] is not None for p in payload['projections']),
        'missing_projections': sum(p['projected_points'] is None for p in payload['projections']),
        'news_note': 'Injury labels and note timestamps are captured; news stories and depth charts are not.'}
    return attach_future_projections(payload, lookahead)


def save_snapshot(payload: dict, directory: Path = Path("data/private")) -> Path:
    """Write only after all requests succeed; create a unique file without overwriting."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (datetime.now(timezone.utc).strftime("snapshot-%Y%m%dT%H%M%SZ-")
                        + uuid4().hex[:8] + ".json")
    encoded = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(encoded)
    return path
