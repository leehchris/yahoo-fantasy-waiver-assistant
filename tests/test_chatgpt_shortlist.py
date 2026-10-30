from yahoo_waiver_assistant.chatgpt_shortlist import build_shortlist
from datetime import datetime, timezone


def test_shortlist_filters_out_inactive_byes_and_sparse_samples():
    def player(key, name, pos, status=None, bye=9):
        return {"player_key": key, "name": name, "primary_position": pos,
                "status": status, "bye_week": bye, "availability": "W", "team": "T"}
    pool = [player("a", "Active", "QB"), player("b", "Inactive", "QB", "O"),
            player("c", "Bye", "QB", bye=7), player("d", "Sparse", "QB")]
    estimates = [{"player_key": key, "projected_points": points,
                  "sample_weeks": weeks, "confidence": "Low"}
                 for key, points, weeks in
                 [("a", 12, [4, 5, 6]), ("b", 50, [4, 5]), ("c", 30, [4, 5]),
                  ("d", 20, [6])]]
    s = {"captured_at": datetime.now(timezone.utc).isoformat(), "week": 7, "team_key": "470.l.1.t.1",
         "league_key": "470.l.1", "roster": {"players": [player('roster1', 'Roster', 'RB')], "name": "My Team", "week": 7, "team_key": "470.l.1.t.1"},
         "league_settings": {"name": "League", "current_week": 7, "league_key": "470.l.1"}, "acquisitions": {},
         "availability_coverage": {"FA": {"complete": True, "count": 0}, "W": {"complete": True, "count": 4}},
         "waivers": pool, "free_agents": [], "projections": [],
         "recent_estimates": estimates, "transactions": []}
    result = build_shortlist(s)
    assert [p["name"] for p in result["candidates_by_position"]["QB"]] == ["Active"]
    assert result["confidence"] == "Low"
