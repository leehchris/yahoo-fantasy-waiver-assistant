from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any


def iter_key_values(value: Any, key: str) -> Iterator[Any]:
    if isinstance(value, dict):
        for current_key, current_value in value.items():
            if current_key == key:
                yield current_value
            yield from iter_key_values(current_value, key)
    elif isinstance(value, list):
        for item in value:
            yield from iter_key_values(item, key)


def unique_scalar_values(value: Any, key: str) -> list[str]:
    return list(dict.fromkeys(str(v) for v in iter_key_values(value, key)
                             if isinstance(v, (str, int, float))))


def fields(value: Any) -> dict:
    """Merge only an entity's list fragments, never its nested child entities."""
    if isinstance(value, dict):
        return value
    result = {}
    if isinstance(value, list):
        for item in value:
            result.update(fields(item))
    return result


def integer(value: Any) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return None


def league_key_from_team(team_key: str) -> str:
    match = re.fullmatch(r"([\w]+\.l\.\d+)\.t\.\d+", team_key)
    if not match:
        raise ValueError("Expected a Yahoo team key such as GAME.l.LEAGUE.t.TEAM")
    return match.group(1)


def discovery_summary(payload: dict) -> dict:
    teams = [fields(v) for v in iter_key_values(payload, "team")]
    teams = [t for t in teams if isinstance(t.get("team_key"), str)]
    keys = list(dict.fromkeys(t["team_key"] for t in teams))
    leagues = unique_scalar_values(payload, "league_key")
    for key in keys:
        try:
            league = league_key_from_team(key)
        except ValueError:
            continue
        if league not in leagues:
            leagues.append(league)
    return {"team_keys": keys, "team_names": list(dict.fromkeys(
        t["name"] for t in teams if isinstance(t.get("name"), str))),
        "league_keys": leagues, "game_keys": unique_scalar_values(payload, "game_key")}


def normalize_player(value: Any, availability: str | None = None) -> dict:
    data = fields(value)
    selected = fields(data.get("selected_position"))
    name = data.get("name", {})
    result = {key: data.get(key) for key in (
        "player_key", "player_id", "display_position", "primary_position",
        "position_type", "status", "status_full", "injury_note")}
    result['player_notes_last_timestamp'] = integer(data.get('player_notes_last_timestamp'))
    result['has_player_notes'] = str(data.get('has_player_notes')).lower() in {'1', 'true'}
    result.update(name=name.get("full") if isinstance(name, dict) else name,
                  team=data.get("editorial_team_abbr"),
                  eligible_positions=unique_scalar_values(data.get("eligible_positions"), "position"),
                  bye_week=integer(fields(data.get("bye_weeks")).get("week")),
                  selected_position=selected.get("position"),
                  week=integer(selected.get("week")), availability=availability,
                  is_undroppable=(str(data["is_undroppable"]) == "1")
                  if "is_undroppable" in data else None)
    return result


def normalize_players(payload: Any, availability: str | None = None) -> list[dict]:
    return [normalize_player(v, availability) for v in iter_key_values(payload, "player")]


def normalize_roster(payload: dict) -> dict:
    team = fields(next(iter_key_values(payload, "team"), {}))
    roster = fields(team.get("roster"))
    adds = fields(team.get("roster_adds"))
    return {"team_key": team.get("team_key"), "name": team.get("name"),
            "faab_balance": integer(team.get("faab_balance")),
            "waiver_priority": integer(team.get("waiver_priority")),
            "number_of_moves": integer(team.get("number_of_moves")),
            "roster_adds": {"coverage_type": adds.get("coverage_type"),
                            "coverage_value": integer(adds.get("coverage_value")),
                            "value": integer(adds.get("value"))},
            "coverage_type": roster.get("coverage_type"),
            "week": integer(roster.get("week")),
            "players": normalize_players(roster)}


def normalize_transactions(payload: dict) -> list[dict]:
    result = []
    for value in iter_key_values(payload, "transaction"):
        data = fields(value)
        row = {key: data.get(key) for key in (
            "transaction_key", "transaction_id", "type", "status")}
        row.update(timestamp=integer(data.get("timestamp")),
                   faab_bid=integer(data.get("faab_bid")), players=[])
        for player in iter_key_values(data.get("players"), "player"):
            normalized = normalize_player(player)
            movement = fields(fields(player).get("transaction_data"))
            normalized["transaction_data"] = {key: movement.get(key) for key in (
                "type", "source_type", "destination_type", "source_team_key",
                "source_team_name", "destination_team_key", "destination_team_name")}
            row["players"].append(normalized)
        result.append(row)
    return result
