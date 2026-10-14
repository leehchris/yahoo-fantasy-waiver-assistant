"""Turn captured Yahoo data into auditable, provisional roster decisions."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

from .decision import Action, DecisionInputs, recommend
from .enrichment import number
from .lineups import RESERVE_SLOTS, bye_coverage, optimize_lineup
from .market import opponent_context, positional_bid_history
from .scoring import CandidateFeatures, WEIGHTS, score_candidate


def workload_summary(player: dict, results: list[dict]) -> dict:
    rows = sorted([r for r in results if r['player_key'] == player['player_key']], key=lambda r: r['week'])
    series = []
    for row in rows:
        stats = row.get('stats', {})
        series.append({'week': row['week'], 'actual_points': row.get('actual_points'),
                       'carries': stats.get('8'), 'targets': stats.get('78'), 'receptions': stats.get('11')})
    usable = [r for r in series if r['week'] != player.get('bye_week')
              and r['carries'] is not None and r['targets'] is not None]
    trend = None
    if len(usable) >= 4:
        early = sum(r['carries'] + r['targets'] for r in usable[-4:-2]) / 2
        recent = sum(r['carries'] + r['targets'] for r in usable[-2:]) / 2
        trend = {'early_average': round(early, 2), 'recent_average': round(recent, 2),
                 'change': round(recent - early, 2),
                 'method': 'Carries plus targets; latest two non-bye weeks versus prior two.'}
    return {'weeks': series, 'opportunity_trend': trend,
            'limitations': ['Targets and carries are opportunity proxies; routes, snaps, and role news are absent.']}


def validate_policy(policy: dict | None, known_keys: set[str]) -> dict:
    policy = policy or {}
    allowed = {'clearance_probabilities', 'bid_ceilings', 'winning_bid_estimates', 'feature_scores',
               'upside_stash_scores', 'news_overrides'}
    if not isinstance(policy, dict) or set(policy) - allowed:
        raise ValueError('Unknown report policy field')
    policy = {field: dict(mapping) if isinstance(mapping, dict) else mapping
              for field, mapping in policy.items()}
    for field, mapping in policy.items():
        if not isinstance(mapping, dict) or set(mapping) - known_keys:
            raise ValueError('Policy fields must map known player keys to values')
        for key, value in mapping.items():
            if field == 'news_overrides':
                if not isinstance(value, bool):
                    raise ValueError('News overrides must be booleans')
            elif field == 'feature_scores':
                if not isinstance(value, dict) or set(value) - set(WEIGHTS):
                    raise ValueError('Unknown weighted-score feature')
                if any(number(v) is None or not 0 <= number(v) <= 100 for v in value.values()):
                    raise ValueError('Feature scores must be between 0 and 100')
                mapping[key] = {k: number(v) for k, v in value.items()}
            else:
                numeric = number(value)
                ceiling = 1 if field == 'clearance_probabilities' else 100 if field == 'upside_stash_scores' else None
                if numeric is None or numeric < 0 or ceiling is not None and numeric > ceiling:
                    raise ValueError('Invalid policy value')
                if field in {'bid_ceilings', 'winning_bid_estimates'} and not numeric.is_integer():
                    raise ValueError('FAAB bids must be whole dollars')
                mapping[key] = int(numeric) if field in {'bid_ceilings', 'winning_bid_estimates'} else numeric
    return policy


def feature_context(player: dict, candidates: list[dict], points: dict, workload: dict,
                    policy: dict) -> dict:
    peers = [p for p in candidates if p.get('display_position') == player.get('display_position')]
    values = sorted(points[p['player_key']] for p in peers)
    score = 100 * sum(v <= points[player['player_key']] for v in values) / len(values)
    observed = {'expected_points': round(score, 2)}
    trend = workload['opportunity_trend']
    if trend:
        # An explicit initial heuristic, kept visible and separate from calibrated models.
        observed['opportunity_trend'] = round(max(0, min(100, 50 + 5 * trend['change'])), 2)
    observed.update(policy.get('feature_scores', {}).get(player['player_key'], {}))
    missing = [key for key in WEIGHTS if key not in observed]
    complete_score = None
    if not missing:
        features = CandidateFeatures(player['name'], player.get('display_position', ''),
                                     **observed, sample_games=len(workload['weeks']))
        complete_score = score_candidate(features).score
    return {'observed_features': observed, 'missing_features': missing, 'candidate_score': complete_score,
            'covered_weight': round(sum(WEIGHTS[k] for k in observed), 2),
            'method': 'Projection percentile within currently available positional peers; '
                      'opportunity score is clamp(50 + 5 * carries/targets change). '
                      'Missing weights are neither zero-filled nor reweighted.'}


def current_lineup(players: list[dict], points: dict) -> dict:
    active = [p for p in players if p.get('selected_position') not in RESERVE_SLOTS | {'BN'}]
    known = [p for p in active if p['player_key'] in points]
    return {'projected_points': round(sum(points[p['player_key']] for p in known), 2),
            'complete_projection_coverage': len(known) == len(active),
            'assignments': [{'player_key': p['player_key'], 'slot': p.get('selected_position')} for p in active]}


def build_report(snapshot: dict, policy: dict | None = None, limit: int = 15,
                 as_of: datetime | None = None) -> dict:
    if snapshot.get('schema_version') != 2:
        raise ValueError('Refresh to snapshot schema version 2')
    if limit < 1:
        raise ValueError('Report limit must be positive')
    now = as_of or datetime.now(timezone.utc)
    captured = datetime.fromisoformat(snapshot['captured_at'].replace('Z', '+00:00'))
    stale = now - captured > timedelta(hours=48) or captured > now + timedelta(minutes=5)
    roster = snapshot['roster']['players']
    available = snapshot['waivers'] + snapshot['free_agents']
    all_keys = {p['player_key'] for p in roster + available}
    if len(all_keys) != len(roster + available):
        raise ValueError('Roster and availability contain duplicate or overlapping players')
    policy = validate_policy(policy, all_keys)
    points = {}
    projection_stale = set()
    for row in snapshot['projections']:
        if row.get('week') != snapshot['week'] or row.get('source') != 'yahoo_fantasy_ui':
            continue
        value = number(row.get('projected_points'))
        if value is not None:
            try:
                stamp = datetime.fromisoformat(row['captured_at'].replace('Z', '+00:00'))
            except (KeyError, TypeError, ValueError, AttributeError):
                projection_stale.add(row['player_key'])
                continue
            if stamp.utcoffset() is None or now - stamp > timedelta(hours=48) or stamp > now + timedelta(minutes=5):
                projection_stale.add(row['player_key'])
            else:
                points[row['player_key']] = value
    settings = snapshot['league_settings']
    baseline = optimize_lineup(roster, points, settings)
    selected = current_lineup(roster, points)
    missing_roster = [p['name'] for p in roster if p.get('selected_position') not in RESERVE_SLOTS
                      and p['player_key'] not in points]
    coverage = bye_coverage(roster, settings, snapshot['week'])
    base_future_holes = sum(sum(row['unfilled_slots'].values()) for row in coverage)
    capacity = sum(row['count'] for row in settings['roster_positions'] if row['position'] not in RESERVE_SLOTS)
    active_count = sum(p.get('selected_position') not in RESERVE_SLOTS for p in roster)
    open_spot = active_count < capacity
    explicit = set().union(*(set(values) for values in policy.values())) if policy else set()
    candidates = [p for p in available if p['player_key'] in points
                  and (points[p['player_key']] > 0 or p['player_key'] in explicit)]
    candidates.sort(key=lambda p: points[p['player_key']], reverse=True)
    market = {position: positional_bid_history(snapshot, position)
              for position in {p.get('display_position') for p in candidates}}
    rows = []
    for player in candidates:
        key = player['player_key']
        workload = workload_summary(player, snapshot.get('recent_results', []))
        features = feature_context(player, candidates, points, workload, policy)
        upper = optimize_lineup(roster + [player], points, settings)
        upper_delta = round(upper['projected_points'] - baseline['projected_points'], 2)
        override = policy.get('news_overrides', {}).get(key, False)
        drop = None
        after = upper
        future_holes_added = 0
        # Pair evaluation is needed only for material projected upgrades or an
        # explicit override. No-drop upper bounds avoid thousands of useless fits.
        material = upper_delta >= 1.5 or override
        if material and not open_spot:
            options = []
            for replacement in roster:
                if replacement.get('is_undroppable') or replacement.get('selected_position') in RESERVE_SLOTS:
                    continue
                changed = [p for p in roster if p['player_key'] != replacement['player_key']] + [player]
                fit = optimize_lineup(changed, points, settings)
                if not fit['complete'] and baseline['complete']:
                    continue
                future = bye_coverage(changed, settings, snapshot['week'])
                extra_holes = max(0, sum(sum(r['unfilled_slots'].values()) for r in future) - base_future_holes)
                usage = workload_summary(replacement, snapshot.get('recent_results', []))['weeks']
                recent_usage = sum((r['carries'] or 0) + (r['targets'] or 0) for r in usage)
                options.append((fit['projected_points'], -extra_holes, -recent_usage,
                                -points.get(replacement['player_key'], 0), replacement, fit))
            if options:
                best = max(options, key=lambda option: option[:4])
                drop, after, future_holes_added = best[4], best[5], -best[1]
            else:
                after = baseline
        delta = round(after['projected_points'] - baseline['projected_points'], 2)
        # Upper bound is informative for a PASS but is not represented as a
        # realizable roster move when a full roster has no chosen replacement.
        if not open_spot and drop is None and material:
            delta = 0.0
        context = snapshot['acquisitions']
        remaining = 1 if context.get('unlimited') else context.get('remaining')
        inputs = DecisionInputs(player['name'], drop['name'] if drop else 'Open Spot' if open_spot else 'No drop recommended',
                                points[key], points.get(drop['player_key'], 0) if drop else 0,
                                None, policy.get('clearance_probabilities', {}).get(key),
                                policy.get('winning_bid_estimates', {}).get(key),
                                policy.get('bid_ceilings', {}).get(key), context.get('faab_balance') or 0,
                                remaining if remaining is not None else 1, features['candidate_score'], 'Low',
                                open_roster_spot=open_spot,
                                upside_stash_score=policy.get('upside_stash_scores', {}).get(key, 0),
                                news_override=override, availability=player['availability'],
                                projected_lineup_delta=delta)
        recommendation = asdict(recommend(inputs))
        missing = list(features['missing_features'])
        if player['availability'] == 'W' and material:
            missing += [field for field in ('clearance_probabilities', 'winning_bid_estimates', 'bid_ceilings')
                        if key not in policy.get(field, {})]
        if missing_roster or stale or remaining is None or future_holes_added:
            recommendation.update(action=Action.REVIEW, bid=None,
                                  reason='Missing/stale roster inputs, acquisition allowance, or a new future bye shortage requires review.')
        if player['availability'] == 'W' and context.get('faab_balance') is None and material:
            recommendation.update(action=Action.REVIEW, bid=None, reason='Current FAAB balance is missing.')
        rows.append({**recommendation, 'add_key': key, 'replace_key': drop['player_key'] if drop else None,
                     'availability': player['availability'], 'candidate_projection': points[key],
                     'before_lineup_projection': baseline['projected_points'],
                     'after_lineup_projection': after['projected_points'] if drop or open_spot else None,
                     'no_drop_upper_bound': upper['projected_points'],
                     'forecast_source': 'yahoo_fantasy_ui', 'workload': workload, 'features': features,
                     'market': market[player.get('display_position')], 'missing_inputs': missing,
                     'future_bye_slots_lost': future_holes_added,
                     'injury_status': player.get('status'),
                     'limitations': ['Provisional projection-based comparison; verify current player/teammate news before acting.',
                                     'Future-week Yahoo projections and long-term upside are not modeled yet.']})
    rows.sort(key=lambda r: (r['expected_lineup_improvement'], r['candidate_projection']), reverse=True)
    names = {p['player_key']: p['name'] for p in roster}
    statuses = {p['player_key']: p.get('status') for p in roster}
    for assignment in baseline['assignments']:
        assignment['name'] = names[assignment['player_key']]
        assignment['injury_status'] = statuses[assignment['player_key']]
    return {'report_version': 1, 'generated_at': now.isoformat(), 'snapshot_captured_at': snapshot['captured_at'],
            'team_key': snapshot['team_key'], 'week': snapshot['week'],
            'current_selected_lineup': selected, 'best_projected_lineup': baseline,
            'projected_gain_from_existing_roster': round(baseline['projected_points'] - selected['projected_points'], 2)
            if selected['complete_projection_coverage'] else None,
            'bye_coverage': coverage, 'opponents': opponent_context(snapshot),
            'recommendations': rows[:limit],
            'summary': {'evaluated_candidates': len(rows), 'available_players': len(available),
                        'material_current_week_upgrades': sum(r['expected_lineup_improvement'] >= 1.5 for r in rows),
                        'missing_roster_projections': missing_roster, 'stale_snapshot': stale,
                        'missing_or_stale_available_projections': sum(p['player_key'] not in points for p in available),
                        'zero_projection_players_not_ranked': sum(points.get(p['player_key']) == 0 for p in available)},
            'limitations': ['Each row is an independent alternative, not a list of transactions to execute together.',
                            'No current news feed, future projections, or historical pregame projection-surprise model.',
                            'Winning bid history cannot identify a waiver-clearance probability.',
                            'Projected optimal lineup is a deterministic scenario, not a probability of starting.',
                            'Zero-projection/bye/inactive players may still have long-term stash value not assessed here.',
                            'IR moves, game locks, positional maximums, and other Yahoo transaction restrictions need final review.']}


def latest_snapshot(directory: Path = Path('data/private')) -> Path:
    paths = sorted(directory.glob('snapshot-*.json'))
    if not paths:
        raise ValueError('No private snapshot found; refresh the league first')
    return paths[-1]


def save_report(report: dict, directory: Path = Path('data/private')) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (datetime.now(timezone.utc).strftime('waiver-report-%Y%m%dT%H%M%SZ-')
                        + uuid4().hex[:8] + '.json')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        json.dump(report, output, indent=2, ensure_ascii=False)
        output.write('\n')
    markdown = path.with_suffix('.md')
    md_fd = os.open(markdown, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(md_fd, 'w', encoding='utf-8') as output:
        output.write(render_report(report))
    return path


def render_report(report: dict) -> str:
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')

    summary = report['summary']
    lines = [f"# Week {report['week']} waiver report", '',
             'Provisional: based on captured Yahoo projections. Check current injuries and role news before acting.', '',
             f"Data captured: {report['snapshot_captured_at']} (timestamp includes timezone).", '']
    if summary['material_current_week_upgrades'] == 0:
        lines += ['No evaluated pickup clears the 1.5-point current-week lineup-improvement threshold.',
                  'This does not rule out longer-term depth or upside moves.', '']
    else:
        lines += [f"{summary['material_current_week_upgrades']} alternatives clear the projected improvement threshold.", '']
    selected = report['current_selected_lineup']
    best = report['best_projected_lineup']
    gain = report['projected_gain_from_existing_roster']
    if gain is not None:
        lines += [f"Existing roster: selected lineup **{selected['projected_points']:.2f}** projected points; "
                  f"best eligible lineup **{best['projected_points']:.2f}**; difference **{gain:+.2f}**.", '']
    lines += ['## Best projected lineup scenario', '', '| Slot | Player | Injury label |', '|---|---|---|']
    for row in best['assignments']:
        lines.append(f"| {cell(row['slot'])} | {cell(row['name'])} | {cell(row.get('injury_status') or '—')} |")
    lines += ['', 'No lineup change has been made.', '', '## Pickup comparisons', '',
              '| Add | Replace | Action | Projected gain | Bid |', '|---|---|---|---:|---:|']
    shown = [r for r in report['recommendations'] if r['expected_lineup_improvement'] > 0 or r['action'] != Action.PASS]
    for row in shown:
        lines.append(f"| {cell(row['add_player'])} | {cell(row['replace_player'])} | {cell(row['action'])} | "
                     f"{row['expected_lineup_improvement']:+.2f} | {row['bid'] if row['bid'] is not None else 'Needs review'} |")
    if not shown:
        lines.append('| No material candidate in this screen | — | PASS | — | — |')
    lines += ['', 'All comparisons are Low confidence and independent alternatives.', '', '## Upcoming bye coverage', '']
    for row in report['bye_coverage']:
        byes = ', '.join(row['players_on_bye']) or 'None'
        holes = ', '.join(f"{slot}: {count}" for slot, count in row['unfilled_slots'].items()) or 'No structural slot shortage'
        lines.append(f"- Week {row['week']}: {byes}. Coverage: {holes}.")
    lines += ['', 'Future coverage uses eligibility and known byes, not future forecasts or assumed injury recoveries.', '',
              '## Data limits', '']
    lines += [f'- {text}' for text in report['limitations']]
    if summary['stale_snapshot'] or summary['missing_roster_projections']:
        lines += ['', '**Refresh/review required:** stale snapshot or missing roster forecasts.']
    return '\n'.join(lines) + '\n'
