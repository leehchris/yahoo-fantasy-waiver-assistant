from yahoo_waiver_assistant.chatgpt_feed import build_feed
from datetime import datetime, timezone


def test_feed_includes_roster_and_candidates_without_secret_fields():
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "team_key": "470.l.1.t.1", "league_key": "470.l.1", "week": 7,
        "league_settings": {"name": "Test League", "league_key": "470.l.1", "current_week": 7},
        "availability_coverage": {"FA": {"complete": True, "count": 1}, "W": {"complete": True, "count": 1}},
        "acquisitions": {"remaining": 5, "faab_balance": 73},
        "roster": {"name": "Test Team", "faab_balance": 73, "team_key": "470.l.1.t.1", "week": 7,
                   "players": [{"player_key": "p1", "name": "Starter", "status": "Q",
                                "selected_position": "RB", "oauth_token": "DO_NOT_EXPORT"}]},
        "waivers": [{"player_key": "p2", "name": "Waiver", "availability": "W"}],
        "free_agents": [{"player_key": "p3", "name": "Free", "availability": "FA"}],
        "projections": [{"player_key": "p1", "projected_points": None, "source": "missing"}],
        "recent_estimates": [], "data_quality": {},
        "transactions": []
    }
    result = build_feed(snapshot)
    assert len(result["available_players"]) == 2
    assert result["my_team"]["players"][0]["yahoo_projected_points"] is None
    assert result["my_team"]["players"][0]["status"] == "Q"
    assert result["available_players"][0]["availability"] == "W"
    assert "oauth_token" not in str(result)
    assert result["acquisitions"]["remaining"] == 5
