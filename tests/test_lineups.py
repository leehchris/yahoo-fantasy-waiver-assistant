import pytest

from yahoo_waiver_assistant.lineups import optimize_lineup, bye_coverage


def settings(*slots):
    return {'roster_positions': [{'position': slot, 'count': count, 'is_starting_position': True}
                                  for slot, count in slots], 'end_week': 17}


def player(key, position, **extras):
    return {'player_key': key, 'name': key, 'eligible_positions': [position],
            'selected_position': 'BN', **extras}


def test_exact_flex_assignment_and_unique_players():
    players = [player('WR', 'WR'), player('RB', 'RB')]
    fit = optimize_lineup(players, {'WR': 8, 'RB': 10}, settings(('WR', 1), ('W/R/T', 1)))
    assert fit['complete'] and fit['projected_points'] == 18
    assert {'player_key': 'RB', 'slot': 'W/R/T'} in fit['assignments']
    fit = optimize_lineup(players[:1], {'WR': 8}, settings(('WR', 1), ('W/R/T', 1)))
    assert fit['filled_slots'] == 1 and not fit['complete']


def test_negative_points_fill_required_slot_and_missing_is_not_zero():
    roster = [player('DEF', 'DEF')]
    assert optimize_lineup(roster, {'DEF': -1}, settings(('DEF', 1)))['projected_points'] == -1
    assert not optimize_lineup(roster, {}, settings(('DEF', 1)))['complete']


def test_ir_unavailable_and_bye_coverage():
    roster = [player('Reserve', 'RB', selected_position='IR'), player('Out', 'RB', status='O'),
              player('Starter', 'RB', bye_week=7)]
    fit = optimize_lineup(roster, {'Reserve': 100, 'Out': 90, 'Starter': 10}, settings(('RB', 1)))
    assert fit['projected_points'] == 10
    # Future structural coverage does not assume a current O designation lasts forever.
    cover = bye_coverage(roster[::2], settings(('RB', 1)), 6)
    assert cover[0]['unfilled_slots'] == {'RB': 1}


def test_duplicates_and_unknown_slots_fail():
    with pytest.raises(ValueError, match='duplicate'):
        optimize_lineup([player('A', 'WR')] * 2, {'A': 10}, settings(('WR', 1)))
    with pytest.raises(ValueError, match='missing'):
        optimize_lineup([], {}, {})
