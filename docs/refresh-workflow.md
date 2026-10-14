# Assistant refresh workflow

When asked to check this league, use the local repository and the user's signed-in
Yahoo Fantasy browser. The user should not need to paste commands or upload files.
All Yahoo actions in this project are read-only.

1. Read the snapshot/discovery context to identify the team, league, game, and
   current week. Read league scoring settings through the OAuth client.
2. Use the supported browser tools to read the visible roster table in that
   league. Refresh stale pages first and verify the displayed scoring week.
   The roster's **Proj Pts** column is the expected-points source. **Fan Pts**
   is actual scoring and must not be confused with it.
3. Open Players through the visible Yahoo link. Verify Status is **All Available
   Players** and Stats is **Week N (proj)** for the requested week. In this view,
   **Fan Pts** is projected scoring. Read all pages using the visible Next 25
   control, covering All Offense, K, and DEF. Never click Add, Drop, Start Active
   Players, waiver claims, or any transaction control.
4. Extract only rendered table content and visible player identifiers. Preserve
   header/cell order including hidden edit columns and colspans. Player-note IDs
   or visible player links identify Yahoo player IDs; match by ID, not by name.
   A blank/dash forecast is missing, not zero. A displayed 0.00 is a valid zero.
5. `parse_yahoo_projection_page` and `build_yahoo_projection_capture` validate
   DOM exports (`url`, `selected_stats`, tables containing caption, headers with
   text/colspan, rows with player_id and cells with text/colspan). They reject
   another league, another week, actual-points views, and conflicting duplicates.
6. Save the forecast capture privately at the path returned by
   `projection_capture_path(league_key, week)`. The capture contains league_key,
   week, source=`yahoo_fantasy_ui`, generated_at with timezone, and players with
   player_key/projected_points. No cookies, credentials, full page HTML, account
   profile data, or action/crumb URLs belong in the normalized capture.
7. Run the snapshot command directly from the repository. It automatically loads
   a fresh matching Yahoo capture, fetches current API data, and saves one private
   snapshot. Verify forecast IDs/coverage against current roster plus availability.
   If availability changed while capturing, refresh affected pages. Missing Yahoo
   values stay null; `recent_estimates` are separate diagnostics.
8. Use the existing decision engine with captured Yahoo points and explicit model
   inputs. Report missing market/lineup/opportunity inputs; do not manufacture
   probabilities or bid economics. Preserve capture times for future pregame
   projection-surprise analysis.

Browser access is assistant-assisted. The standalone Python CLI does not control
Chrome or retrieve projections by itself. If the browser connection or login is
unavailable, preserve scoring/current-player data and report missing forecasts.
Ask for login only when necessary; never ask for command-output copies or payload
uploads as the normal workflow. Do not extract browser cookies or bypass paywalls.

Private captures and snapshots are Git-ignored. Tests/fixtures must contain only
sanitized, synthetic identifiers and scoring choices.


After the verified snapshot, run `python -m yahoo_waiver_assistant report` directly
and read its private output. Lead with existing-roster lineup opportunities,
material add/drop differences, future bye shortages, and data gaps. Each candidate
row is an independent alternative. Research current news before promoting a
provisional scenario to advice. Do not treat observed winning bids as calibrated
clearance probabilities, and do not fill missing weighted features with guesses.


For upcoming-week requests, capture each future week separately using the Stats
selector (Week N (proj)). For the user roster, set All Players and the user's
Fantasy Teams filter and capture Offense, K, and DEF. For available candidates,
set No Team Selected, All Available Players, and capture QB/RB/WR/TE/K/DEF.
Check table header sort links match the selected period and filters before
reading rows; filter controls can update before the table finishes loading.
State whether the candidate pool is complete or a shortlist. Save each week to
its own projection_capture_path, refresh the snapshot, and run the plan command.
Do not infer a missing future forecast from today's points or an aggregate view.
Review both alternatives and the combined scenario; individual rows are not a
compatible set of transactions until recomputed together.

## One refresh and complete report

On Windows, double-click **Refresh My Team.cmd** in the repository folder. It
refreshes Yahoo's read-only API data, saves a snapshot and a combined private
report, and opens the report in your browser. The existing `.venv` and Yahoo
authorization must be set up first. Errors leave the window open for diagnosis.

Alternatively: `python -m yahoo_waiver_assistant refresh --open`.
Options: `--team-key`, `--lookahead 1..4`, `--limit`, `--history-file`.
The combined report includes the best current lineup, waiver alternatives,
upcoming-week scenarios and season performance. Files are uniquely named
`data/private/fantasy-update-*.json`, `.md`, and (with `--open`) `.html`.
Nothing submits Yahoo claims or roster changes.

Refresh updates API data, **not browser projections**. Current and future reports
reuse the existing week-specific Yahoo page captures, subject to their existing
freshness checks. Missing/stale forecasts require review, not fabricated values.

## Season performance

Refresh fetches each completed week's own roster and league-scored actual points,
including players since dropped. Team comparisons use the historical starters,
not today's lineup or bench totals. Player comparisons include bench games during
weeks on your roster; current players are identified separately in the JSON.

Historical Yahoo forecasts come from retained `Proj Pts` columns in signed-in
completed-week roster pages. The assistant can capture them through browser tools;
the CLI does not read browser cookies or automate login. Import rendered DOM
exports (same table/cell shape as the existing projection parser, plus `week` on
each page) using:

`python -m yahoo_waiver_assistant import-history PAGES.json --team-key GAME.l.LEAGUE.t.TEAM --current-week N`

This saves `data/private/yahoo-history/TEAM_KEY.json`, reused by refresh.
Import the complete desired history together: importing replaces that team's cache.
These are retrospective Yahoo forecasts, not proof of an independently archived
pregame forecast. Historical forecasts do not expire like upcoming projections.
Missing forecasts or actual points remain unknown; a season delta requires all
starter comparisons. Positive-projection non-reserve games qualify for player
comparisons; byes/zero projections are excluded from those player percentages.
Zero-point games show their contribution and the difference excluding zeros;
the tool cannot infer their injury/inactive causes from today's status.

Repeated shortfalls are flagged for review at >=3 comparable weeks, >=60% misses
and >=20% aggregate shortfall. This is a transparent screening rule, not a
statistical significance claim or an automatic drop recommendation.
Rebuild offline with `python -m yahoo_waiver_assistant performance --snapshot PATH`
using a snapshot created by refresh. All private outputs stay ignored by Git.
