import pytest

from yahoo_waiver_assistant.client import YahooFantasyClient
from yahoo_waiver_assistant.yahoo_json import unique_scalar_values


def test_available_players_rejects_unknown_status():
    client = YahooFantasyClient(lambda: "token")
    with pytest.raises(ValueError):
        client.available_players("league-key", status="UNKNOWN")


def test_unique_scalar_values_handles_yahoo_style_nested_json():
    payload = {
        "fantasy_content": {
            "users": {
                "0": {
                    "user": [
                        {
                            "games": {
                                "0": {
                                    "game": [
                                        {
                                            "game_key": "461",
                                            "teams": {
                                                "0": {
                                                    "team": [
                                                        {
                                                            "team_key": "461.l.123.t.4",
                                                            "name": "Example Team",
                                                        }
                                                    ]
                                                }
                                            },
                                        }
                                    ]
                                }
                            }
                        }
                    ]
                }
            }
        }
    }

    assert unique_scalar_values(payload, "team_key") == ["461.l.123.t.4"]
    assert unique_scalar_values(payload, "game_key") == ["461"]


def test_new_endpoints_are_read_only_and_league_scoped():
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {}
    class Session:
        calls = []
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return Response()
    session = Session()
    client = YahooFantasyClient(lambda: 'test-token', session)
    client.league_settings('999.l.123')
    client.league_rosters('999.l.123', 6)
    client.weekly_player_stats('999.l.123', ['999.p.1', '999.p.2'], 5)
    assert session.calls[0][0].endswith('/league/999.l.123/settings')
    assert session.calls[1][0].endswith('/league/999.l.123/teams/roster;week=6')
    assert session.calls[2][0].endswith('/league/999.l.123/players;player_keys=999.p.1,999.p.2/stats;type=week;week=5')
    assert all(call[1]['params'] == {'format': 'json'} for call in session.calls)
    with pytest.raises(ValueError):
        client.weekly_player_stats('999.l.123', ['999.p.1'] * 26, 5)
