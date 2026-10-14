import json
from datetime import datetime, timezone, timedelta

import pytest

from yahoo_waiver_assistant.forecasts import recent_results_estimate, load_provider_projections, decision_inputs_from_snapshot
from yahoo_waiver_assistant.decision import recommend, Action


def test_estimate_uses_past_weeks_weighted_and_separates_actuals():
    history = [{'player_key': '999.p.1', 'week': w, 'actual_points': p, 'stats': {}}
               for w, p in [(3, 2), (4, 4), (5, 6), (6, 100)]]
    row = recent_results_estimate({'player_key': '999.p.1'}, history, 6, 'capture')
    assert row['projected_points'] == 4.67
    assert row['sample_weeks'] == [3, 4, 5]
    assert row['confidence'] == 'Low'
    assert row['source'] == 'recent_actuals_estimate'
    assert history[-1]['actual_points'] == 100


def test_bye_injury_inactivity_and_unknown():
    player = {'player_key': '999.p.1'}
    history = [{'player_key': player['player_key'], 'week': 5, 'actual_points': 0, 'stats': {'9': 0}}]
    assert recent_results_estimate(player, history, 6, '')['projected_points'] is None
    assert recent_results_estimate({**player, 'bye_week': 6}, [], 6, '')['projected_points'] == 0
    history[0]['actual_points'] = 10
    assert recent_results_estimate({**player, 'status': 'IR'}, history, 6, '')['projected_points'] is None
    assert recent_results_estimate({**player, 'bye_week': 5}, history, 6, '')['projected_points'] is None


def provider_file(tmp_path, **updates):
    payload = {'league_key': '999.l.123', 'week': 6, 'source': 'Example provider',
               'generated_at': datetime.now(timezone.utc).isoformat(),
               'players': [{'player_key': '999.p.1', 'projected_points': 0}]}
    payload.update(updates)
    path = tmp_path / 'forecasts.json'
    path.write_text(json.dumps(payload))
    return path


def test_import_zero_with_provenance(tmp_path):
    rows = load_provider_projections(provider_file(tmp_path), '999.l.123', 6, {'999.p.1'})
    assert rows[0]['projected_points'] == 0
    assert rows[0]['source'] == 'Example provider'


@pytest.mark.parametrize('updates', [
    {'league_key': '999.l.456'}, {'week': 5}, {'source': ''},
    {'generated_at': '2026-10-14T10:00:00'},
    {'generated_at': (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()},
    {'players': [{'player_key': '999.p.2', 'projected_points': 5}]},
    {'players': [{'player_key': '999.p.1', 'projected_points': 'NaN'}]},
    {'players': [{'player_key': '999.p.1', 'projected_points': 1}] * 2},
    {'players': []},
])
def test_provider_validation(tmp_path, updates):
    with pytest.raises(ValueError):
        load_provider_projections(provider_file(tmp_path, **updates), '999.l.123', 6, {'999.p.1'})


def decision_snapshot():
    return {'week': 6, 'waivers': [{'player_key': '999.p.1', 'name': 'Add'}], 'free_agents': [],
            'roster': {'players': [{'player_key': '999.p.2', 'name': 'Drop'}]},
            'projections': [{'player_key': k, 'week': 6, 'projected_points': p,
                             'source': 'recent_actuals_estimate'} for k, p in [('999.p.1', 15), ('999.p.2', 5)]],
            'acquisitions': {'remaining': 2, 'faab_balance': 10}}


def policy():
    return dict(lineup_probability=1.0, free_agency_probability=0.2,
                expected_winning_faab=3, max_justified_faab=5, candidate_score=80, confidence='Low')


def test_existing_decision_engine_receives_snapshot_inputs():
    snapshot = decision_snapshot()
    with pytest.raises(ValueError, match='opt-in'):
        decision_inputs_from_snapshot(snapshot, '999.p.1', '999.p.2', **policy())
    inputs = decision_inputs_from_snapshot(snapshot, '999.p.1', '999.p.2', accept_estimates=True, **policy())
    result = recommend(inputs)
    assert result.action == Action.CLAIM
    assert result.bid == 3
    assert result.expected_lineup_improvement == 10
    snapshot['roster']['players'][0]['is_undroppable'] = True
    with pytest.raises(ValueError, match='undroppable'):
        decision_inputs_from_snapshot(snapshot, '999.p.1', '999.p.2', accept_estimates=True, **policy())


def test_unknown_or_wrong_week_projection_not_used():
    snapshot = decision_snapshot()
    snapshot['projections'][0]['week'] = 5
    with pytest.raises(ValueError, match='matching-week'):
        decision_inputs_from_snapshot(snapshot, '999.p.1', '999.p.2', accept_estimates=True, **policy())


def test_estimates_cannot_be_promoted_to_high_confidence():
    values = policy()
    values['confidence'] = 'High'
    inputs = decision_inputs_from_snapshot(decision_snapshot(), '999.p.1', '999.p.2',
                                          accept_estimates=True, **values)
    assert inputs.confidence == 'Low'
