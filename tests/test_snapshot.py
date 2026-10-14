import json

import pytest

from yahoo_waiver_assistant.snapshot import create_snapshot, save_snapshot, resolve_team
from yahoo_waiver_assistant.cli import build_parser


class FakeClient:
    def __init__(self):
        self.calls = []

    def discover_nfl_teams(self):
        return {'teams': [{'team': [{'team_key': '998.l.1.t.1'}]},
                          {'team': [{'team_key': '999.l.123.t.1'}]}]}

    def league_settings(self, key):
        return {'league': [{'league_key': key, 'current_week': 6, 'start_week': 1, 'end_week': 17},
                           {'settings': [{'max_weekly_adds': '5'}]}]}

    def league_rosters(self, key, week):
        return {'teams': {'count': 0}}

    def weekly_player_stats(self, key, player_keys, week):
        self.calls.append(('history', key, player_keys, week))
        return {'players': {str(i): {'player': [[{'player_key': pk}],
            {'player_points': {'0': {'coverage_type': 'week', 'week': str(week)}, 'total': '10'},
             'player_stats': {'0': {'coverage_type': 'week', 'week': str(week)}, 'stats': []}}]}
            for i, pk in enumerate(player_keys)}}

    def roster(self, key, week=None):
        self.calls.append(('roster', key, week))
        return {'team': [{'team_key': key}, {'roster': {'players': {'count': 0}}}]}

    def available_players(self, key, status, start, count):
        self.calls.append((status, key, start, count))
        # A short page must not truncate the snapshot.
        if start >= 2:
            return {'players': {'count': 0}}
        return {'players': {'0': {'player': [[{'player_key': f'999.p.{start+1}'}]]}, 'count': 1}}

    def transactions(self, key):
        self.calls.append(('transactions', key))
        return {'transactions': {'count': 0}}


def test_snapshot_discovery_pagination_and_save(tmp_path):
    client = FakeClient()
    payload = create_snapshot(client, week=3)
    assert payload['league_key'] == '999.l.123'
    assert len(payload['waivers']) == len(payload['free_agents']) == 2
    assert ('roster', '999.l.123.t.1', 3) in client.calls
    assert ('FA', '999.l.123', 2, 25) in client.calls
    paths = [save_snapshot(payload, tmp_path) for _ in range(2)]
    assert paths[0] != paths[1]
    assert json.loads(paths[0].read_text()) == payload
    assert 'access_token' not in paths[0].read_text()


def test_explicit_team_does_not_discover():
    assert resolve_team(object(), '999.l.123.t.1') == '999.l.123.t.1'


def test_ambiguous_and_empty_discovery():
    class Discovery:
        def discover_nfl_teams(self):
            return {'teams': [{'team': {'team_key': '999.l.1.t.1'}},
                              {'team': {'team_key': '999.l.2.t.1'}}]}
    with pytest.raises(ValueError, match='Multiple teams'):
        resolve_team(Discovery())
    class Empty:
        def discover_nfl_teams(self):
            return {}
    with pytest.raises(ValueError, match='No teams'):
        resolve_team(Empty())


def test_repeated_page_aborts():
    class Repeated(FakeClient):
        def available_players(self, *args, **kwargs):
            return {'player': [[{'player_key': '999.p.1'}]]}
    with pytest.raises(ValueError, match='duplicate'):
        create_snapshot(Repeated())


def test_request_failure_does_not_save(tmp_path, monkeypatch):
    from yahoo_waiver_assistant import cli
    class Failure(FakeClient):
        def transactions(self, key):
            raise RuntimeError('Request failed')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, '_services', lambda: (None, None, Failure()))
    monkeypatch.setattr('sys.argv', ['waiver-assistant', 'snapshot', '--team-key', '999.l.123.t.1'])
    with pytest.raises(RuntimeError, match='Request failed'):
        cli.main()
    assert not (tmp_path / 'data').exists()


