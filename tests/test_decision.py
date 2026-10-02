from yahoo_waiver_assistant.decision import Action, DecisionInputs, recommend


def base_inputs(**overrides):
    values = dict(
        add_player="Candidate RB",
        replace_player="Current RB",
        candidate_expected_points=11.0,
        replacement_expected_points=7.0,
        lineup_probability=0.75,
        free_agency_probability=0.25,
        expected_winning_faab=6,
        max_justified_faab=10,
        remaining_faab=84,
        weekly_acquisitions_remaining=5,
        candidate_score=75,
        confidence="Medium",
    )
    values.update(overrides)
    return DecisionInputs(**values)


def test_claim_when_upgrade_is_material_and_clear_probability_is_low():
    result = recommend(base_inputs())
    assert result.action == Action.CLAIM
    assert result.bid == 6
    assert result.max_bid == 10
    assert result.expected_lineup_improvement == 3.0


def test_wait_when_player_is_likely_to_clear():
    result = recommend(base_inputs(free_agency_probability=0.80))
    assert result.action == Action.WAIT
    assert result.bid == 0


def test_pass_on_marginal_upgrade():
    result = recommend(
        base_inputs(
            candidate_expected_points=7.5,
            replacement_expected_points=7.0,
            lineup_probability=0.5,
        )
    )
    assert result.action == Action.PASS


def test_open_spot_can_justify_upside_stash():
    result = recommend(
        base_inputs(
            replace_player="Open Spot",
            candidate_expected_points=7.0,
            replacement_expected_points=7.0,
            lineup_probability=0.0,
            free_agency_probability=0.45,
            open_roster_spot=True,
            upside_stash_score=85,
            candidate_score=72,
            expected_winning_faab=2,
            max_justified_faab=4,
        )
    )
    assert result.action == Action.VALUE_CLAIM
    assert result.bid == 2
