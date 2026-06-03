def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def recommendation_label(value):
    if value >= 85:
        return "strong"
    if value >= 70:
        return "medium"
    if value >= 55:
        return "weak"
    if value >= 40:
        return "watch"
    return "avoid"


def score_recommendation(
    model_probability,
    market_probability,
    lineup_confidence=1.0,
    data_freshness=1.0,
    model_confidence=1.0,
    risk_modifier=1.0,
):
    edge = round(model_probability - market_probability, 6)
    confidence = (
        clamp(lineup_confidence, 0.0, 1.0)
        * clamp(data_freshness, 0.0, 1.0)
        * clamp(model_confidence, 0.0, 1.0)
        * clamp(risk_modifier, 0.0, 1.0)
    )
    edge_score = 60.0 + edge * 500.0
    value = int(round(clamp(edge_score * confidence, 0.0, 100.0)))

    return {
        "edge": edge,
        "value": value,
        "label": recommendation_label(value),
    }
