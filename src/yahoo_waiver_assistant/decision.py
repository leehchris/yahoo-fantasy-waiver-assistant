from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Action(StrEnum):
    CLAIM = "CLAIM"
    VALUE_CLAIM = "VALUE CLAIM"
    WAIT = "WAIT FOR FREE AGENCY"
    PASS = "PASS"


@dataclass(frozen=True)
class DecisionInputs:
    add_player: str
    replace_player: str
    candidate_expected_points: float
    replacement_expected_points: float
    lineup_probability: float
    free_agency_probability: float
    expected_winning_faab: int
    max_justified_faab: int
    remaining_faab: int
    weekly_acquisitions_remaining: int
    candidate_score: float
    confidence: str
    open_roster_spot: bool = False
    upside_stash_score: float = 0.0
    news_override: bool = False


@dataclass(frozen=True)
class Recommendation:
    add_player: str
    replace_player: str
    action: Action
    bid: int
    max_bid: int
    expected_lineup_improvement: float
    free_agency_probability: float
    confidence: str
    reason: str


def recommend(inputs: DecisionInputs) -> Recommendation:
    if not 0 <= inputs.lineup_probability <= 1:
        raise ValueError("lineup_probability must be between 0 and 1")
    if not 0 <= inputs.free_agency_probability <= 1:
        raise ValueError("free_agency_probability must be between 0 and 1")
    if not 0 <= inputs.upside_stash_score <= 100:
        raise ValueError("upside_stash_score must be between 0 and 100")

    raw_upgrade = inputs.candidate_expected_points - inputs.replacement_expected_points
    expected_lineup_improvement = round(raw_upgrade * inputs.lineup_probability, 2)

    effective_max = max(
        0, min(inputs.max_justified_faab, inputs.remaining_faab)
    )

    if inputs.weekly_acquisitions_remaining <= 0:
        return Recommendation(
            inputs.add_player,
            inputs.replace_player,
            Action.PASS,
            0,
            effective_max,
            expected_lineup_improvement,
            inputs.free_agency_probability,
            inputs.confidence,
            "No weekly acquisitions remain.",
        )

    material_upgrade = expected_lineup_improvement >= 1.5
    worthwhile_stash = (
        inputs.open_roster_spot
        and inputs.upside_stash_score >= 70
        and inputs.candidate_score >= 60
    )
    actionable = material_upgrade or worthwhile_stash or inputs.news_override

    if not actionable:
        return Recommendation(
            inputs.add_player,
            inputs.replace_player,
            Action.PASS,
            0,
            effective_max,
            expected_lineup_improvement,
            inputs.free_agency_probability,
            inputs.confidence,
            "The expected roster improvement does not clear the transaction threshold.",
        )

    if inputs.free_agency_probability >= 0.70 and not inputs.news_override:
        return Recommendation(
            inputs.add_player,
            inputs.replace_player,
            Action.WAIT,
            0,
            effective_max,
            expected_lineup_improvement,
            inputs.free_agency_probability,
            inputs.confidence,
            "The player is useful, but the model expects a strong chance he clears waivers.",
        )

    expected_price = max(0, inputs.expected_winning_faab)
    bid = min(expected_price, effective_max)

    if effective_max <= 0:
        return Recommendation(
            inputs.add_player,
            inputs.replace_player,
            Action.WAIT,
            0,
            0,
            expected_lineup_improvement,
            inputs.free_agency_probability,
            inputs.confidence,
            "The pickup is actionable, but no FAAB is available.",
        )

    if inputs.news_override or inputs.free_agency_probability < 0.40:
        action = Action.CLAIM
        reason = (
            "Meaningful roster value with a material risk the player will not reach free agency."
        )
    else:
        action = Action.VALUE_CLAIM
        reason = (
            "Worth protecting with a modest bid, but not enough demand to justify paying the ceiling."
        )

    return Recommendation(
        inputs.add_player,
        inputs.replace_player,
        action,
        bid,
        effective_max,
        expected_lineup_improvement,
        inputs.free_agency_probability,
        inputs.confidence,
        reason,
    )
