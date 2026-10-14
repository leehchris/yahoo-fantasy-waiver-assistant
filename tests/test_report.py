import json
from datetime import datetime, timezone, timedelta

import pytest

from yahoo_waiver_assistant.decision import Action
from yahoo_waiver_assistant.report import build_report, latest_snapshot, save_report, validate_policy
from yahoo_waiver_assistant.market import positional_bid_history


def snapshot(candidate_points=15, availability='FA'):
    now = datetime.now(timezone.utc).isoformat()
    players = [{'player_key': '999.p.1', 'name': 'QB', 'display_position': 'QB',
                'eligible_positions': ['QB'], 'selected_position': 'QB', 'is_undroppable': True},
               {'player_key': '999.p.2', 'name': 'Starter', 'display_position': 'WR',
                'eligible_positions': ['WR'], 'selected_position': 'WR'},
               {'player_key': '999.p.3', 'name': 'Bench', 'display_position': 'WR',
                'eligible_positions': ['WR'], 'selected_position': 'BN'}]
    candidate = {'player_key': '999.p.4', 'name': 'Candidate', 'display_position': 'WR',
                 'eligible_positions': ['WR'], 'availability': availability}
    projections = [{'player_key': key, 'projected_points': value, 'week': 6,
                    'source': 'yahoo_fantasy_ui', 'captured_at': now}
                   for key, value in [('999.p.1', 30), ('999.p.2', 10), ('999.p.3', 1), ('999.p.4', candidate_points)]]
    history = [{'player_key': key, 'week': week, 'actual_points': 5, 'stats': {'8': 0, '78': targets, '11': 1}}
               for key, targets in [('999.p.2', 8), ('999.p.3', 1), ('999.p.4', 6)] for week in [2, 3, 4, 5]]
    return {'schema_version': 2, 'captured_at': now, 'team_key': '999.l.123.t.1', 'week': 6,
            'league_settings': {'end_week': 17, 'roster_positions': [
                {'position': 'QB', 'count': 1, 'is_starting_position': True},
                {'position': 'WR', 'count': 1, 'is_starting_position': True},
                {'position': 'BN', 'count': 1, 'is_starting_position': False}]},
            'roster': {'players': players}, 'waivers': [candidate] if availability == 'W' else [],
            'free_agents': [candidate] if availability == 'FA' else [],
            'projections': projections, 'recent_results': history, 'transactions': [], 'league_rosters': [],
            'acquisitions': {'remaining': 2, 'faab_balance': 10}}


def test_add_drop_uses_lineup_delta_not_candidate_minus_weak_bench():
    row = build_report(snapshot())['recommendations'][0]
    assert row['action'] == Action.PICKUP and row['bid'] == 0
    assert row['replace_key'] == '999.p.3'
    assert row['expected_lineup_improvement'] == 5  # Not 15 - 1 = 14.
    assert row['features']['candidate_score'] is None
    assert row['features']['missing_features']


def test_bench_upgrade_not_starting_upgrade_is_pass():
    row = build_report(snapshot(8))['recommendations'][0]
    assert row['action'] == Action.PASS
    assert row['expected_lineup_improvement'] == 0
    assert row['replace_key'] is None


def test_waiver_demand_is_not_invented_and_explicit_policy_uses_existing_engine():
    s = snapshot(15, 'W')
    row = build_report(s)['recommendations'][0]
    assert row['action'] == Action.REVIEW and row['bid'] is None
    assert row['free_agency_probability'] is None
    policy = {'clearance_probabilities': {'999.p.4': 0.2},
              'winning_bid_estimates': {'999.p.4': 3}, 'bid_ceilings': {'999.p.4': 5}}
    row = build_report(s, policy)['recommendations'][0]
    assert row['action'] == Action.CLAIM and row['bid'] == 3 and row['max_bid'] == 5


def test_acquisition_limit_missing_projection_and_staleness():
    s = snapshot()
    s['acquisitions']['remaining'] = 0
    assert build_report(s)['recommendations'][0]['action'] == Action.PASS
    s['acquisitions']['remaining'] = None
    assert build_report(s)['recommendations'][0]['action'] == Action.REVIEW
    s = snapshot()
    s['projections'][1]['projected_points'] = None
    assert build_report(s)['recommendations'][0]['action'] == Action.REVIEW
    s = snapshot()
    s['captured_at'] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    assert build_report(s)['recommendations'][0]['action'] == Action.REVIEW


def test_current_roster_improvement_precedes_pickup():
    s = snapshot(8)
    s['roster']['players'][1]['selected_position'] = 'BN'
    s['roster']['players'][2]['selected_position'] = 'WR'
    report = build_report(s)
    assert report['projected_gain_from_existing_roster'] == 9
    assert report['best_projected_lineup']['projected_points'] == 40


