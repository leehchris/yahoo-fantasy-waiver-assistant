# Local Setup and Yahoo OAuth

## Prerequisites

- Python 3.11+
- A Yahoo Developer application with Fantasy Sports - Read permission
- The application's Client ID and Client Secret

Yahoo's current OAuth documentation uses the authorization-code flow. The authorization endpoint is https://api.login.yahoo.com/oauth2/request_auth and the token endpoint is https://api.login.yahoo.com/oauth2/get_token.

The Fantasy API base URL is https://fantasysports.yahooapis.com/fantasy/v2.

## Install

Create and activate a virtual environment, then install:

    python -m venv .venv
    pip install -e ".[dev]"

Windows activation:

    .venv\Scripts\Activate.ps1

macOS/Linux activation:

    source .venv/bin/activate

## Configure credentials

Copy .env.example to .env and set:

    YAHOO_CLIENT_ID=<your client id>
    YAHOO_CLIENT_SECRET=<your client secret>
    YAHOO_REDIRECT_URI=https://localhost:8080/callback
    YAHOO_TOKEN_FILE=data/private/yahoo_tokens.json

Never commit .env or the token file.

## Authorize

After Yahoo confirms the replacement application's Fantasy Sports access:

    python -m yahoo_waiver_assistant auth

The command opens Yahoo's consent page and starts a temporary HTTPS callback server at localhost:8080. Yahoo requires HTTPS for local authorization. Flask uses a temporary self-signed development certificate, so the browser may display a local certificate warning.

After a successful callback, access and refresh tokens are stored in data/private/yahoo_tokens.json, which is excluded from Git.

Access tokens are refreshed automatically when they are near expiration.

## Discover the league and team

    python -m yahoo_waiver_assistant discover

The first live test should verify the returned team_key and league_key.

## Fetch data

    python -m yahoo_waiver_assistant roster TEAM_KEY
    python -m yahoo_waiver_assistant roster TEAM_KEY --week 4
    python -m yahoo_waiver_assistant available LEAGUE_KEY --status FA
    python -m yahoo_waiver_assistant available LEAGUE_KEY --status W
    python -m yahoo_waiver_assistant transactions LEAGUE_KEY

These commands intentionally return raw Yahoo JSON for now. The next implementation phase will normalize rosters, players, projections, and transactions into stable internal models after we capture real responses from the live league.

## Test

    pytest

The current tests do not require live Yahoo credentials.
