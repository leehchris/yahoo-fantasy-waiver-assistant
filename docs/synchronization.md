# Read-only synchronization

Run from the repository root with the existing private `.env` and Yahoo token file:

    .venv\Scripts\python.exe -m yahoo_waiver_assistant.sync

The Python module refreshes Yahoo data, verifies the current scoring week, team,
nonempty roster, unique IDs and complete FA/W pagination, then publishes all files
in one non-forced commit to the confirmed private `leehchris/yahoo-fantasy-private-data`
repository. No local data checkout or Git staging is needed. An expired or future
snapshot is rejected. Snapshot capture time, not report generation time, determines age.
The publish limit is 24 hours. Consumers must independently check age when reading.
Yahoo forecasts expire independently after 48 hours; unavailable forecasts stay null.
API synchronization does not refresh the browser forecasts. News still needs review.

Use `--expected-week 8` to require a particular week for a one-time check. Do not
pin a week in the recurring task. `--team-key` selects among multiple teams.

The private feed includes a verification summary. `yahoo/sync-status.json` records
the last successful publication. A failed run exits nonzero and records failure in
the local ignored `data/private/sync-status.json`; it cannot mark old remote data
as current. Remote consumers must compare `captured_at` with their own clock and
verify current week; a historical `verified` status is not proof of current freshness.
`latest-report.json` now contains the waiver/lineup report (`report_version: 1`).
The local refresh command continues to produce the full season/future report bundle.

## Activate on Windows

1. Authenticate GitHub CLI if `gh auth status` fails: `gh auth login -h github.com`.
2. Run `python -m yahoo_waiver_assistant discover` with the project virtual environment.
   Renew Yahoo consent with `auth` only if Yahoo rejects the refresh token.
3. Run the synchronization module above and verify its successful exit.
4. Run `scripts\schedule-tuesday-sync.ps1` in normal Windows PowerShell.

The schedule is daily 7 AM and Tuesday 10 PM Pacific, with daylight saving handled
by Windows. Windows timezone must be Pacific. It runs only while the current user
is signed in; wake timers depend on the machine's power settings. It retries twice
at ten-minute intervals, starts missed tasks when possible and prevents overlapping
instances. Check `Get-ScheduledTask -TaskName 'Yahoo Fantasy Private Sync - Tuesday'`
and `Get-ScheduledTaskInfo` for actual registration and run results. Authentication
and local file permissions are not portable to a GitHub-hosted runner. Never put
Yahoo credentials or tokens in Git commits, issue comments, chat or public artifacts.

Yahoo transactions remain read-only: Fantasy API calls use GET. The only Yahoo
POST is the existing OAuth token exchange/refresh. No add/drop/trade API exists here.
