"""One read-only refresh produces a private report bundle."""
from .snapshot import create_snapshot, save_snapshot
from .performance import fetch_season, load_history, build_performance, render_performance
from .report import build_report, render_report
from .planning import build_upcoming_plan, render_upcoming_plan


def build_bundle(snapshot: dict, performance: dict, lookahead: int = 2, limit: int = 10) -> dict:
    return {'snapshot_captured_at': snapshot['captured_at'],
            'waivers_and_lineup': build_report(snapshot, limit=limit),
            'upcoming_plan': build_upcoming_plan(snapshot, lookahead=lookahead, limit=limit),
            'performance': performance}


def refresh(client, team_key=None, *, lookahead=2, limit=10, history_file=None):
    snapshot = create_snapshot(client, team_key, lookahead=lookahead)
    season = fetch_season(client, snapshot, load_history(snapshot['team_key'], history_file))
    snapshot['season_history'] = season
    performance = build_performance(season, {p['player_key'] for p in snapshot['roster']['players']})
    bundle = build_bundle(snapshot, performance, lookahead, limit)
    snapshot_path = save_snapshot(snapshot)
    return snapshot_path, bundle


def render_bundle(bundle: dict) -> str:
    return ('# Your fantasy football update\n\nRead-only: no Yahoo changes made.\n\n'
            'Current/future projections use existing Yahoo page captures; the API refresh does not refresh browser forecasts.\n\n'
            + render_report(bundle['waivers_and_lineup']) + '\n'
            + render_upcoming_plan(bundle['upcoming_plan']) + '\n'
            + render_performance(bundle['performance']))
