from yahoo_waiver_assistant.projection import add_position_week_z_scores


def test_zero_projection_is_excluded_from_z_scores():
    rows = [
        ("RB A", "RB", 3, 10.0, 15.0),
        ("RB B", "RB", 3, 10.0, 5.0),
        ("Injured RB", "RB", 3, 0.0, 1.7),
    ]

    results = add_position_week_z_scores(rows)

    assert results[0].z_score == 1.0
    assert results[1].z_score == -1.0
    assert results[2].z_score is None
