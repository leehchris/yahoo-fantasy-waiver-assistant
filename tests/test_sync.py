from datetime import datetime, timezone, timedelta
from copy import deepcopy
import pytest
from yahoo_waiver_assistant.freshness import validate_snapshot
from yahoo_waiver_assistant.sync import publish
from yahoo_waiver_assistant.client import YahooFantasyClient
from yahoo_waiver_assistant.oauth import TokenStore, YahooOAuth

def snapshot():
    return {'captured_at': datetime.now(timezone.utc).isoformat(), 'week': 8,
        'team_key': '999.l.1.t.1', 'league_key': '999.l.1',
        'league_settings': {'current_week': 8, 'league_key': '999.l.1'},
        'roster': {'team_key': '999.l.1.t.1', 'week': 8, 'players': [{'player_key': '999.p.1'}]},
        'free_agents': [{'player_key': '999.p.2'}], 'waivers': [],
        'availability_coverage': {'FA': {'complete': True, 'count': 1}, 'W': {'complete': True, 'count': 0}}}

def test_freshness_guards():
    data = snapshot()
    assert validate_snapshot(data)['free_agent_count'] == 1
    for field, value in [('captured_at', (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()),
        ('captured_at', datetime.now().isoformat()), ('week', 7), ('availability_coverage', {}),
        ('free_agents', [{'player_key': '999.p.1'}])]:
        bad = deepcopy(data)
        bad[field] = value
        with pytest.raises(ValueError): validate_snapshot(bad)
    with pytest.raises(ValueError): validate_snapshot(data, expected_week=9)

def test_public_and_stale_publish_blocked():
    calls = []
    def api(path, **kwargs):
        calls.append(path)
        return {'private': False, 'full_name': 'owner/repo'}
    data = snapshot()
    with pytest.raises(ValueError): publish('owner/repo', data, api=api)
    assert calls == ['repos/owner/repo']
    calls.clear()
    data['captured_at'] = '2020-01-01T00:00:00Z'
    with pytest.raises(ValueError): publish('owner/repo', data, api=api)
    assert not calls

def test_401_refresh_bounded_get_only():
    class Response:
        status_code = 401
        def raise_for_status(self): raise RuntimeError('unauthorized')
    class Session:
        def __init__(self): self.calls = []
        def get(self, url, **kwargs):
            self.calls.append(kwargs)
            return Response()
    session = Session()
    refreshes = []
    def refresh():
        refreshes.append(True)
        return 'new'
    with pytest.raises(RuntimeError): YahooFantasyClient(lambda: 'old', session, refresh).league('999.l.1')
    assert len(refreshes) == 1 and len(session.calls) == 2
    assert session.calls[1]['headers']['Authorization'] == 'Bearer new'

def test_token_rotation(tmp_path):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'access_token': 'new', 'expires_in': 3600}
    class Session:
        def post(self, *args, **kwargs): return Response()
    store = TokenStore(tmp_path/'tokens.json')
    store.save({'access_token': 'old', 'refresh_token': 'retained'})
    oauth = YahooOAuth('test', 'test', 'https://localhost:8080/callback', store, Session())
    assert oauth.refresh_access_token() == 'new'
    assert store.load()['refresh_token'] == 'retained'
    assert not list(tmp_path.glob('.yahoo-token-*'))
