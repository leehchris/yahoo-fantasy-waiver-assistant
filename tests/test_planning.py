import json
from datetime import datetime, timezone, timedelta

import pytest

from yahoo_waiver_assistant.planning import build_upcoming_plan
from yahoo_waiver_assistant.future_forecasts import attach_future_projections
from yahoo_waiver_assistant.plan_storage import save_plan
from yahoo_waiver_assistant.yahoo_ui import projection_capture_path


def sample():
    now = datetime.now(timezone.utc).isoformat()
    players = [{'player_key':'999.p.1','name':'Starting QB','eligible_positions':['QB'],
                'selected_position':'QB','bye_week':7,'is_undroppable':True},
               {'player_key':'999.p.2','name':'Starting K','eligible_positions':['K'],
                'selected_position':'K','bye_week':7},
               {'player_key':'999.p.3','name':'Bench WR','eligible_positions':['WR'],
                'selected_position':'BN'}]
    available = [{'player_key':'999.p.4','name':'Backup QB','eligible_positions':['QB'],'availability':'FA'},
                 {'player_key':'999.p.5','name':'Replacement K','eligible_positions':['K'],'availability':'FA'}]
    def row(key, week, points):
        return {'player_key':key,'week':week,'projected_points':points,'source':'yahoo_fantasy_ui','captured_at':now}
    projections = [row(key,6,p) for key,p in [('999.p.1',20),('999.p.2',8),('999.p.3',0),('999.p.4',0),('999.p.5',8)]]
    future = [row(key,w,p) for w, vals in [(7,[0,0,0,15,8]),(8,[20,8,0,16,8])]
              for key,p in zip([p['player_key'] for p in players+available],vals)]
    return {'schema_version':2,'captured_at':now,'week':6,'team_key':'999.l.123.t.1','league_key':'999.l.123',
            'roster':{'players':players},'waivers':[],'free_agents':available,'projections':projections,
            'future_projections':future,'acquisitions':{'remaining':3},
            'league_settings':{'end_week':17,'roster_positions':[
                {'position':'QB','count':1,'is_starting_position':True},
                {'position':'K','count':1,'is_starting_position':True},
                {'position':'BN','count':1,'is_starting_position':False}]}}


def test_zero_now_positive_future_candidate_and_combined_no_double_counting():
    plan = build_upcoming_plan(sample())
    assert plan['evaluated_weeks'] == [6,7,8]
    assert plan['full_window_evaluated']
    qb = next(row for row in plan['alternatives'] if row['add_key']=='999.p.4')
    assert qb['first_benefit_week'] == 7
    assert qb['projected_horizon_gain'] == 15
    assert len(plan['free_agent_scenario']) == 2
    assert plan['scenario_horizon_gain'] == 23
    assert len({r['replace_key'] for r in plan['free_agent_scenario']}) == 2


def test_missing_future_roster_forecasts_are_not_current_week_extrapolations():
    s = sample()
    s['future_projections'] = []
    plan = build_upcoming_plan(s)
    assert plan['evaluated_weeks'] == [6]
    assert not plan['alternatives'] and not plan['free_agent_scenario']
    assert plan['coverage'][1]['baseline_points'] is None


def test_bye_zero_is_known_even_without_yahoo_numeric_row():
    s = sample()
    s['future_projections'] = [r for r in s['future_projections'] if not (r['week']==7 and r['player_key'] in {'999.p.1','999.p.2'})]
    assert 7 in build_upcoming_plan(s)['evaluated_weeks']


def test_stale_future_rows_withheld_and_partial_window_explicit():
    s = sample()
    for row in s['future_projections']:
        if row['week']==8:
            row['captured_at']=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat()
    plan=build_upcoming_plan(s)
    assert plan['evaluated_weeks']==[6,7] and not plan['full_window_evaluated']


def test_acquisition_allowance_waivers_and_ir():
    s = sample()
    s['acquisitions']['remaining']=1
    assert len(build_upcoming_plan(s)['free_agent_scenario'])==1
    s['acquisitions']['remaining']=None
    assert not build_upcoming_plan(s)['free_agent_scenario']
    s=sample()
    player=s['free_agents'].pop(0)
    player['availability']='W'
    s['waivers']=[player]
    plan=build_upcoming_plan(s)
    row=next(r for r in plan['alternatives'] if r['add_key']=='999.p.4')
    assert row['acquisition_status']=='REVIEW' and row['bid'] is None
    assert all(r['add_key']!='999.p.4' for r in plan['free_agent_scenario'])
    s=sample()
    s['roster']['players'][2]['selected_position']='IR'
    assert all(r['replace_key']!='999.p.3' for r in build_upcoming_plan(s)['alternatives'])


