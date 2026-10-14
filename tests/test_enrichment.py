import json
from pathlib import Path

import pytest

from yahoo_waiver_assistant.enrichment import (
    acquisition_context, fetch_history, normalize_settings,
    normalize_league_rosters, normalize_weekly_results, number,
)


def fixture(name):
    return json.loads((Path(__file__).parent / 'fixtures' / f'{name}.json').read_text())


def test_real_settings_shape():
    settings = normalize_settings(fixture('settings'))
    assert settings['league_key'] == '999.l.123'
    assert settings['current_week'] == 6
    assert settings['max_weekly_adds'] == 3
    assert settings['uses_faab'] is True
    assert settings['roster_positions'][0] == {'position': 'QB', 'count': 1, 'is_starting_position': True}
    assert next(s for s in settings['stat_modifiers'] if s['stat_id'] == '11')['value'] == 1.0
    assert all(isinstance(s['stat_id'], str) for s in settings['stat_categories'])


def test_real_weekly_stats_numbered_coverage():
    rows = normalize_weekly_results(fixture('weekly_results'), 5)
    assert len(rows) == 2
    assert rows[0]['actual_points'] == 10
    assert rows[0]['week'] == 5
    assert rows[0]['stats']['4'] == 1
    with pytest.raises(ValueError, match='different scoring period'):
        normalize_weekly_results(fixture('weekly_results'), 4)


def test_opponent_roster_shape():
    teams = normalize_league_rosters(fixture('league_rosters'))
    assert len(teams) == 2
    assert all(t['name'] == 'Example' and t['faab_balance'] == 10 for t in teams)
    assert all(t['players'] for t in teams)


def test_complex_scoring_rules_retained():
    rules = {'bonuses': [{'bonus': {'target': '100', 'points': '3'}}]}
    payload = {'league': [{'league_key': '999.l.123'}, {'settings': {
        'stat_modifiers': {'stats': [{'stat': {'stat_id': 9, 'value': '0.1', **rules}}]}}}]}
    assert normalize_settings(payload)['stat_modifiers'][0]['rules'] == rules


@pytest.mark.parametrize('value', [None, '', '-', 'NaN', 'Infinity', True])
def test_missing_numeric_values_not_zero(value):
    assert number(value) is None


def test_acquisition_week_must_match_and_unlimited_is_explicit():
    settings = {'max_weekly_adds': 3}
    roster = {'faab_balance': 10, 'roster_adds': {'coverage_type': 'week', 'coverage_value': 6, 'value': 1}}
    assert acquisition_context(settings, roster, 6)['remaining'] == 2
    assert acquisition_context(settings, roster, 5)['remaining'] is None
    unlimited = acquisition_context({'max_weekly_adds': -1}, roster, 6)
    assert unlimited['unlimited'] and unlimited['remaining'] is None


def test_batching_and_missing_player_rejection():
    class Client:
        calls = []
        def weekly_player_stats(self, league, keys, week):
            self.calls.append((keys, week))
            return {'players': [{'player': [{'player_key': key}]} for key in keys]}
    client = Client()
    rows = fetch_history(client, '999.l.123', [f'999.p.{i}' for i in range(26)], [4, 5])
    assert len(rows) == 52
    assert [len(c[0]) for c in client.calls] == [25, 1, 25, 1]
    class Missing:
        def weekly_player_stats(self, *args):
            return {}
    with pytest.raises(ValueError, match='missing'):
        fetch_history(Missing(), '999.l.123', ['999.p.1'], [5])
