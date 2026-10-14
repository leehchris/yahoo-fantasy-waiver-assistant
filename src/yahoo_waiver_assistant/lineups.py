"""Exact player-to-slot assignment for projected lineup comparisons."""
from __future__ import annotations

from .enrichment import number

RESERVE_SLOTS = {'IR', 'IR+', 'NA', 'IL', 'IL+'}
UNAVAILABLE = {'IR', 'O', 'NA', 'SUSP'}


def positions(player: dict) -> set[str]:
    values = set(player.get('eligible_positions') or [])
    if not values and player.get('display_position'):
        values.update(player['display_position'].replace('/', ',').split(','))
    return {value.strip() for value in values}


def eligible(player: dict, slot: str) -> bool:
    values = positions(player)
    if slot in values:
        return True
    flexible = {'W/R/T': {'WR', 'RB', 'TE'}, 'W/R': {'WR', 'RB'}, 'W/T': {'WR', 'TE'},
                'Q/W/R/T': {'QB', 'WR', 'RB', 'TE'}}
    return bool(values & flexible.get(slot, set()))


def starting_slots(settings: dict) -> list[tuple[str, int]]:
    result = []
    for row in settings.get('roster_positions', []):
        if row.get('is_starting_position'):
            count = row.get('count')
            if not isinstance(count, int) or count < 0:
                raise ValueError('Invalid starting-slot count')
            if count:
                result.append((row['position'], count))
    if not result:
        raise ValueError('League starting roster slots are missing')
    return result


def optimize_lineup(players: list[dict], projections: dict[str, float], settings: dict,
                    *, bye_week: int | None = None, structural: bool = False) -> dict:
    """Maximize filled slots, then points, respecting eligibility and unique players.

    Dynamic programming over slot counts resolves flex conflicts exactly. This
    is a comparison model, never a Yahoo roster edit. Unknown projections are
    omitted rather than replaced with made-up zeroes.
    """
    slots = starting_slots(settings)
    keys = [p['player_key'] for p in players]
    if len(keys) != len(set(keys)):
        raise ValueError('Roster contains duplicate player keys')
    dp = {(0,) * len(slots): (0.0, ())}
    for player in players:
        if player.get('selected_position') in RESERVE_SLOTS:
            continue
        if bye_week is not None and player.get('bye_week') == bye_week:
            continue
        if not structural and player.get('status') in UNAVAILABLE:
            continue
        score = 1.0 if structural else number(projections.get(player['player_key']))
        if score is None:
            continue
        allowed = [i for i, (slot, _) in enumerate(slots) if eligible(player, slot)]
        updated = dict(dp)
        for state, (points, assignment) in dp.items():
            for index in allowed:
                if state[index] >= slots[index][1]:
                    continue
                target = list(state)
                target[index] += 1
                target = tuple(target)
                value = (points + score, assignment + ((player['player_key'], slots[index][0]),))
                if target not in updated or value[0] > updated[target][0]:
                    updated[target] = value
        dp = updated
    state = max(dp, key=lambda key: (sum(key), dp[key][0]))
    points, assignment = dp[state]
    return {'projected_points': round(points, 2), 'filled_slots': sum(state),
            'required_slots': sum(count for _, count in slots),
            'complete': all(state[i] == count for i, (_, count) in enumerate(slots)),
            'assignments': [{'player_key': key, 'slot': slot} for key, slot in assignment],
            'unfilled': {slot: count - state[i] for i, (slot, count) in enumerate(slots)
                         if count > state[i]}}


def bye_coverage(players: list[dict], settings: dict, week: int, lookahead: int = 3) -> list[dict]:
    return [{'week': future,
             'players_on_bye': [p['name'] for p in players if p.get('bye_week') == future],
             'unfilled_slots': optimize_lineup(players, {}, settings, bye_week=future,
                                                structural=True)['unfilled']}
            for future in range(week + 1, min(week + lookahead, settings.get('end_week') or 18) + 1)]
