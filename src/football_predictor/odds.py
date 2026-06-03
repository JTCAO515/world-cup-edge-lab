def decimal_to_probability(decimal_odds):
    if decimal_odds <= 1:
        raise ValueError("decimal_odds must be greater than 1")
    return 1.0 / decimal_odds


def remove_overround(decimal_odds_by_outcome):
    implied = {
        outcome: decimal_to_probability(decimal_odds)
        for outcome, decimal_odds in decimal_odds_by_outcome.items()
    }
    total = sum(implied.values())
    if total <= 0:
        raise ValueError("market has no implied probability")
    return {outcome: probability / total for outcome, probability in implied.items()}
