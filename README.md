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
team/league keys, scoring settings and roster slots, all league rosters and FAAB,
current player metadata, all waiver/free-agent pages, recent weekly results, forecasts,
and the transaction history returned by Yahoo. Credentials and raw API envelopes are excluded.
The file still contains private league information: share it only deliberately.
Git ignoring prevents commits; it is not encryption. On Windows, directory ACLs
control access; on POSIX the file is created with owner-only permissions.

Roster, available, and transactions commands now print normalized JSON. Missing
numeric fields are null; zero bids remain zero. Player injury status is separate
from availability (FA/W). Snapshot aborts on request or pagination errors before
writing a file. It does not submit claims, adds, drops, or trades.

Tests use sanitized fixtures derived from captured Yahoo payload shapes and mocked
clients; they require no live credentials. Run `python -m pytest`.

## Scoring, current players, and forecasts

Snapshot schema version 2 adds:

- `league_settings`: stat category IDs/names, scoring modifiers, complex bonus rules,
  roster positions, waiver rules, acquisition limits, and current scoring week.
- `league_rosters`: all team rosters, remaining FAAB, and weekly acquisition counts.
- `recent_results`: league-scored actual fantasy points and stat IDs/values for the
  prior four completed weeks, including carries, targets, and receptions when returned.
- `recent_estimates`: separate low-confidence recent-results diagnostics.
- `projections`: Yahoo/provider week-specific forecast values with source, timestamp, confidence,
  sample weeks, and limitations. Missing values remain null.
- `acquisitions`: the allowance for the requested week. A count from another week
  is not reused; unlimited limits are explicit.
- `data_quality`: forecast coverage and unavailable data. Player injury labels,
  bye weeks, and note timestamps refresh with each capture; note text and depth
  charts are not supplied by these endpoints.

The official [Yahoo API documentation](https://sports.yahoo.com/developer/docs/)
describes league settings and league-context player stats. Live projection-option
requests were rejected or returned only actual points during verification. We do
not relabel actuals as Yahoo projections. **Yahoo's league-scored projected points
shown in the fantasy app are the base.** The assistant reads the signed-in browser's
visible roster/available-player tables and saves a validated private forecast capture.
These use `source: yahoo_fantasy_ui`; the API and UI sources remain distinct.
Missing Yahoo projections stay null. Four-week weighted recent-results estimates
are retained separately in `recent_estimates` for comparison and carry Low confidence.
They do not replace the Yahoo baseline.

The snapshot command automatically looks for a fresh matching capture at
`data/private/yahoo-projections/GAME.l.LEAGUE-weekN.json`. This command alone does
not control the browser or fetch UI projections: an assistant refresh reads the
browser and updates that private file first. An expired or mismatched default
capture is withheld with a data-quality warning. You do not need to copy commands
or upload a file when the assistant has access to the local repo and signed-in browser.
See [the assistant refresh workflow](docs/refresh-workflow.md).

`--history-weeks 0` skips recent results; the default is 4, with a maximum of 8.
All roster/available players are fetched in batches of 25 for each history week.
This makes a full refresh slower than version 1. Each capture is a separate private
file; old snapshots are preserved. Never use a forecast created after a game as a
pregame projection for projection-surprise analysis.

### Provider projections

Set `YAHOO_PROJECTIONS_FILE=data/private/provider-projections.json` in `.env`, or
pass `snapshot --projections-file data/private/provider-projections.json`. The file
must contain points **already scored for the league**, not generic standard/PPR
points or raw statistical projections. Format (replace all example values):

```json
{
  "league_key": "999.l.123",
  "week": 6,
  "source": "Your projection provider",
  "generated_at": "2026-10-14T17:00:00Z",
  "players": [
    {"player_key": "999.p.1", "projected_points": 12.5}
  ]
}
```

The league/week must match; timestamps require a timezone and must be no more
than 48 hours old or five minutes in the future. Unknown/duplicate player keys and
nonfinite points are rejected. Valid zero points stay zero. Imported forecasts
replace the corresponding missing entries; uncovered players remain null. No provider account or paid service is configured automatically.

### Existing recommendation logic

`decision_inputs_from_snapshot` supplies current player names, matched-week
expected points, remaining FAAB, and the correct acquisition allowance to the
existing `DecisionInputs`/`recommend` engine. It validates available adds, on-roster
replacements, and undroppable flags. Recent-results estimates require explicit
opt-in and force Low confidence. The caller must still supply lineup probability,
market/clearance probability, bid economics, and candidate score. These inputs
are not fabricated from projections alone. This adapter does not optimize lineup
eligibility or validate every Yahoo roster rule, and it never executes transactions.
