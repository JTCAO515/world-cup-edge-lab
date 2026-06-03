from football_predictor.scorelines import (
    aggregate_markets,
    bivariate_poisson_matrix,
    independent_poisson_matrix,
)


def test_independent_poisson_matrix_sums_close_to_one():
    matrix = independent_poisson_matrix(1.4, 1.1, max_goals=10)
    assert abs(sum(sum(row) for row in matrix) - 1.0) < 0.01


def test_bivariate_poisson_correlation_lifts_draw_probability():
    independent = aggregate_markets(independent_poisson_matrix(1.2, 1.2, max_goals=10))
    bivariate = aggregate_markets(
        bivariate_poisson_matrix(1.2, 1.2, shared_lambda=0.18, max_goals=10)
    )
    assert bivariate["draw"] > independent["draw"]


def test_aggregate_markets_returns_wdl_and_total_probabilities():
    markets = aggregate_markets(independent_poisson_matrix(1.5, 0.9, max_goals=10))
    assert set(markets) == {"team_a_win", "draw", "team_b_win", "over_2_5", "under_2_5"}
    assert abs(markets["team_a_win"] + markets["draw"] + markets["team_b_win"] - 1.0) < 0.01
    assert abs(markets["over_2_5"] + markets["under_2_5"] - 1.0) < 0.01
