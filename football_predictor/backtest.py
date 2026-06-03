import json
from pathlib import Path

from football_predictor.odds import remove_overround
from football_predictor.recommendations import score_recommendation
from football_predictor.scorelines import (
    aggregate_markets,
    bivariate_poisson_matrix,
    independent_poisson_matrix,
)
from football_predictor.timegate import filter_available_records, merge_audits, parse_timestamp


WDL_KEYS = ("team_a_win", "draw", "team_b_win")
TOTAL_KEYS = ("over_2_5", "under_2_5")


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def merge_config(config, overrides=None):
    merged = dict(config)
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def _latest(records):
    if not records:
        return None
    return max(records, key=lambda record: parse_timestamp(record.get("observed_at")).timestamp())


def _clamp_xg(value, minimum_xg):
    return max(minimum_xg, value)


def _scoreline_matrix(team_a_xg, team_b_xg, config):
    max_goals = int(config.get("max_goals", 10))
    if config.get("scoreline_model") == "bivariate_poisson":
        shared_lambda = min(
            float(config.get("shared_lambda", 0.0)),
            team_a_xg,
            team_b_xg,
        )
        return bivariate_poisson_matrix(
            team_a_xg,
            team_b_xg,
            shared_lambda=shared_lambda,
            max_goals=max_goals,
        )
    return independent_poisson_matrix(team_a_xg, team_b_xg, max_goals=max_goals)


def _market_probabilities(odds_snapshot):
    if odds_snapshot is None:
        return {}
    probabilities = {}
    if "h2h" in odds_snapshot:
        probabilities.update(remove_overround(odds_snapshot["h2h"]))
    if "totals" in odds_snapshot:
        probabilities.update(remove_overround(odds_snapshot["totals"]))
    return probabilities


def _market_name(outcome):
    if outcome in WDL_KEYS:
        return "h2h"
    return "totals"


def _round_probabilities(probabilities):
    return {key: round(value, 6) for key, value in probabilities.items()}


def _build_recommendations(model_probabilities, market_probabilities, lineup_status, checkpoint_name, config):
    recommendations = []
    lineup_confidence = config["lineup_confidence"].get(
        lineup_status,
        config["lineup_confidence"]["unknown"],
    )
    data_freshness = config["data_freshness"].get(checkpoint_name, 0.8)

    for outcome, model_probability in model_probabilities.items():
        if outcome not in market_probabilities:
            continue
        recommendation = score_recommendation(
            model_probability=model_probability,
            market_probability=market_probabilities[outcome],
            lineup_confidence=lineup_confidence,
            data_freshness=data_freshness,
            model_confidence=config.get("model_confidence", 1.0),
            risk_modifier=config.get("risk_modifier", 1.0),
        )
        recommendation.update(
            {
                "market": _market_name(outcome),
                "outcome": outcome,
                "model_probability": round(model_probability, 6),
                "market_probability": round(market_probabilities[outcome], 6),
                "reason": (
                    "Model edge versus de-vigged market probability, adjusted by "
                    f"{lineup_status} lineup confidence."
                ),
            }
        )
        recommendations.append(recommendation)

    if not recommendations:
        return {
            "market": None,
            "outcome": None,
            "value": None,
            "label": "unavailable",
            "edge": None,
            "reason": "No usable market odds were available at this checkpoint.",
        }

    return max(recommendations, key=lambda item: (item["value"], item["edge"]))


def _visible_inputs(match, checkpoint_time):
    lineups, lineup_audit = filter_available_records(
        match.get("lineup_updates", []),
        checkpoint_time,
    )
    odds, odds_audit = filter_available_records(
        match.get("odds_snapshots", []),
        checkpoint_time,
    )
    injuries, injury_audit = filter_available_records(
        match.get("injury_updates", []),
        checkpoint_time,
    )
    return lineups, odds, injuries, merge_audits(lineup_audit, odds_audit, injury_audit)


