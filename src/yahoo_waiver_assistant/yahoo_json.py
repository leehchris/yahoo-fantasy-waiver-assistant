from __future__ import annotations

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
    seen: set[str] = set()
    result: list[str] = []
    for candidate in iter_key_values(value, key):
        if isinstance(candidate, (str, int, float)):
            text = str(candidate)
            if text not in seen:
                seen.add(text)
                result.append(text)
    return result


def discovery_summary(payload: dict) -> dict:
    return {
        "team_keys": unique_scalar_values(payload, "team_key"),
        "team_names": unique_scalar_values(payload, "name"),
        "league_keys": unique_scalar_values(payload, "league_key"),
        "game_keys": unique_scalar_values(payload, "game_key"),
    }
