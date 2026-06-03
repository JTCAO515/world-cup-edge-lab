from football_predictor.odds import decimal_to_probability, remove_overround


def test_decimal_to_probability():
    assert decimal_to_probability(2.0) == 0.5


def test_remove_overround_normalizes_market_probabilities():
    fair = remove_overround({"home": 2.0, "draw": 3.4, "away": 4.0})
    assert abs(sum(fair.values()) - 1.0) < 0.000001
    assert fair["home"] > fair["away"]