def test_future_loader_week_isolation_and_missing_capture(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    s=sample()
    path=projection_capture_path('999.l.123',7)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'league_key':'999.l.123','week':7,'source':'yahoo_fantasy_ui',
        'generated_at':datetime.now(timezone.utc).isoformat(),
        'players':[{'player_key':'999.p.4','projected_points':15}]}))
    loaded=attach_future_projections(s)
    assert len(loaded['future_projections'])==6 and loaded['future_projections'][0]['week']==7
    assert loaded['future_projection_coverage'][1]['warning']
    assert len(s['future_projections'])==10


def test_season_end_and_snapshot_freshness():
    s=sample()
    s['league_settings']['end_week']=7
    assert build_upcoming_plan(s)['requested_weeks']==[6,7]
    s['captured_at']=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat()
    with pytest.raises(ValueError,match='Refresh'):
        build_upcoming_plan(s)


def test_conflicting_future_values_rejected():
    s=sample()
    s['future_projections'].append({**s['future_projections'][0],'projected_points':99})
    with pytest.raises(ValueError,match='Conflicting'):
        build_upcoming_plan(s)


def test_private_plan_files_and_cli_without_credentials(tmp_path,monkeypatch,capsys):
    path=save_plan(build_upcoming_plan(sample()),tmp_path)
    assert path.with_suffix('.md').exists()
    assert 'No Yahoo roster changes' in path.with_suffix('.md').read_text()
    from yahoo_waiver_assistant import cli
    monkeypatch.chdir(tmp_path)
    root=tmp_path/'data/private'
    root.mkdir(parents=True)
    (root/'snapshot-20261014T000000Z-example.json').write_text(json.dumps(sample()))
    monkeypatch.setattr('sys.argv',['waiver-assistant','plan'])
    monkeypatch.setattr(cli,'_services',lambda:pytest.fail('Offline planning must not use OAuth'))
    cli.main()
    assert 'Saved private upcoming-week plan:' in capsys.readouterr().out


def test_zero_point_backup_is_not_useful_coverage():
    s=sample()
    for row in s['future_projections']:
        if row['player_key']=='999.p.4':
            row['projected_points']=0
    plan=build_upcoming_plan(s)
    assert all(row['add_key']!='999.p.4' for row in plan['alternatives'])


def test_tiny_improvements_do_not_accumulate_into_forced_churn():
    s=sample()
    s['roster']['players'][1]['bye_week']=None
    for row in s['projections']+s['future_projections']:
        if row['player_key']=='999.p.2':
            row['projected_points']=8
        if row['player_key']=='999.p.5':
            row['projected_points']=8.6
    assert all(row['add_key']!='999.p.5' for row in build_upcoming_plan(s)['alternatives'])


def test_embedded_future_snapshot_is_portable_without_cache_files(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    loaded=attach_future_projections(sample())
    assert len(loaded['future_projections'])==10
    assert build_upcoming_plan(loaded)['full_window_evaluated']


def test_partial_window_does_not_propose_combined_acquisitions():
    s=sample()
    s['future_projections']=[r for r in s['future_projections'] if r['week']==7]
    plan=build_upcoming_plan(s)
    assert plan['evaluated_weeks']==[6,7]
    assert not plan['free_agent_scenario']
    assert all(row['acquisition_status']=='REVIEW' for row in plan['alternatives'])


def test_unknown_candidate_week_is_not_zero_or_carried_forward():
    s=sample()
    s['future_projections']=[r for r in s['future_projections'] if not (r['week']==8 and r['player_key']=='999.p.4')]
    assert all(row['add_key']!='999.p.4' for row in build_upcoming_plan(s)['alternatives'])


def test_historical_roster_week_is_not_current_upcoming_plan():
    s=sample()
    s['league_settings']['current_week']=7
    with pytest.raises(ValueError,match='current league week'):
        build_upcoming_plan(s)
