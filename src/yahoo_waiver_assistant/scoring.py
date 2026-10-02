from __future__ import annotations

from dataclasses import dataclass

WEIGHTS = {
    "expected_points": 0.30,
    "opportunity_trend": 0.20,
    "projection_outperformance": 0.15,
    "points_above_replacement": 0.15,
    "next_four_schedule": 0.10,
    "playoff_schedule": 0.05,
    "market_demand": 0.05,
}


@dataclass(frozen=True)
class CandidateFeatures:
    player_name: str
    position: str
    expected_points: float
    opportunity_trend: float
    projection_outperformance: float
    points_above_replacement: float
    next_four_schedule: float
    playoff_schedule: float
    market_demand: float
    sample_games: int = 0


@dataclass(frozen=True)
class CandidateScore:
    player_name: str
    position: str
    score: float
    confidence: str


def _validate_feature(value: float, name: str) -> None:
    if not 0 <= value <= 100:
        raise ValueError(f"{name} must be between 0 and 100")


def score_candidate(features: CandidateFeatures) -> CandidateScore:
    values = {
        "expected_points": features.expected_points,
        "opportunity_trend": features.opportunity_trend,
        "projection_outperformance": features.projection_outperformance,
        "points_above_replacement": features.points_above_replacement,
        "next_four_schedule": features.next_four_schedule,
        "playoff_schedule": features.playoff_schedule,
        "market_demand": features.market_demand,
    }

    for name, value in values.items():
        _validate_feature(value, name)

    score = sum(values[name] * WEIGHTS[name] for name in WEIGHTS)

    if features.sample_games >= 4:
        confidence = "High"
    elif features.sample_games >= 2:
        confidence = "Medium"
    else:
        confidence = "Low"

    return CandidateScore(
        player_name=features.player_name,
        position=features.position,
        score=round(score, 2),
        confidence=confidence,
    )
