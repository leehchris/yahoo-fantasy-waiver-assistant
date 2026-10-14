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
