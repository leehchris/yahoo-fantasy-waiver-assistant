from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    client_id: str
    client_secret: str
    redirect_uri: str
    token_file: Path

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        client_id = os.getenv("YAHOO_CLIENT_ID", "").strip()
        client_secret = os.getenv("YAHOO_CLIENT_SECRET", "").strip()
        redirect_uri = os.getenv(
            "YAHOO_REDIRECT_URI", "https://localhost:8080/callback"
        ).strip()
        token_file = Path(
            os.getenv("YAHOO_TOKEN_FILE", "data/private/yahoo_tokens.json")
        )

        missing = [
            name
            for name, value in (
                ("YAHOO_CLIENT_ID", client_id),
                ("YAHOO_CLIENT_SECRET", client_secret),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing required environment variable(s): " + ", ".join(missing)
            )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            token_file=token_file,
        )