def test_bid_history_ignores_free_adds_failed_old_and_multi_add_transactions():
    s = snapshot()
    stamp = int(datetime.now(timezone.utc).timestamp()) - 1
    add = {'display_position': 'WR', 'transaction_data': {'type': 'add', 'destination_team_key': '999.l.123.t.2'}}
    s['transactions'] = [{'status': 'successful', 'timestamp': stamp, 'faab_bid': 0, 'players': [add]},
                         {'status': 'successful', 'timestamp': stamp, 'faab_bid': 6, 'players': [add]},
                         {'status': 'failed', 'timestamp': stamp, 'faab_bid': 100, 'players': [add]},
                         {'status': 'successful', 'timestamp': stamp, 'faab_bid': None, 'players': [add]},
                         {'status': 'successful', 'timestamp': stamp, 'faab_bid': 30, 'players': [add, add]},
                         {'status': 'successful', 'timestamp': stamp - 60*86400, 'faab_bid': 50, 'players': [add]}]
    market = positional_bid_history(s, 'WR')
    assert market['winning_bid_samples'] == 2 and market['median_winning_bid'] == 3
    assert market['clearance_probability'] is None


def test_policy_validation_rejects_unknowns_and_normalizes_numbers():
    with pytest.raises(ValueError):
        validate_policy({'clearance_probabilities': {'unknown': 0.3}}, {'999.p.4'})
    with pytest.raises(ValueError):
        validate_policy({'bid_ceilings': {'999.p.4': 1.2}}, {'999.p.4'})
    with pytest.raises(ValueError):
        validate_policy({'clearance_probabilities': {'999.p.4': 1.2}}, {'999.p.4'})
    assert validate_policy({'bid_ceilings': {'999.p.4': '3'}}, {'999.p.4'})['bid_ceilings']['999.p.4'] == 3


def test_private_report_does_not_become_latest_snapshot(tmp_path):
    path = tmp_path / 'snapshot-20261014T000000Z-test.json'
    path.write_text('{}')
    report_path = save_report(build_report(snapshot()), tmp_path)
    assert report_path.name.startswith('waiver-report-')
    assert latest_snapshot(tmp_path) == path
    assert json.loads(report_path.read_text())['report_version'] == 1


def test_report_cli_needs_no_credentials_or_yahoo_write(tmp_path, monkeypatch, capsys):
    from yahoo_waiver_assistant import cli
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / 'data/private'
    directory.mkdir(parents=True)
    (directory / 'snapshot-20261014T000000Z-test.json').write_text(json.dumps(snapshot()))
    def forbidden():
        raise AssertionError('Report must not initialize OAuth or execute transactions')
    monkeypatch.setattr(cli, '_services', forbidden)
    monkeypatch.setattr('sys.argv', ['waiver-assistant', 'report'])
    cli.main()
    assert 'Saved private waiver report:' in capsys.readouterr().out
    assert len(list(directory.glob('waiver-report-*.json'))) == 1


def test_future_bye_coverage_breaks_drop_tie():
    s = snapshot()
    s['roster']['players'][1]['bye_week'] = 7
    s['roster']['players'][2]['bye_week'] = 8
    s['free_agents'][0]['bye_week'] = 7
    row = build_report(s)['recommendations'][0]
    assert row['replace_key'] == '999.p.2'
    assert row['future_bye_slots_lost'] == 0


def test_open_spot_and_undroppable_replacements():
    s = snapshot()
    s['league_settings']['roster_positions'][-1]['count'] = 2
    row = build_report(s)['recommendations'][0]
    assert row['replace_player'] == 'Open Spot' and row['action'] == Action.PICKUP
    s = snapshot()
    s['roster']['players'][2]['is_undroppable'] = True
    assert build_report(s)['recommendations'][0]['replace_key'] == '999.p.2'


def test_zero_forecasts_with_explicit_news_context_are_not_discarded():
    s = snapshot(0)
    report = build_report(s, {'news_overrides': {'999.p.4': True}})
    assert report['summary']['evaluated_candidates'] == 1


def test_missing_capture_time_is_missing_forecast_not_zero():
    s = snapshot()
    s['projections'][1]['captured_at'] = None
    report = build_report(s)
    assert 'Starter' in report['summary']['missing_roster_projections']
    assert report['recommendations'][0]['action'] == Action.REVIEW


def test_readable_report_is_saved_and_marks_provisional_scenarios(tmp_path):
    report = build_report(snapshot())
    path = save_report(report, tmp_path)
    text = path.with_suffix('.md').read_text(encoding='utf-8')
    assert 'Provisional' in text
    assert 'PICK UP FREE AGENT' in text
    assert 'No lineup change has been made' in text
    assert 'Future coverage uses eligibility and known byes' in text
