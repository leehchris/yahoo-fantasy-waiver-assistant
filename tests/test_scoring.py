from yahoo_waiver_assistant.scoring import CandidateFeatures, score_candidate


def test_candidate_score_uses_documented_weights():
    features = CandidateFeatures(
        player_name="Example RB",
        position="RB",
        expected_points=80,
        opportunity_trend=70,
        projection_outperformance=60,
        points_above_replacement=75,
        next_four_schedule=65,
        playoff_schedule=50,
        market_demand=40,
        sample_games=3,
    )

    result = score_candidate(features)

    assert result.score == 69.25
    assert result.confidence == "Medium"
