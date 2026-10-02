from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import requests
from requests.auth import HTTPBasicAuth

AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"


def build_authorization_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "language": "en-us",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def new_state() -> str:
    return secrets.token_urlsafe(32)


class TokenStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass


class YahooOAuth:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_store: TokenStore,
        session: requests.Session | None = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_store = token_store
        self.session = session or requests.Session()

    def exchange_code(self, code: str) -> dict:
        response = self.session.post(
            TOKEN_URL,
            auth=HTTPBasicAuth(self.client_id, self.client_secret),
            data={
                "redirect_uri": self.redirect_uri,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        response.raise_for_status()
        return self._save_token_response(response.json())

    def refresh(self, refresh_token: str) -> dict:
        response = self.session.post(
            TOKEN_URL,
            auth=HTTPBasicAuth(self.client_id, self.client_secret),
            data={
                "redirect_uri": self.redirect_uri,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        payload.setdefault("refresh_token", refresh_token)
        return self._save_token_response(payload)

    def access_token(self) -> str:
        tokens = self.token_store.load()
        if not tokens:
            raise RuntimeError(
                "No Yahoo tokens found. Run the auth command first."
            )

        if self._expires_soon(tokens):
            refresh_token = tokens.get("refresh_token")
            if not refresh_token:
                raise RuntimeError(
                    "Yahoo access token expired and no refresh token is stored. "
                    "Run the auth command again."
                )
            tokens = self.refresh(refresh_token)

        token = tokens.get("access_token")
        if not token:
            raise RuntimeError("Stored Yahoo token response has no access_token.")
        return token

    def _save_token_response(self, payload: dict) -> dict:
        saved = dict(payload)
        expires_in = int(saved.get("expires_in", 3600))
        now = int(time.time())
        saved["obtained_at"] = now
        saved["expires_at"] = now + expires_in
        self.token_store.save(saved)
        return saved

    @staticmethod
    def _expires_soon(tokens: dict, buffer_seconds: int = 120) -> bool:
        expires_at = int(tokens.get("expires_at", 0))
        return expires_at <= int(time.time()) + buffer_seconds
