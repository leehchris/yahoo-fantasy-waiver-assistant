from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import webbrowser
from urllib.parse import urlparse

from flask import Flask, request

from .client import YahooFantasyClient
from .config import Settings
from .oauth import TokenStore, YahooOAuth, build_authorization_url, new_state
from .yahoo_json import discovery_summary, normalize_roster, normalize_players, normalize_transactions
from .snapshot import create_snapshot, save_snapshot
from .report import build_report, latest_snapshot, save_report, render_report
from .planning import build_upcoming_plan, render_upcoming_plan
from .future_forecasts import attach_future_projections
from .plan_storage import save_plan
from .performance import import_history, history_path, build_performance, render_performance
from .refresh import refresh, render_bundle
from .output_storage import save_output


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
    _print_json(normalize_roster(client.roster(team_key, week=week)))


def available_command(
    league_key: str, status: str, start: int, count: int
) -> None:
    _, _, client = _services()
    _print_json(
        normalize_players(client.available_players(
            league_key, status=status, start=start, count=count
        ), status)
    )


def transactions_command(league_key: str) -> None:
    _, _, client = _services()
    _print_json(normalize_transactions(client.transactions(league_key)))


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

    snapshot = subparsers.add_parser("snapshot", help="Save a complete normalized private snapshot")
    snapshot.add_argument("--team-key", help="Defaults to YAHOO_TEAM_KEY or unique latest-season team")
    snapshot.add_argument("--week", type=int)

    snapshot.add_argument("--history-weeks", type=int, default=4, choices=range(9),
                          help="Completed prior weeks to fetch (default: 4)")
    snapshot.add_argument("--projections-file", type=Path,
                          help="Private JSON file of provider projections already scored for this league")
    report = subparsers.add_parser("report", help="Build a private waiver report from a captured snapshot")
    report.add_argument("--snapshot", type=Path, help="Defaults to the latest private snapshot")
    report.add_argument("--policy", type=Path, help="Optional private calibrated model inputs")
    report.add_argument("--limit", type=int, default=15)
    snapshot.add_argument("--lookahead", type=int, choices=range(5), default=2,
                          help="Upcoming weeks to load from Yahoo captures (default: 2)")
    plan = subparsers.add_parser("plan", help="Plan upcoming weeks from separate Yahoo weekly forecasts")
    plan.add_argument("--snapshot", type=Path)
    plan.add_argument("--lookahead", type=int, choices=range(1, 5), default=2)
    plan.add_argument("--limit", type=int, default=10)
    plan.add_argument("--max-moves", type=int, choices=range(6), default=3)
    refresh_parser = subparsers.add_parser('refresh', help='Refresh data and save one lineup, waiver, bye and season report')
    refresh_parser.add_argument('--team-key')
    refresh_parser.add_argument('--lookahead', type=int, choices=range(1, 5), default=2)
    refresh_parser.add_argument('--limit', type=int, default=10)
    refresh_parser.add_argument('--history-file', type=Path)
    refresh_parser.add_argument('--open', action='store_true', help='Open the saved report in your browser')
    performance = subparsers.add_parser('performance', help='Rebuild season performance offline from a refresh snapshot')
    performance.add_argument('--snapshot', type=Path)
    history = subparsers.add_parser('import-history', help='Import rendered historical Yahoo roster pages')
    history.add_argument('pages', type=Path)
    history.add_argument('--team-key', required=True)
    history.add_argument('--current-week', type=int, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == 'refresh':
        _, _, client = _services()
        print('Refreshing your league and building your complete report...')
        snapshot_path, bundle = refresh(client, args.team_key or os.getenv('YAHOO_TEAM_KEY'),
                                       lookahead=args.lookahead, limit=args.limit, history_file=args.history_file)
        markdown = render_bundle(bundle)
        path = save_output(bundle, markdown, 'fantasy-update')
        print(f'Saved private snapshot: {snapshot_path.resolve()}')
        print(f'Saved complete report: {path.with_suffix(".md").resolve()}')
        if args.open:
            from .report_html import render_html
            target = path.with_suffix('.html')
            content = render_html(markdown)
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            webbrowser.open(target.resolve().as_uri())
    elif args.command == 'performance':
        source = args.snapshot or latest_snapshot()
        snapshot = json.loads(source.read_text(encoding='utf-8-sig'))
        if 'season_history' not in snapshot:
            raise ValueError('This snapshot has no season history; run refresh first')
        report = build_performance(snapshot['season_history'], {p['player_key'] for p in snapshot['roster']['players']})
        path = save_output(report, render_performance(report), 'season-performance')
        print(f'Saved season report: {path.with_suffix(".md").resolve()}')
        print(render_performance(report))
    elif args.command == 'import-history':
        from .yahoo_json import league_key_from_team
        pages = json.loads(args.pages.read_text(encoding='utf-8-sig'))
        capture = import_history(pages, args.team_key, league_key_from_team(args.team_key), args.current_week)
        path = history_path(args.team_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Deliberate cache update; only this team's historical projection cache is replaced.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(capture, f, indent=2)
        print(f'Saved historical projection cache: {path.resolve()}')
    elif args.command == "auth":
        auth_command()
    elif args.command == "discover":
        discover_command()
    elif args.command == "roster":
        roster_command(args.team_key, args.week)
    elif args.command == "available":
        available_command(args.league_key, args.status, args.start, args.count)
    elif args.command == "snapshot":
        _, _, client = _services()
        projections_file = args.projections_file
        if projections_file is None and os.getenv("YAHOO_PROJECTIONS_FILE"):
            projections_file = Path(os.environ["YAHOO_PROJECTIONS_FILE"])
        print("Fetching league settings, current players, and recent weekly results...")
        payload = create_snapshot(client, args.team_key or os.getenv("YAHOO_TEAM_KEY"), args.week,
                                  history_weeks=args.history_weeks, projections_file=projections_file, lookahead=args.lookahead)
        print(f"Saved private snapshot: {save_snapshot(payload).resolve()}")
    elif args.command == "plan":
        source = args.snapshot or latest_snapshot()
        snapshot = json.loads(source.read_text(encoding="utf-8-sig"))
        snapshot = attach_future_projections(snapshot, args.lookahead)
        plan = build_upcoming_plan(snapshot, args.lookahead, args.limit, args.max_moves)
        path = save_plan(plan)
        print(f"Saved private upcoming-week plan: {path.with_suffix('.md').resolve()}")
        print(render_upcoming_plan(plan))
    elif args.command == "report":
        source = args.snapshot or latest_snapshot()
        snapshot = json.loads(source.read_text(encoding="utf-8-sig"))
        policy = json.loads(args.policy.read_text(encoding="utf-8-sig")) if args.policy else None
        report = build_report(snapshot, policy, limit=args.limit)
        print(f"Saved private waiver report: {save_report(report).resolve()}")
        print(render_report(report))
    elif args.command == "transactions":
        transactions_command(args.league_key)


if __name__ == "__main__":
    main()
