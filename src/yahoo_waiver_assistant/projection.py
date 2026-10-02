from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass(frozen=True)
class ProjectionResult:
    player_name: str
    position: str
    week: int
    projected: float
    actual: float
    error: float
    z_score: float | None


def projection_error(projected: float, actual: float) -> float:
    return actual - projected


def add_position_week_z_scores(
    rows: list[tuple[str, str, int, float, float]]
) -> list[ProjectionResult]:
    """
    Calculate projection-error z-scores within each position/week population.

    Input rows:
        (player_name, position, week, projected_points, actual_points)

    Rows with a projected value <= 0 are excluded from the z-score population
    because injury/inactivity zeroes can create false outperformance signals.
    They are still returned with z_score=None.
    """
    grouped: dict[tuple[str, int], list[float]] = {}

    for _, position, week, projected, actual in rows:
        if projected > 0:
            grouped.setdefault((position, week), []).append(
                projection_error(projected, actual)
            )

    stats: dict[tuple[str, int], tuple[float, float]] = {}
    for key, errors in grouped.items():
        stats[key] = (mean(errors), pstdev(errors))

    output: list[ProjectionResult] = []
    for player_name, position, week, projected, actual in rows:
        error = projection_error(projected, actual)
        z_score = None

        if projected > 0:
            group_mean, group_sd = stats[(position, week)]
            if group_sd > 0:
                z_score = round((error - group_mean) / group_sd, 3)
            else:
                z_score = 0.0

        output.append(
            ProjectionResult(
                player_name=player_name,
                position=position,
                week=week,
                projected=projected,
                actual=actual,
                error=round(error, 3),
                z_score=z_score,
            )
        )

    return output
