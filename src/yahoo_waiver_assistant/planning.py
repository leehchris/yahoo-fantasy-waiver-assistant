"""Rolling Yahoo-projection scenarios, with missing future data left unknown."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from .enrichment import number
from .lineups import RESERVE_SLOTS, optimize_lineup


def fresh_points(rows: list[dict], week: int, now: datetime) -> dict[str, float]:
    result = {}
    for row in rows:
        if row.get('week') != week or row.get('source') != 'yahoo_fantasy_ui':
            continue
        points = number(row.get('projected_points'))
        try:
            captured = datetime.fromisoformat(row['captured_at'].replace('Z', '+00:00'))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if points is None or captured.utcoffset() is None or now - captured > timedelta(hours=48) or captured - now > timedelta(minutes=5):
            continue
        key = row['player_key']
        if key in result and result[key] != points:
            raise ValueError('Conflicting projections for the same player/week')
        result[key] = points
    return result


def _fit(roster: list[dict], points: dict, settings: dict, week: int, future: bool) -> dict:
    # Future Yahoo projections, not today's O/Q flag, describe the projected
    # scoring scenario. IR slots stay excluded; actual health remains uncertain.
    players = [{**p, 'status': None} for p in roster] if future else roster
    fit = optimize_lineup(players, points, settings, bye_week=week)
    return fit


def _missing(roster: list[dict], points: dict, week: int) -> list[str]:
    return [p['player_key'] for p in roster if p.get('selected_position') not in RESERVE_SLOTS
            and p.get('bye_week') != week and p['player_key'] not in points]


def _comparisons(snapshot: dict, roster: list[dict], candidates: list[dict], point_maps: dict,
                 weeks: list[int], baselines: dict, *, protected: set[str] | None = None) -> list[dict]:
    settings = snapshot['league_settings']
    protected = protected or set()
    active_count = sum(p.get('selected_position') not in RESERVE_SLOTS for p in roster)
    capacity = sum(p['count'] for p in settings['roster_positions'] if p['position'] not in RESERVE_SLOTS)
    drops = [None] if active_count < capacity else [p for p in roster
             if not p.get('is_undroppable') and p.get('selected_position') not in RESERVE_SLOTS
             and p['player_key'] not in protected]
    result = []
    for candidate in candidates:
        key = candidate['player_key']
        # A player on bye can be evaluated with a known zero. Missing forecasts
        # for a playing week are not replaced with this week's projection.
        if any(candidate.get('bye_week') != week and key not in point_maps[week] for week in weeks):
            continue
        upper_fits = {week: _fit(roster + [candidate], point_maps[week], settings, week,
                                week != snapshot['week']) for week in weeks}
        if not any(upper_fits[week]['projected_points'] - baselines[week]['projected_points'] >= 1.5
                   or (upper_fits[week]['filled_slots'] > baselines[week]['filled_slots'] and
                       upper_fits[week]['projected_points'] > baselines[week]['projected_points'])
                   for week in weeks):
            continue
        options = []
        for drop in drops:
            changed = [p for p in roster if drop is None or p['player_key'] != drop['player_key']] + [candidate]
            comparisons = []
            worsens = False
            for week in weeks:
                before = baselines[week]
                after = _fit(changed, point_maps[week], settings, week, week != snapshot['week'])
                missing = _missing(changed, point_maps[week], week)
                if any(after['unfilled'].get(slot, 0) > count for slot, count in before['unfilled'].items()) or any(
                        count > before['unfilled'].get(slot, 0) for slot, count in after['unfilled'].items()):
                    worsens = True
                comparisons.append({'week': week, 'before_points': before['projected_points'],
                                    'after_points': after['projected_points'],
                                    'projected_gain': round(after['projected_points'] - before['projected_points'], 2),
                                    'before_unfilled': before['unfilled'], 'after_unfilled': after['unfilled'],
                                    'filled_slots_gained': after['filled_slots'] - before['filled_slots'],
                                    'missing_player_forecasts': missing})
            gain = round(sum(row['projected_gain'] for row in comparisons), 2)
            slots_gained = sum(row['filled_slots_gained'] for row in comparisons)
            current_loss = comparisons[0]['projected_gain'] < -1.5
            drop_value = sum(point_maps[w].get(drop['player_key'], 0) for w in weeks) if drop else 0
            options.append((not worsens, gain, slots_gained, -drop_value, drop, comparisons, current_loss))
        if not options:
            continue
        best = max(options, key=lambda row: row[:4])
        safe, gain, slots_gained, _, drop, comparisons, current_loss = best
        if not any(row['projected_gain'] >= 1.5 or (row['filled_slots_gained'] > 0 and row['projected_gain'] > 0)
                   for row in comparisons):
            continue
        uncertainty = not safe or current_loss or any(row['missing_player_forecasts'] for row in comparisons)
        result.append({'add_key': key, 'add_player': candidate['name'],
                       'replace_key': drop['player_key'] if drop else None,
                       'replace_player': drop['name'] if drop else 'Open Spot',
                       'availability_now': candidate['availability'],
                       'projected_horizon_gain': gain, 'filled_slots_gained': slots_gained,
                       'weekly_comparisons': comparisons,
                       'first_benefit_week': next((r['week'] for r in comparisons if r['projected_gain'] >= 1.5
                                                   or (r['filled_slots_gained'] > 0 and r['projected_gain'] > 0)), None),
                       'review_required': uncertainty or candidate['availability'] == 'W',
                       'reason': 'Yahoo-projected lineup value across the captured window; a waiver bid or roster tradeoff may require review.',
                       'confidence': 'Low',
                       'acquisition_status': 'PLAN FREE-AGENT PICKUP' if candidate['availability'] == 'FA' and not uncertainty else 'REVIEW',
                       'bid': 0 if candidate['availability'] == 'FA' else None})
    return sorted(result, key=lambda row: (not row['review_required'], row['projected_horizon_gain'],
                                          row['filled_slots_gained']), reverse=True)


def build_upcoming_plan(snapshot: dict, lookahead: int = 2, limit: int = 10,
                         max_moves: int = 3, as_of: datetime | None = None) -> dict:
    if snapshot.get('schema_version') != 2 or not 1 <= lookahead <= 4 or limit < 1 or not 0 <= max_moves <= 5:
        raise ValueError('Use schema 2, lookahead 1-4, a positive limit, and max_moves 0-5')
    now = as_of or datetime.now(timezone.utc)
    captured = datetime.fromisoformat(snapshot['captured_at'].replace('Z', '+00:00'))
    if captured.utcoffset() is None or now - captured > timedelta(hours=48) or captured - now > timedelta(minutes=5):
        raise ValueError('Refresh stale or invalid league data before planning')
    current = snapshot['week']
    league_week = snapshot['league_settings'].get('current_week')
    if league_week is not None and current != league_week:
        raise ValueError('Upcoming planning must start from the current league week')
    weeks = list(range(current, min(current + lookahead, snapshot['league_settings'].get('end_week') or 18) + 1))
    rows = snapshot['projections'] + snapshot.get('future_projections', [])
    point_maps = {week: fresh_points(rows, week, now) for week in weeks}
    roster = snapshot['roster']['players']
    candidates = snapshot['waivers'] + snapshot['free_agents']
    keys = [p['player_key'] for p in roster + candidates]
    if len(keys) != len(set(keys)):
        raise ValueError('Roster/availability must contain unique player keys')
    coverage = []
    baselines = {}
    evaluated_weeks = []
    for week in weeks:
        points = point_maps[week]
        missing = _missing(roster, points, week)
        fit = _fit(roster, points, snapshot['league_settings'], week, week != current)
        baselines[week] = fit
        available_known = sum(p['player_key'] in points or p.get('bye_week') == week for p in candidates)
        coverage.append({'week': week, 'baseline_points': fit['projected_points'] if not missing else None,
                         'unfilled_slots': fit['unfilled'], 'missing_roster_forecasts': missing,
                         'candidate_forecasts_available': available_known,
                         'available_players': len(candidates), 'candidate_pool_complete': available_known == len(candidates),
                         'players_on_bye': [p['name'] for p in roster if p.get('bye_week') == week]})
        if not missing:
            evaluated_weeks.append(week)
    comparisons = []
    scenario = []
    remaining = snapshot['acquisitions'].get('remaining')
    allowance_known = remaining is not None or snapshot['acquisitions'].get('unlimited', False)
    if current in evaluated_weeks and len(evaluated_weeks) > 1:
        comparisons = _comparisons(snapshot, roster, candidates, point_maps, evaluated_weeks, baselines)
        # Greedy, explicitly non-global scenario. Recompute after each free-agent
        # move so two players do not get credit for filling the same hole.
        full_window = evaluated_weeks == weeks
        if not full_window:
            for row in comparisons:
                row.update(review_required=True, acquisition_status='REVIEW',
                           reason='Only part of the requested window has roster forecasts; review missing weeks before proposing moves.')
        allowed_moves = (max_moves if snapshot['acquisitions'].get('unlimited') else min(max_moves, remaining or 0)) if full_window else 0
        working_roster = list(roster)
        remaining_candidates = [p for p in candidates if p['availability'] == 'FA']
        protected = set()
        for step in range(allowed_moves):
            current_baselines = {w: _fit(working_roster, point_maps[w], snapshot['league_settings'], w, w != current)
                                 for w in evaluated_weeks}
            ranked = _comparisons(snapshot, working_roster, remaining_candidates, point_maps,
                                   evaluated_weeks, current_baselines, protected=protected)
            ranked = [r for r in ranked if not r['review_required']]
            if not ranked:
                break
            chosen = ranked[0]
            candidate = next(p for p in remaining_candidates if p['player_key'] == chosen['add_key'])
            working_roster = [p for p in working_roster if p['player_key'] != chosen['replace_key']] + [candidate]
            remaining_candidates = [p for p in remaining_candidates if p['player_key'] != chosen['add_key']]
            protected.add(chosen['add_key'])
            scenario.append({'step': step + 1, **chosen})
    total_gain = round(sum(row['projected_horizon_gain'] for row in scenario), 2)
    return {'plan_version': 1, 'generated_at': now.isoformat(), 'snapshot_captured_at': snapshot['captured_at'],
            'week': current, 'team_key': snapshot['team_key'], 'requested_weeks': weeks,
            'evaluated_weeks': evaluated_weeks, 'coverage': coverage,
            'alternatives': comparisons[:limit], 'free_agent_scenario': scenario,
            'scenario_horizon_gain': total_gain, 'weekly_acquisitions_remaining': remaining,
            'acquisition_allowance_known': allowance_known,
            'full_window_evaluated': evaluated_weeks == weeks,
            'limitations': ['Candidate rankings cover captured future forecasts; unobserved candidates are not ranked as zero.',
                            'Equal weights across weeks; this is near-term planning, not a season/playoff value model.',
                            'Free-agent scenario is greedy and conditional on availability, not a globally optimal transaction plan.',
                            'All scenario acquisitions are modeled now using this week\'s remaining allowance; future resets are not assumed.',
                            'Current IR placement stays fixed. Future Yahoo forecasts do not guarantee injury recovery.',
                            'Yahoo game locks, positional maximums, verified news, and transaction feasibility need review.',
                            'Waiver bids remain REVIEW; no Yahoo transaction or roster change is executed.']}


def render_upcoming_plan(plan: dict) -> str:
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    lines = ['# Upcoming-week plan', '', 'Provisional Yahoo-projection scenarios. No Yahoo roster changes have been made.', '',
             f"Requested weeks: {', '.join(map(str, plan['requested_weeks']))}. "
             f"Evaluated weeks: {', '.join(map(str, plan['evaluated_weeks'])) or 'None'}.", '',
             '## Week-by-week needs', '', '| Week | Existing-roster projection | Unfilled slots | Candidate coverage: forecasts + known byes |',
             '|---|---:|---|---|']
    for row in plan['coverage']:
        points = f"{row['baseline_points']:.2f}" if row['baseline_points'] is not None else 'Missing forecasts'
        holes = ', '.join(f'{k}: {v}' for k, v in row['unfilled_slots'].items()) or 'None'
        lines.append(f"| {row['week']} | {points} | {holes} | {row['candidate_forecasts_available']}/{row['available_players']} |")
    if not plan['full_window_evaluated']:
        lines += ['', '**Incomplete window:** missing roster forecasts require review; no combined acquisition scenario is proposed.']
    lines += ['', '## Independent alternatives', '', '| Add | Replace | Benefit starts | Window gain | Status |', '|---|---|---:|---:|---|']
    for row in plan['alternatives']:
        lines.append(f"| {cell(row['add_player'])} | {cell(row['replace_player'])} | {row['first_benefit_week']} | "
                     f"{row['projected_horizon_gain']:+.2f} | {row['acquisition_status']} |")
    if not plan['alternatives']:
        lines.append('| No supported alternatives yet | — | — | — | Review forecast coverage |')
    lines += ['', '## Combined free-agent scenario', '']
    if not plan['free_agent_scenario']:
        lines.append('No supported combined scenario; review forecast coverage and acquisition allowance.')
    for row in plan['free_agent_scenario']:
        lines.append(f"{row['step']}. Add **{cell(row['add_player'])}**, replace **{cell(row['replace_player'])}**. "
                     f"Incremental window gain: **{row['projected_horizon_gain']:+.2f}**; bid: $0.")
    if plan['free_agent_scenario']:
        lines += ['', f"Scenario window gain: **{plan['scenario_horizon_gain']:+.2f}** projected points. "
                  'The scenario recomputes each move and does not reuse a dropped player.']
    lines += ['', '## Limits', ''] + [f'- {text}' for text in plan['limitations']]
    return '\n'.join(lines) + '\n'
