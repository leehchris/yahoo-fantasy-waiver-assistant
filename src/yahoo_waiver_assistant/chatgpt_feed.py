"""Small, explicit read-only Yahoo feed for ChatGPT's GitHub connector.

Do not add tokens, OAuth payloads, arbitrary config or account profile fields.
Missing projections stay null; they are NOT estimated as zero.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

PLAYER_FIELDS = ("player_key", "name", "team", "primary_position", "display_position",
                 "eligible_positions", "status", "status_full", "injury_note",
                 "selected_position", "bye_week", "availability", "is_undroppable")


def slim_player(player: dict) -> dict:
    return {key: player.get(key) for key in PLAYER_FIELDS}


def build_feed(snapshot: dict) -> dict:
    from .freshness import validate_snapshot
    verification = validate_snapshot(snapshot)
    roster = snapshot["roster"]
    candidates = snapshot.get("waivers", []) + snapshot.get("free_agents", [])
    forecasts = {row["player_key"]: row for row in snapshot.get("projections", [])}
    estimates = {row.get("player_key"): row for row in snapshot.get("recent_estimates", [])}
    def enrich(player: dict) -> dict:
        row = slim_player(player)
        projection = forecasts.get(player.get("player_key"), {})
        try:
            stamp = datetime.fromisoformat(projection['captured_at'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            usable = (stamp.utcoffset() is not None and now - stamp <= timedelta(hours=48)
                      and stamp <= now + timedelta(minutes=5)
                      and projection.get('week') == snapshot['week']
                      and projection.get('source') == 'yahoo_fantasy_ui')
        except (KeyError, TypeError, ValueError, AttributeError):
            usable = False
        row["yahoo_projected_points"] = projection.get("projected_points") if usable else None
        row['projection_captured_at'] = projection.get('captured_at')
        row['projection_usable'] = usable
        row["projection_source"] = projection.get("source")
        # Recent estimates remain separately labeled; never masquerade as projections.
        estimate = estimates.get(player.get("player_key"), {})
        row["recent_estimate"] = estimate.get("projected_points")
        row["recent_estimate_sample_weeks"] = estimate.get("sample_weeks", [])
        row["recent_estimate_confidence"] = estimate.get("confidence") if estimate.get("projected_points") is not None else None
        return row
    return {
        "schema_version": 1,
        "verification": verification,
        "read_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "captured_at": snapshot.get("captured_at"),
        "team_key": snapshot.get("team_key"),
        "league_key": snapshot.get("league_key"),
        "week": snapshot.get("week"),
        "league": {k: snapshot.get("league_settings", {}).get(k) for k in
                   ("name", "season", "current_week", "scoring_type", "roster_positions",
                    "max_weekly_adds", "uses_faab", "waiver_type")},
        "acquisitions": snapshot.get("acquisitions", {}),
        "my_team": {"name": roster.get("name"), "faab_balance": roster.get("faab_balance"),
                    "players": [enrich(p) for p in roster.get("players", [])]},
        "available_players": [enrich(p) for p in candidates],
        "data_quality": snapshot.get("data_quality", {}),
        "recent_transactions": [{
            "type": t.get("type"), "status": t.get("status"), "timestamp": t.get("timestamp"),
            "faab_bid": t.get("faab_bid"), "players": [
                {"name": p.get("name"), "player_key": p.get("player_key"),
                 "transaction_data": p.get("transaction_data")} for p in t.get("players", [])]
        } for t in snapshot.get("transactions", [])[:40]],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = build_feed(json.loads(args.snapshot.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
                           encoding="utf-8")
    print(f"Prepared compact Yahoo feed: {args.output} ({len(data['available_players'])} available players)")


if __name__ == "__main__":
    main()