def test_cli_snapshot_saves_private_file(tmp_path, monkeypatch, capsys):
    from yahoo_waiver_assistant import cli
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, '_services', lambda: (None, None, FakeClient()))
    monkeypatch.setenv('YAHOO_TEAM_KEY', '999.l.123.t.1')
    monkeypatch.setattr('sys.argv', ['waiver-assistant', 'snapshot'])
    cli.main()
    assert len(list((tmp_path / 'data/private').glob('snapshot-*.json'))) == 1
    assert 'Saved private snapshot:' in capsys.readouterr().out
    assert build_parser().parse_args(['snapshot', '--week', '4']).week == 4


def test_snapshot_enrichment_completed_weeks_only():
    client = FakeClient()
    payload = create_snapshot(client)
    assert payload['schema_version'] == 2
    assert payload['week'] == 6
    assert payload['data_quality']['history_weeks'] == [2, 3, 4, 5]
    assert len(payload['recent_results']) == 8
    assert all(p['source'] == 'recent_actuals_estimate' for p in payload['recent_estimates'])
    assert all(p['projected_points'] == 10 for p in payload['recent_estimates'])
    assert all(p['projected_points'] is None for p in payload['projections'])
    assert payload['data_quality']['yahoo_projections_available'] is False


def test_snapshot_no_history_and_early_season():
    assert create_snapshot(FakeClient(), history_weeks=0)['recent_results'] == []
    assert create_snapshot(FakeClient(), week=1)['recent_results'] == []
    with pytest.raises(ValueError):
        create_snapshot(FakeClient(), history_weeks=9)


def test_provider_overrides_only_matched_player(tmp_path):
    from datetime import datetime, timezone
    path = tmp_path / 'provider.json'
    path.write_text(json.dumps({'league_key': '999.l.123', 'week': 6,
        'source': 'Example provider', 'generated_at': datetime.now(timezone.utc).isoformat(),
        'players': [{'player_key': '999.p.1', 'projected_points': 12.5}]}))
    payload = create_snapshot(FakeClient(), projections_file=path)
    forecasts = {p['player_key']: p for p in payload['projections']}
    assert forecasts['999.p.1']['projected_points'] == 12.5
    assert forecasts['999.p.1']['source'] == 'Example provider'
    assert forecasts['999.p.2']['source'] == 'yahoo_projection_missing'
    assert forecasts['999.p.2']['projected_points'] is None


def test_history_failure_prevents_file_creation(tmp_path, monkeypatch):
    from yahoo_waiver_assistant import cli
    class Failure(FakeClient):
        def weekly_player_stats(self, *args):
            raise RuntimeError('History request failed')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, '_services', lambda: (None, None, Failure()))
    monkeypatch.setattr('sys.argv', ['waiver-assistant', 'snapshot', '--team-key', '999.l.123.t.1'])
    with pytest.raises(RuntimeError, match='History request failed'):
        cli.main()
    assert not (tmp_path / 'data').exists()


def test_default_yahoo_capture_loaded_without_file_argument(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from yahoo_waiver_assistant.yahoo_ui import projection_capture_path
    monkeypatch.chdir(tmp_path)
    path = projection_capture_path('999.l.123', 6)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'league_key': '999.l.123', 'week': 6,
        'source': 'yahoo_fantasy_ui', 'generated_at': datetime.now(timezone.utc).isoformat(),
        'players': [{'player_key': '999.p.1', 'projected_points': 12.5}]}))
    payload = create_snapshot(FakeClient())
    assert payload['data_quality']['yahoo_projections_available'] is True
    assert payload['data_quality']['yahoo_api_projections_available'] is False
    assert payload['projections'][0]['projected_points'] == 12.5
    assert payload['projections'][1]['projected_points'] is None
    assert payload['recent_estimates'][1]['projected_points'] == 10


def test_stale_default_yahoo_capture_does_not_replace_missing_forecast(tmp_path, monkeypatch):
    from datetime import datetime, timezone, timedelta
    from yahoo_waiver_assistant.yahoo_ui import projection_capture_path
    monkeypatch.chdir(tmp_path)
    path = projection_capture_path('999.l.123', 6)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'league_key': '999.l.123', 'week': 6,
        'source': 'yahoo_fantasy_ui',
        'generated_at': (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        'players': [{'player_key': '999.p.1', 'projected_points': 12.5}]}))
    payload = create_snapshot(FakeClient())
    assert all(p['projected_points'] is None for p in payload['projections'])
    assert 'stale' in payload['data_quality']['projection_warning']
