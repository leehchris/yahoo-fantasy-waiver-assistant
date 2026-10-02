from __future__ import annotations

import argparse
import json
import webbrowser
from urllib.parse import urlparse

from flask import Flask, request

from .client import YahooFantasyClient
from .config import Settings
from .oauth import TokenStore, YahooOAuth, build_authorization_url, new_state
from .yahoo_json import discovery_summary


def _services():
    settings = Settings.from_env()
    token_store = TokenStore(settings.token_file)
    oauth = YahooOAuth(
        settings.client_id,
        settings.client_secret,
        settings.redirect_uri,
        token_store,
    )
    client = YahooFantasyClient(oauth.access_token)
    return settings, oauth, client


def auth_command() -> None:
    settings, oauth, _ = _services()
    parsed = urlparse(settings.redirect_uri)
    if parsed.scheme != "https" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise RuntimeError(
            "The local auth helper expects an HTTPS localhost redirect URI."
        )

    expected_state = new_state()
    authorization_url = build_authorization_url(
        settings.client_id, settings.redirect_uri, expected_state
    )

    app = Flask(__name__)

    @app.get("/callback")
    def callback():
        if request.args.get("state") != expected_state:
            return "State mismatch. Authorization rejected.", 400
        if error := request.args.get("error"):
            return f"Yahoo authorization failed: {error}", 400

        code = request.args.get("code")
        if not code:
            return "Yahoo callback did not include an authorization code.", 400

        try:
            oauth.exchange_code(code)
        except Exception as exc:
            return f"Token exchange failed: {type(exc).__name__}. Check the terminal.", 500

        return (
            "Yahoo authorization succeeded. Tokens were stored locally. "
            "You can close this tab and stop the terminal server with Ctrl+C."
        )

    print("Opening Yahoo authorization in your browser...")
    print("If it does not open automatically, visit:")
    print(authorization_url)
    print()
    print(
        "Yahoo requires HTTPS for localhost. Your browser may warn about the "
        "temporary self-signed development certificate."
    )

    webbrowser.open(authorization_url)
    app.run(
        host=parsed.hostname or "localhost",
        port=parsed.port or 8080,
        ssl_context="adhoc",
        debug=False,
        use_reloader=False,
    )


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def discover_command() -> None:
    _, _, client = _services()
    payload = client.discover_nfl_teams()
    _print_json(discovery_summary(payload))


def roster_command(team_key: str, week: int | None) -> None:
    _, _, client = _services()
    _print_json(client.roster(team_key, week=week))


def available_command(
    league_key: str, status: str, start: int, count: int
) -> None:
    _, _, client = _services()
    _print_json(
        client.available_players(
            league_key, status=status, start=start, count=count
        )
    )


def transactions_command(league_key: str) -> None:
    _, _, client = _services()
    _print_json(client.transactions(league_key))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Yahoo Fantasy Football waiver assistant"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("auth", help="Authorize Yahoo and store tokens locally")
    subparsers.add_parser(
        "discover", help="Discover NFL team/league keys for the logged-in user"
    )

    roster = subparsers.add_parser("roster", help="Fetch a Yahoo team roster")
    roster.add_argument("team_key")
    roster.add_argument("--week", type=int)

    available = subparsers.add_parser(
        "available", help="Fetch free agents or players currently on waivers"
    )
    available.add_argument("league_key")
    available.add_argument("--status", choices=["FA", "W"], default="FA")
    available.add_argument("--start", type=int, default=0)
    available.add_argument("--count", type=int, default=25)

    transactions = subparsers.add_parser(
        "transactions", help="Fetch league transactions"
    )
    transactions.add_argument("league_key")

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "auth":
        auth_command()
    elif args.command == "discover":
        discover_command()
    elif args.command == "roster":
        roster_command(args.team_key, args.week)
    elif args.command == "available":
        available_command(args.league_key, args.status, args.start, args.count)
    elif args.command == "transactions":
        transactions_command(args.league_key)


if __name__ == "__main__":
    main()
