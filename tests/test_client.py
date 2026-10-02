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
