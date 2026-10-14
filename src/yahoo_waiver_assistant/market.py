"""Observed bid history, not an invented waiver-clearance probability."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from statistics import median

from .enrichment import number
from .lineups import optimize_lineup


def positional_bid_history(snapshot: dict, position: str, days: int = 28) -> dict:
    captured = datetime.fromisoformat(snapshot['captured_at'].replace('Z', '+00:00'))
    bids = []
    team_bids: dict[str, list[float]] = {}
    for transaction in snapshot.get('transactions', []):
        bid = number(transaction.get('faab_bid'))
        stamp = transaction.get('timestamp')
        if transaction.get('status') != 'successful' or bid is None or bid < 0 or stamp is None:
            continue
        date = datetime.fromtimestamp(stamp, timezone.utc)
        if not captured - timedelta(days=days) <= date <= captured:
            continue
        adds = [p for p in transaction.get('players', [])
                if p.get('transaction_data', {}).get('type') == 'add']
        # A transaction-level bid cannot safely be allocated across multiple adds.
        if len(adds) != 1 or adds[0].get('display_position') != position:
            continue
        bids.append(bid)
        key = adds[0]['transaction_data'].get('destination_team_key')
        if key:
            team_bids.setdefault(key, []).append(bid)
    return {'position': position, 'lookback_days': days, 'winning_bid_samples': len(bids),
            'median_winning_bid': median(bids) if bids else None,
            'minimum_winning_bid': min(bids) if bids else None,
            'maximum_winning_bid': max(bids) if bids else None,
            'team_bid_history': [{'team_key': key, 'samples': len(values), 'median_bid': median(values)}
                                 for key, values in team_bids.items()],
            'clearance_probability': None,
            'limitations': ['Winning bids alone do not reveal losing bids or waiver-clearance rates.',
                            'Historical bids are context, not a calibrated price prediction.']}


def opponent_context(snapshot: dict) -> list[dict]:
    result = []
    for team in snapshot.get('league_rosters', []):
        if team.get('team_key') == snapshot['team_key']:
            continue
        available = [p for p in team['players'] if p.get('status') not in {'IR', 'O', 'NA', 'SUSP'}]
        fit = optimize_lineup(available, {}, snapshot['league_settings'],
                              bye_week=snapshot['week'], structural=True)
        result.append({'team_key': team.get('team_key'), 'name': team.get('name'),
                       'faab_balance': team.get('faab_balance'), 'unfilled_slots': fit['unfilled'],
                       'method': 'Structural slot coverage only; opponent projections are not captured.'})
    return result
