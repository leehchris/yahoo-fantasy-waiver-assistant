"""Forecast provenance and a deliberately conservative recent-results baseline."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .decision import DecisionInputs
from .enrichment import number


def recent_results_estimate(player: dict, history: list[dict], week: int, captured_at: str) -> dict:
    row = {'player_key': player['player_key'], 'week': week, 'projected_points': None,
           'source': 'recent_actuals_estimate', 'captured_at': captured_at,
           'confidence': 'Low', 'sample_weeks': [], 'limitations': [
               'Baseline only: no opponent adjustment, depth-chart model, or current news analysis.',
               'Past zeroes may reflect injuries or inactivity; this is not a Yahoo projection.']}
    if player.get('bye_week') == week:
        row.update(projected_points=0.0, source='known_bye', limitations=['Current Yahoo bye-week metadata.'])
        return row
    if player.get('status') in {'IR', 'O', 'NA', 'SUSP'}:
        row['limitations'].append('Player is currently unavailable; estimate withheld.')
        return row
    results = sorted([r for r in history if r['player_key'] == player['player_key']
                      and r['week'] < week and r['actual_points'] is not None
                      and r['week'] != player.get('bye_week')], key=lambda r: r['week'])[-4:]
    # The API includes zero rows for players with no recorded activity. Those
    # should not become apparently usable projections for every inactive player.
    if not results or not any(r['actual_points'] != 0 or any(v not in (None, 0) for v in r['stats'].values())
                              for r in results):
        row['limitations'].append('No recent recorded activity; estimate withheld.')
        return row
    weights = list(range(1, len(results) + 1))
    row['projected_points'] = round(sum(r['actual_points'] * w for r, w in zip(results, weights)) / sum(weights), 2)
    row['sample_weeks'] = [r['week'] for r in results]
    if player.get('status') in {'Q', 'D'}:
        row['limitations'].append('Current injury designation requires review before using this estimate.')
    return row


def load_provider_projections(path: Path, league_key: str, week: int, player_keys: set[str],
                              now: datetime | None = None) -> list[dict]:
    """Only league-scored point projections with explicit, recent provenance."""
    now = now or datetime.now(timezone.utc)
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(payload, dict):
        raise ValueError('Projection file must contain a JSON object')
    if payload.get('league_key') != league_key or payload.get('week') != week:
        raise ValueError('Projection file league/week does not match the snapshot')
    source = payload.get('source')
    if not isinstance(source, str) or not source.strip():
        raise ValueError('Projection file requires a source')
    try:
        generated = datetime.fromisoformat(payload['generated_at'].replace('Z', '+00:00'))
        if generated.utcoffset() is None:
            raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError('Projection generated_at must include a timezone') from None
    if now - generated > timedelta(hours=48) or generated - now > timedelta(minutes=5):
        raise ValueError('Projection file is stale or dated in the future')
    rows = []
    seen = set()
    if not isinstance(payload.get('players'), list):
        raise ValueError('Projection players must be a list')
    for item in payload['players']:
        if not isinstance(item, dict):
            raise ValueError('Projection player must be an object')
        key = item.get('player_key')
        points = number(item.get('projected_points'))
        if key not in player_keys or key in seen or points is None:
            raise ValueError('Projection file contains unknown/duplicate players or invalid points')
        seen.add(key)
        rows.append({'player_key': key, 'week': week, 'projected_points': points,
                     'source': source, 'captured_at': generated.isoformat(),
                     'confidence': 'Unspecified', 'sample_weeks': [],
                     'limitations': ['Imported points must already use this league scoring.']})
    if not rows:
        raise ValueError('Projection file contains no player projections')
    return rows


def decision_inputs_from_snapshot(snapshot: dict, add_key: str, replace_key: str,
                                  *, accept_estimates: bool = False, **policy) -> DecisionInputs:
    """Feed the existing decision engine without guessing its market/feature inputs.

    Required policy inputs remain lineup_probability, free_agency_probability,
    expected_winning_faab, max_justified_faab, candidate_score, and confidence.
    """
    if snapshot.get('schema_version', 2) != 2:
        raise ValueError('Refresh to snapshot schema version 2 before building decision inputs')
    candidates = {p['player_key']: p for p in snapshot['waivers'] + snapshot['free_agents']}
    roster = {p['player_key']: p for p in snapshot['roster']['players']}
    if add_key not in candidates or replace_key not in roster:
        raise ValueError('Add must be available and replacement must be on the current roster')
    if roster[replace_key].get('is_undroppable'):
        raise ValueError('Replacement is marked undroppable')
    projected = {p['player_key']: p for p in snapshot['projections']}
    points = []
    for key in (add_key, replace_key):
        row = projected.get(key, {})
        if row.get('week') != snapshot['week'] or number(row.get('projected_points')) is None:
            raise ValueError('Missing matching-week projection for add or replacement')
        if row.get('source') == 'recent_actuals_estimate' and not accept_estimates:
            raise ValueError('Recent-results estimates require explicit opt-in')
        points.append(row['projected_points'])
    if any(projected[key].get('source') == 'recent_actuals_estimate' for key in (add_key, replace_key)):
        policy['confidence'] = 'Low'
    context = snapshot['acquisitions']
    remaining = context.get('remaining')
    if context.get('unlimited'):
        remaining = 1  # Existing engine only checks whether any acquisitions remain.
    if remaining is None or context.get('faab_balance') is None:
        raise ValueError('Missing acquisition allowance or FAAB balance')
    inputs = DecisionInputs(add_player=candidates[add_key]['name'], replace_player=roster[replace_key]['name'],
                            candidate_expected_points=points[0], replacement_expected_points=points[1],
                            remaining_faab=context['faab_balance'], weekly_acquisitions_remaining=remaining,
                            **policy)
    return inputs
