import pytest

from yahoo_waiver_assistant.yahoo_ui import build_yahoo_projection_capture, parse_yahoo_projection_page


def page(selected='Week 6 (proj)', column='Fan Pts\ue002'):
    return {'url': 'https://football.fantasysports.yahoo.com/f1/123/players',
            'selected_stats': selected, 'tables': [{'headers': [
                {'text': 'Player'}, {'text': column}], 'rows': [
                {'player_id': '1', 'cells': [{'text': 'Example'}, {'text': '12.50'}]},
                {'player_id': '2', 'cells': [{'text': 'Other'}, {'text': '0.00'}]},
                {'player_id': '3', 'cells': [{'text': 'Missing'}, {'text': '-'}]}]}]}


def test_yahoo_ui_projected_selection_and_zero():
    capture = build_yahoo_projection_capture([page()], '999.l.123', 6)
    assert capture['source'] == 'yahoo_fantasy_ui'
    assert capture['players'] == [{'player_key': '999.p.1', 'projected_points': 12.5},
                                  {'player_key': '999.p.2', 'projected_points': 0}]


def test_actual_points_cannot_become_projections():
    with pytest.raises(ValueError, match='weekly projected'):
        parse_yahoo_projection_page(page(selected='Week 6'), '999.l.123', 6)


def test_roster_projection_column_and_colspans():
    p = page(column='Proj Pts')
    p['selected_stats'] = None
    table = p['tables'][0]
    table['caption'] = 'Example Offense roster for week 6.'
    table['headers'].insert(1, {'text': 'Fan Pts'})
    for row in table['rows']:
        row['cells'][0]['colspan'] = 2
    rows = parse_yahoo_projection_page(p, '999.l.123', 6)
    assert rows[0]['projected_points'] == 12.5
    with pytest.raises(ValueError, match='different scoring week'):
        parse_yahoo_projection_page(p, '999.l.123', 5)


def test_source_league_and_conflicting_duplicates():
    p = page()
    p['url'] = 'https://football.fantasysports.yahoo.com/f1/456/players'
    with pytest.raises(ValueError, match='requested Yahoo league'):
        parse_yahoo_projection_page(p, '999.l.123', 6)
    altered = page()
    altered['tables'][0]['rows'][0]['cells'][1]['text'] = '13'
    with pytest.raises(ValueError, match='changed during capture'):
        build_yahoo_projection_capture([page(), altered], '999.l.123', 6)
