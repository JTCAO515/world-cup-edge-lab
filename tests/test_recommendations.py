from football_predictor.recommendations import recommendation_label, score_recommendation


def test_recommendation_score_uses_edge_and_confidence():
    result = score_recommendation(
        model_probability=0.58,
        market_probability=0.50,
        lineup_confidence=0.9,
        data_freshness=0.95,
        model_confidence=0.85,
        risk_modifier=0.8,
    )
    assert 55 <= result["value"] <= 84
    assert result["edge"] == 0.08


def test_recommendation_label_thresholds():
    assert recommendation_label(90) == "strong"
    assert recommendation_label(75) == "medium"
    assert recommendation_label(60) == "weak"
    assert recommendation_label(45) == "watch"
    assert recommendation_label(20) == "avoid"
