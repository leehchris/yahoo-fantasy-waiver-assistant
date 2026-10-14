import copy
import pytest
from yahoo_waiver_assistant.performance import build_performance, import_history, render_performance, fetch_season
from yahoo_waiver_assistant.refresh import build_bundle, render_bundle
from yahoo_waiver_assistant.cli import build_parser


def season():
    rosters = [{'week': w, 'players': [
        {'player_key': '999.p.1', 'name': 'Starter', 'selected_position': 'WR', 'week': w},
        {'player_key': '999.p.2', 'name': 'Bench', 'selected_position': 'BN', 'week': w}]} for w in [1, 2, 3]]
    return {'team_key': '999.l.123.t.1', 'league_key': '999.l.123', 'rosters': rosters,
        'actuals': [{'week': w, 'player_key': key, 'actual_points': a}
                    for w in [1, 2, 3] for key, a in [('999.p.1', 5), ('999.p.2', 0 if w == 3 else 9)]],
        'projection_capture': {'team_key': '999.l.123.t.1', 'league_key': '999.l.123',
             'source': 'yahoo_historical_roster_ui', 'captured_at': '2026-10-14T20:00:00+00:00',
             'players': [{'week': w, 'player_key': key, 'projected_points': 10}
                         for w in [1, 2, 3] for key in ['999.p.1', '999.p.2']]}}


def test_starters_not_bench_and_repeated_shortfall():
    r = build_performance(season(), {'999.p.1'})
    assert r['season_delta'] == -15
    assert all(w['actual'] == 5 and w['projected'] == 10 for w in r['weekly'])
    p = r['players'][0]
    assert p['repeated_shortfall'] and p['misses'] == 3
    assert 'Starter' in render_performance(r)


def test_zero_context_small_sample_and_unknown():
    r = build_performance(season())
    p = next(p for p in r['players'] if p['name'] == 'Bench')
    assert p['zero_point_weeks'] == [3] and p['zero_shortfall'] == 10
    assert p['delta_excluding_zeros'] == -2
    s = season()
    s['projection_capture'] = None
    r = build_performance(s)
    assert r['season_delta'] is None and not r['comparison_complete']
    assert all(p['delta'] is None and not p['repeated_shortfall'] for p in r['players'])
    s = season()
    s['projection_capture']['players'] = s['projection_capture']['players'][:2]
    assert not any(p['repeated_shortfall'] for p in build_performance(s)['players'])


def test_missing_actual_zero_forecast_and_negative_result():
    s = season()
    s['actuals'][0]['actual_points'] = -2
    s['projection_capture']['players'][0]['projected_points'] = 0
    r = build_performance(s)
    assert r['weekly'][0]['delta'] == -2
    assert next(p for p in r['players'] if p['name'] == 'Starter')['sample_weeks'] == 2
    s['actuals'][0]['actual_points'] = None
    assert build_performance(s)['season_delta'] is None


@pytest.mark.parametrize('mutation', ['source', 'team', 'duplicate', 'future', 'nan', 'slot'])
def test_invalid_history_rejected(mutation):
    s = season()
    c = s['projection_capture']
    if mutation == 'source': c['source'] = 'recent_estimate'
    if mutation == 'team': c['team_key'] = '999.l.123.t.2'
    if mutation == 'duplicate': c['players'].append(copy.copy(c['players'][0]))
    if mutation == 'future': c['players'][0]['week'] = 6
    if mutation == 'nan': c['players'][0]['projected_points'] = 'NaN'
    if mutation == 'slot': s['rosters'][0]['players'][0]['selected_position'] = None
    with pytest.raises(ValueError): build_performance(s)


