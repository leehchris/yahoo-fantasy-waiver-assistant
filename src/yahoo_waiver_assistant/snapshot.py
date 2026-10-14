from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .yahoo_json import (discovery_summary, league_key_from_team,
                         normalize_players, normalize_roster, normalize_transactions)


def resolve_team(client, team_key: str | None = None) -> str:
    if team_key:
        league_key_from_team(team_key)
        return team_key
    keys = discovery_summary(client.discover_nfl_teams())["team_keys"]
    if not keys:
        raise ValueError("No teams discovered; provide --team-key")
    # NFL game keys increase each season; never silently choose between leagues.
    latest = max(int(key.split(".")[0]) for key in keys)
    current = [key for key in keys if int(key.split(".")[0]) == latest]
    if len(current) != 1:
        raise ValueError("Multiple teams in the latest season; provide --team-key")
    return current[0]


def available_all(client, league_key: str, status: str) -> list[dict]:
    result = []
    seen = set()
    start = 0
    while True:
        page = normalize_players(client.available_players(
            league_key, status=status, start=start, count=25), status)
        if not page:
            return result
        keys = [player["player_key"] for player in page]
        if any(not key or key in seen for key in keys) or len(set(keys)) != len(keys):
            raise ValueError("Yahoo returned duplicate or missing player keys during pagination")
        seen.update(keys)
        result.extend(page)
        start += len(page)


def create_snapshot(client, team_key: str | None = None, week: int | None = None) -> dict:
    team_key = resolve_team(client, team_key)
    league_key = league_key_from_team(team_key)
    return {"schema_version": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
            "team_key": team_key, "league_key": league_key,
            "roster": normalize_roster(client.roster(team_key, week=week)),
            "waivers": available_all(client, league_key, "W"),
            "free_agents": available_all(client, league_key, "FA"),
            "transactions": normalize_transactions(client.transactions(league_key))}


def save_snapshot(payload: dict, directory: Path = Path("data/private")) -> Path:
    """Write only after all requests succeed; create a unique file without overwriting."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (datetime.now(timezone.utc).strftime("snapshot-%Y%m%dT%H%M%SZ-")
                        + uuid4().hex[:8] + ".json")
    encoded = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(encoded)
    return path
