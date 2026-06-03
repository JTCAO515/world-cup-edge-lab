import math


def poisson_pmf(goal_count, expected_goals):
    if goal_count < 0:
        return 0.0
    if expected_goals < 0:
        raise ValueError("expected_goals must be non-negative")
    return math.exp(-expected_goals) * expected_goals**goal_count / math.factorial(goal_count)


def _normalize_matrix(matrix):
    total = sum(sum(row) for row in matrix)
    if total <= 0:
        raise ValueError("scoreline matrix has no probability mass")
    return [[cell / total for cell in row] for row in matrix]


def independent_poisson_matrix(team_a_xg, team_b_xg, max_goals=10):
    matrix = []
    for team_a_goals in range(max_goals + 1):
        row = []
        team_a_probability = poisson_pmf(team_a_goals, team_a_xg)
        for team_b_goals in range(max_goals + 1):
            row.append(team_a_probability * poisson_pmf(team_b_goals, team_b_xg))
        matrix.append(row)
    return _normalize_matrix(matrix)


def bivariate_poisson_matrix(team_a_xg, team_b_xg, shared_lambda=0.0, max_goals=10):
    if shared_lambda < 0:
        raise ValueError("shared_lambda must be non-negative")
    if shared_lambda > min(team_a_xg, team_b_xg):
        raise ValueError("shared_lambda cannot exceed either team's expected goals")

    independent_a = team_a_xg - shared_lambda
    independent_b = team_b_xg - shared_lambda
    matrix = []

    for team_a_goals in range(max_goals + 1):
        row = []
        for team_b_goals in range(max_goals + 1):
            probability = 0.0
            for shared_goals in range(min(team_a_goals, team_b_goals) + 1):
                probability += (
                    poisson_pmf(shared_goals, shared_lambda)
                    * poisson_pmf(team_a_goals - shared_goals, independent_a)
                    * poisson_pmf(team_b_goals - shared_goals, independent_b)
                )
            row.append(probability)
        matrix.append(row)

    return _normalize_matrix(matrix)


def aggregate_markets(matrix):
    team_a_win = 0.0
    draw = 0.0
    team_b_win = 0.0
    over_2_5 = 0.0
    under_2_5 = 0.0

    for team_a_goals, row in enumerate(matrix):
        for team_b_goals, probability in enumerate(row):
            if team_a_goals > team_b_goals:
                team_a_win += probability
            elif team_a_goals == team_b_goals:
                draw += probability
            else:
                team_b_win += probability

            if team_a_goals + team_b_goals > 2.5:
                over_2_5 += probability
            else:
                under_2_5 += probability

    return {
        "team_a_win": team_a_win,
        "draw": draw,
        "team_b_win": team_b_win,
        "over_2_5": over_2_5,
        "under_2_5": under_2_5,
    }
