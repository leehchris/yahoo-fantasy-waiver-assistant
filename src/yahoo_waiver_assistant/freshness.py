"""Fail-closed validation for published snapshots, separate from forecast coverage."""
from datetime import datetime, timedelta, timezone


def validate_snapshot(snapshot, *, max_age_hours=24, expected_week=None, now=None):
    now = now or datetime.now(timezone.utc)
    stamp = datetime.fromisoformat(snapshot['captured_at'].replace('Z', '+00:00'))
    if stamp.utcoffset() is None or not 0 < max_age_hours <= 48:
        raise ValueError('Timezone-aware capture and maximum age of 1-48 hours required')
    if now - stamp > timedelta(hours=max_age_hours) or stamp > now + timedelta(minutes=5):
        raise ValueError('Snapshot is stale or future-dated; refresh Yahoo first')
    week = snapshot['week']
    settings = snapshot['league_settings']
    if week != settings['current_week'] or expected_week is not None and week != expected_week:
        raise ValueError('Snapshot scoring week does not match the current/requested week')
    roster = snapshot['roster']
    if roster.get('team_key') != snapshot['team_key'] or roster.get('week') != week:
        raise ValueError('Roster identity or scoring week mismatch')
    if snapshot['team_key'].split('.t.')[0] != snapshot['league_key'] or settings.get('league_key') != snapshot['league_key']:
        raise ValueError('League identity mismatch')
    groups = [roster['players'], snapshot['free_agents'], snapshot['waivers']]
    if not groups[0]:
        raise ValueError('Empty roster; capture is incomplete')
    keys = [p.get('player_key') for group in groups for p in group]
    if any(not k for k in keys) or len(keys) != len(set(keys)):
        raise ValueError('Missing, duplicate, or overlapping roster/available player keys')
    coverage = snapshot.get('availability_coverage', {})
    if not all(coverage.get(s, {}).get('complete') is True for s in ('FA', 'W')):
        raise ValueError('Complete FA and waiver pagination has not been verified')
    for status, group in zip(('FA', 'W'), groups[1:]):
        if coverage[status].get('count') != len(group):
            raise ValueError('Availability count mismatch')
    return {'captured_at': snapshot['captured_at'], 'week': week,
            'roster_count': len(groups[0]), 'free_agent_count': len(groups[1]),
            'waiver_count': len(groups[2]), 'max_age_hours': max_age_hours}
