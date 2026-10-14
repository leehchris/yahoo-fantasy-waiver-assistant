import json
from pathlib import Path

import pytest

from yahoo_waiver_assistant.yahoo_json import (
    discovery_summary, league_key_from_team, normalize_players,
    normalize_roster, normalize_transactions,
)


def fixture(name):
    return json.loads((Path(__file__).parent / 'fixtures' / f'{name}.json').read_text())


@pytest.mark.parametrize('name,status', [('free_agents', 'FA'), ('waivers', 'W')])
def test_real_available_shapes(name, status):
    players = normalize_players(fixture(name), status)
    assert len(players) == 2
    assert players[0]['name'] == 'Example'
    assert players[0]['player_key'].startswith('999.p.')
    assert players[0]['availability'] == status
    assert isinstance(players[0]['eligible_positions'], list)


def test_real_roster_shape():
    roster = normalize_roster(fixture('roster'))
    assert roster['team_key'] == '999.l.123.t.1'
    assert roster['faab_balance'] == 1
    assert roster['roster_adds']['value'] == 0
    assert len(roster['players']) == 2
    assert roster['players'][0]['selected_position'] == 'QB'
    assert roster['players'][0]['week'] == 1


def test_real_transaction_list_and_dict_movement():
    transactions = normalize_transactions(fixture('transactions'))
    assert len(transactions) == 2
    transaction = transactions[0]
    assert transaction['type'] == 'add/drop'
    assert transaction['timestamp'] == 1
    add, drop = transaction['players']
    assert add['transaction_data']['type'] == 'add'
    assert add['transaction_data']['destination_team_key'] == '999.l.123.t.1'
    assert drop['transaction_data']['type'] == 'drop'
    assert drop['transaction_data']['destination_type'] == 'waivers'


def test_missing_and_zero_bid_and_empty_collections():
    payload = {'transactions': {'0': {'transaction': [{'faab_bid': '0'}, {'players': {'count': 0}}]}}}
    assert normalize_transactions(payload)[0]['faab_bid'] == 0
    assert normalize_transactions({'transaction': {'faab_bid': 'bad'}})[0]['faab_bid'] is None
    assert normalize_transactions({'transactions': {'count': 0}}) == []
    assert normalize_players({'players': []}) == []
    assert normalize_roster({})['players'] == []


def test_entity_fields_do_not_leak_nested_names_or_status():
    payload = {'game_key': '999', 'name': 'Football', 'teams': {'0': {'team': [
        [{'team_key': '999.l.123.t.1'}, {'name': 'Example Team'},
         {'managers': [{'manager': {'name': 'Private Manager'}}]}]]},
        '1': {'team': [{'team_key': '999.l.123.t.2'}, {'name': 'Other'}]}}}
    summary = discovery_summary(payload)
    assert summary['league_keys'] == ['999.l.123']
    assert summary['team_names'] == ['Example Team', 'Other']
    player = normalize_players({'player': [[{'status': 'Q'}, {'is_keeper': {'status': False}}]]})[0]
    assert player['status'] == 'Q'


@pytest.mark.parametrize('key', ['invalid', '999.l.123', '999.l.123.t.1/transactions'])
def test_invalid_team_key(key):
    with pytest.raises(ValueError):
        league_key_from_team(key)


def test_current_player_note_metadata():
    players = normalize_players({'player': [[{'has_player_notes': '0'},
                                             {'player_notes_last_timestamp': '123'}]]})
    assert players[0]['has_player_notes'] is False
    assert players[0]['player_notes_last_timestamp'] == 123
