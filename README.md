# Yahoo Fantasy Waiver Assistant

Personal, non-commercial fantasy football analytics project for a single private league.

The assistant uses read-only Yahoo Fantasy Sports data to monitor roster changes, player availability, projections, transactions, FAAB activity, and waiver opportunities. It produces recommendations for one user; it does not execute Yahoo transactions.

## Current status

- Waiver decision framework documented
- Data requirements documented
- Yahoo OAuth 2.0 scaffolding implemented
- Read-only Fantasy Sports client implemented
- Live Yahoo response normalization for rosters, free agents, waivers, and transactions
- League discovery derives league keys from team keys
- One-command private snapshots with complete available-player pagination

## Core workflow

1. Discover waiver and free-agent candidates.
2. Estimate each player's fantasy value and uncertainty.
3. Compare each candidate with the exact roster player they would replace.
4. Estimate waiver demand, likely FAAB price, and the chance the player clears to free agency.
5. Recommend CLAIM, VALUE CLAIM, WAIT FOR FREE AGENCY, or PASS.
6. Re-scan after waivers for useful players dropped by other managers.

Every recommendation should identify Add, Replace/open roster spot, Action, Bid, Maximum bid, Expected lineup improvement, Free-agency probability, Confidence, and a short rationale.

## Local setup

See docs/setup.md.

Quick start:

    python -m venv .venv
    pip install -e ".[dev]"
    copy .env.example .env
    python -m yahoo_waiver_assistant auth
    python -m yahoo_waiver_assistant discover

See docs/waiver-strategy.md for the decision framework and docs/data-requirements.md for required inputs.

## Security

OAuth secrets, access tokens, refresh tokens, private league data, and local caches must never be committed. Use environment variables and local ignored files.

## Private snapshots

    python -m yahoo_waiver_assistant snapshot

This selects the unique team in the latest discovered NFL season. Set `YAHOO_TEAM_KEY`
in `.env` or use `snapshot --team-key GAME.l.LEAGUE.t.TEAM` to select explicitly.
Ambiguous discovery requires explicit selection. `--week` selects the roster week.

Run from the repository root. One uniquely named UTF-8 JSON file is saved under
`data/private/`, ignored by Git. It contains a versioned schema, UTC capture time,
team/league keys, roster metadata and players, all waiver/free-agent pages, and the
transaction history returned by Yahoo. Credentials and raw API envelopes are excluded.
The file still contains private league information: share it only deliberately.
Git ignoring prevents commits; it is not encryption. On Windows, directory ACLs
control access; on POSIX the file is created with owner-only permissions.

Roster, available, and transactions commands now print normalized JSON. Missing
numeric fields are null; zero bids remain zero. Player injury status is separate
from availability (FA/W). Snapshot aborts on request or pagination errors before
writing a file. It does not submit claims, adds, drops, or trades.

Tests use sanitized fixtures derived from captured Yahoo payload shapes and mocked
clients; they require no live credentials. Run `python -m pytest`.