def page():
    # Sanitized completed-roster table shape: separate actual and forecast columns,
    # an edit-cell colspan, and a bye row without numeric forecasts.
    return {'week': 1, 'url': 'https://football.fantasysports.yahoo.com/f1/123/1/team?week=1',
        'tables': [{'caption': 'Example Offense roster for week 1.',
            'headers': [{'text': t} for t in ['Pos', 'Offense', 'Fan Pts', 'Proj Pts']],
            'rows': [{'player_id': '1', 'cells': [{'text': 'WR', 'colspan': 2}, {'text': '5'}, {'text': '10'}]},
                     {'player_id': '2', 'cells': [{'text': t} for t in ['BN', 'Example', 'Bye', 'Bye']]}]}]}


def test_historical_dom_import_does_not_confuse_actual_points():
    c = import_history([page()], '999.l.123.t.1', '999.l.123', 2)
    assert c['players'] == [{'player_key': '999.p.1', 'projected_points': 10, 'week': 1}]
    for wrong in [1, 0]:
        with pytest.raises(ValueError): import_history([page()], '999.l.123.t.1', '999.l.123', wrong)
    with pytest.raises(ValueError): import_history([page()], '999.l.123.t.2', '999.l.123', 2)


def test_bundle_has_all_four_outputs():
    from test_report import snapshot
    s = snapshot()
    s['league_key'] = '999.l.123'
    b = build_bundle(s, build_performance(season()), lookahead=2)
    text = render_bundle(b)
    for phrase in ['Best projected lineup', 'Pickup comparisons', 'Upcoming-week plan', 'Season performance']:
        assert phrase in text
    assert build_parser().parse_args(['refresh', '--open']).open
    assert build_parser().parse_args(['performance']).command == 'performance'


def test_refresh_single_capture_and_no_saved_bundle_on_failure(monkeypatch):
    import yahoo_waiver_assistant.refresh as module
    from test_report import snapshot
    s = snapshot()
    s['league_key'] = '999.l.123'
    calls = []
    monkeypatch.setattr(module, 'create_snapshot', lambda *a, **kw: calls.append('snapshot') or s)
    monkeypatch.setattr(module, 'load_history', lambda *a: None)
    monkeypatch.setattr(module, 'fetch_season', lambda *a: season())
    monkeypatch.setattr(module, 'save_snapshot', lambda *a: calls.append('save') or 'saved')
    path, b = module.refresh(object())
    assert path == 'saved' and calls == ['snapshot', 'save']
    monkeypatch.setattr(module, 'fetch_season', lambda *a: (_ for _ in ()).throw(ValueError('Wrong week')))
    with pytest.raises(ValueError): module.refresh(object())
    assert calls == ['snapshot', 'save', 'snapshot']


def test_report_html_escapes_player_names_and_formats_tables():
    from yahoo_waiver_assistant.report_html import render_html
    text = render_html('# Report\n\n| Player | Points |\n|---|---:|\n| <script>alert(1)</script> | **10** |')
    assert '<script>' not in text and '&lt;script&gt;' in text
    assert '<table>' in text and '<strong>10</strong>' in text


def test_fetch_season_checks_historical_week_and_batches_own_players(monkeypatch):
    import yahoo_waiver_assistant.performance as module
    class Client:
        def roster(self, team, week):
            return {'team_key': team, 'week': week, 'players': [{'player_key': '999.p.1'}]}
    monkeypatch.setattr(module, 'normalize_roster', lambda payload: payload)
    calls = []
    monkeypatch.setattr(module, 'fetch_history', lambda client, league, keys, weeks: calls.append((keys,weeks)) or [])
    s = {'team_key':'999.l.123.t.1','league_key':'999.l.123','week':4,
         'league_settings': {'start_week':1,'current_week':4}}
    r = fetch_season(Client(), s)
    assert [p['week'] for p in r['rosters']] == [1,2,3]
    assert calls == [(['999.p.1'],[1]),(['999.p.1'],[2]),(['999.p.1'],[3])]
    monkeypatch.setattr(module, 'normalize_roster', lambda payload: {**payload,'week':4})
    with pytest.raises(ValueError, match='mismatch'): fetch_season(Client(), s)
