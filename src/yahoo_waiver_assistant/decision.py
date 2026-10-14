from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class Action(StrEnum):
    CLAIM = 'CLAIM'
    VALUE_CLAIM = 'VALUE CLAIM'
    WAIT = 'WAIT FOR FREE AGENCY'
    PASS = 'PASS'
    PICKUP = 'PICK UP FREE AGENT'
    REVIEW = 'REVIEW'


@dataclass(frozen=True)
class DecisionInputs:
    add_player: str
    replace_player: str
    candidate_expected_points: float
    replacement_expected_points: float
    lineup_probability: float | None
    free_agency_probability: float | None
    expected_winning_faab: int | None
    max_justified_faab: int | None
    remaining_faab: int
    weekly_acquisitions_remaining: int
    candidate_score: float | None
    confidence: str
    open_roster_spot: bool = False
    upside_stash_score: float = 0.0
    news_override: bool = False
    availability: str = 'W'
    # Exact before/after best-lineup delta supersedes player-to-player subtraction.
    projected_lineup_delta: float | None = None


@dataclass(frozen=True)
class Recommendation:
    add_player: str
    replace_player: str
    action: Action
    bid: int | None
    max_bid: int | None
    expected_lineup_improvement: float
    free_agency_probability: float | None
    confidence: str
    reason: str


def recommend(inputs: DecisionInputs) -> Recommendation:
    if inputs.lineup_probability is not None and not 0 <= inputs.lineup_probability <= 1:
        raise ValueError('lineup_probability must be between 0 and 1')
    if inputs.free_agency_probability is not None and not 0 <= inputs.free_agency_probability <= 1:
        raise ValueError('free_agency_probability must be between 0 and 1')
    if not 0 <= inputs.upside_stash_score <= 100:
        raise ValueError('upside_stash_score must be between 0 and 100')
    if inputs.availability not in {'FA', 'W'}:
        raise ValueError('availability must be FA or W')
    if inputs.projected_lineup_delta is not None:
        improvement = round(inputs.projected_lineup_delta, 2)
    else:
        if inputs.lineup_probability is None:
            raise ValueError('Supply a lineup probability or exact projected lineup delta')
        improvement = round((inputs.candidate_expected_points - inputs.replacement_expected_points)
                            * inputs.lineup_probability, 2)
    if not math.isfinite(improvement):
        raise ValueError('Lineup improvement must be finite')
    maximum = (max(0, min(inputs.max_justified_faab, inputs.remaining_faab))
               if inputs.max_justified_faab is not None else None)

    def result(action, bid, reason):
        return Recommendation(inputs.add_player, inputs.replace_player, action, bid,
                              0 if inputs.availability == 'FA' else maximum, improvement,
                              inputs.free_agency_probability, inputs.confidence, reason)

    if inputs.weekly_acquisitions_remaining <= 0:
        return result(Action.PASS, 0, 'No weekly acquisitions remain.')
    material_upgrade = improvement >= 1.5
    worthwhile_stash = (inputs.open_roster_spot and inputs.upside_stash_score >= 70
                        and inputs.candidate_score is not None and inputs.candidate_score >= 60)
    if not (material_upgrade or worthwhile_stash or inputs.news_override):
        return result(Action.PASS, 0, 'The expected roster improvement does not clear the transaction threshold.')
    if inputs.availability == 'FA':
        return result(Action.PICKUP, 0, 'Available now with a material roster benefit; no waiver bid is needed.')
    probability = inputs.free_agency_probability
    if probability is not None and probability >= 0.70 and not inputs.news_override:
        return result(Action.WAIT, 0, 'The player is useful, but the model expects a strong chance he clears waivers.')
    if probability is None or maximum is None or inputs.expected_winning_faab is None:
        return result(Action.REVIEW, None, 'Useful waiver candidate, but clearance probability, justified bid ceiling, or price is missing.')
    if maximum <= 0:
        return result(Action.WAIT, 0, 'The pickup is actionable, but no FAAB is available.')
    bid = min(max(0, inputs.expected_winning_faab), maximum)
    if inputs.news_override or probability < 0.40:
        return result(Action.CLAIM, bid, 'Meaningful roster value with a material risk the player will not reach free agency.')
    return result(Action.VALUE_CLAIM, bid, 'Worth protecting with a modest bid, but not enough demand to justify paying the ceiling.')