def _checkpoint_report(match, checkpoint, config):
    lineups, odds, injuries, audit = _visible_inputs(match, checkpoint["time"])
    latest_lineup = _latest(lineups)
    latest_odds = _latest(odds)

    impact_multiplier = float(config.get("lineup_impact_multiplier", 1.0))
    minimum_xg = float(config.get("minimum_xg", 0.2))
    team_a_xg = float(match["base_xg"]["team_a"])
    team_b_xg = float(match["base_xg"]["team_b"])

    if latest_lineup is not None:
        team_a_xg += float(latest_lineup.get("team_a_xg_delta", 0.0)) * impact_multiplier
        team_b_xg += float(latest_lineup.get("team_b_xg_delta", 0.0)) * impact_multiplier

    for injury in injuries:
        team_a_xg += float(injury.get("team_a_xg_delta", 0.0)) * impact_multiplier
        team_b_xg += float(injury.get("team_b_xg_delta", 0.0)) * impact_multiplier

    team_a_xg = _clamp_xg(team_a_xg, minimum_xg)
    team_b_xg = _clamp_xg(team_b_xg, minimum_xg)
    matrix = _scoreline_matrix(team_a_xg, team_b_xg, config)
    model_probabilities = aggregate_markets(matrix)
    market_probabilities = _market_probabilities(latest_odds)
    lineup_status = latest_lineup.get("confidence", "unknown") if latest_lineup else "unknown"

    return {
        "time": checkpoint["time"],
        "expected_goals": {
            "team_a": round(team_a_xg, 4),
            "team_b": round(team_b_xg, 4),
        },
        "lineup_status": lineup_status,
        "lineup_note": latest_lineup.get("note") if latest_lineup else None,
        "probabilities": _round_probabilities(model_probabilities),
        "market_probabilities": _round_probabilities(market_probabilities),
        "best_recommendation": _build_recommendations(
            model_probabilities,
            market_probabilities,
            lineup_status,
            checkpoint["name"],
            config,
        ),
        "leakage_audit": audit,
    }


def _actual_wdl(result):
    if result["team_a_goals"] > result["team_b_goals"]:
        return "team_a_win"
    if result["team_a_goals"] == result["team_b_goals"]:
        return "draw"
    return "team_b_win"


def _actual_total(result):
    if result["team_a_goals"] + result["team_b_goals"] > 2.5:
        return "over_2_5"
    return "under_2_5"


def _brier(probabilities, actual_key, keys):
    return sum(
        (probabilities[key] - (1.0 if key == actual_key else 0.0)) ** 2
        for key in keys
    )


def _average(values):
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def run_backtest(data_path, config_path, config_overrides=None):
    dataset = load_json(data_path)
    config = merge_config(load_json(config_path), config_overrides)
    matches = []
    audit = {
        "future_records": 0,
        "untimestamped_records": 0,
        "visible_records": 0,
    }
    wdl_briers = []
    total_briers = []

    for match in dataset["matches"]:
        checkpoint_reports = {}
        for checkpoint in match["checkpoints"]:
            report = _checkpoint_report(match, checkpoint, config)
            checkpoint_reports[checkpoint["name"]] = report
            audit = merge_audits(audit, report["leakage_audit"])

        final_checkpoint_name = match["checkpoints"][-1]["name"]
        final_probabilities = checkpoint_reports[final_checkpoint_name]["probabilities"]
        wdl_briers.append(_brier(final_probabilities, _actual_wdl(match["result"]), WDL_KEYS))
        total_briers.append(_brier(final_probabilities, _actual_total(match["result"]), TOTAL_KEYS))

        matches.append(
            {
                "id": match["id"],
                "team_a": match["team_a"],
                "team_b": match["team_b"],
                "result": match["result"],
                "checkpoints": checkpoint_reports,
            }
        )

    return {
        "parameter_set": config["parameter_set"],
        "scoreline_model": config.get("scoreline_model", "independent_poisson"),
        "effective_config": config,
        "matches": matches,
        "metrics": {
            "brier_wdl": _average(wdl_briers),
            "brier_over_under_2_5": _average(total_briers),
        },
        "leakage_audit": audit,
    }
