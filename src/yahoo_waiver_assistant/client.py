from __future__ import annotations

from typing import Any

import requests

FANTASY_BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"


class YahooFantasyClient:
    def __init__(
        self,
        access_token_provider,
        session: requests.Session | None = None,
    ):
        self._access_token_provider = access_token_provider
        self.session = session or requests.Session()

    def get(self, resource: str, **params: Any) -> dict:
        resource = resource.lstrip("/")
        query = {"format": "json", **params}
        response = self.session.get(
            f"{FANTASY_BASE_URL}/{resource}",
            headers={"Authorization": f"Bearer {self._access_token_provider()}"},
            params=query,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def discover_nfl_teams(self) -> dict:
        return self.get("users;use_login=1/games;game_codes=nfl/teams")

    def team(self, team_key: str) -> dict:
        return self.get(f"team/{team_key}")

    def roster(self, team_key: str, week: int | None = None) -> dict:
        resource = f"team/{team_key}/roster"
        if week is not None:
            resource += f";week={week}"
        return self.get(resource)

    def league(self, league_key: str) -> dict:
        return self.get(f"league/{league_key}")

    def available_players(
        self,
        league_key: str,
        status: str = "FA",
        start: int = 0,
        count: int = 25,
    ) -> dict:
        status = status.upper()
        if status not in {"FA", "W"}:
            raise ValueError("status must be FA (free agent) or W (waivers)")
        resource = (
            f"league/{league_key}/players;status={status};start={start};count={count}"
        )
        return self.get(resource)

    def transactions(self, league_key: str) -> dict:
        return self.get(f"league/{league_key}/transactions")
