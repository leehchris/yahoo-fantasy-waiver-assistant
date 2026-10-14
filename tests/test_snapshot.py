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
