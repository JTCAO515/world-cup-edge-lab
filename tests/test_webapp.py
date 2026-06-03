from pathlib import Path

from football_predictor.backtest import run_backtest
from football_predictor.webapp import build_report_payload


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "ucl_semifinals_sample.json"
CONFIG_PATH = ROOT / "configs" / "default.json"


def test_run_backtest_accepts_config_overrides():
    default = run_backtest(DATA_PATH, CONFIG_PATH)
    tuned = run_backtest(DATA_PATH, CONFIG_PATH, {"shared_lambda": 0.3})

    default_draw = default["matches"][0]["checkpoints"]["T-60m"]["probabilities"]["draw"]
    tuned_draw = tuned["matches"][0]["checkpoints"]["T-60m"]["probabilities"]["draw"]

    assert tuned["effective_config"]["shared_lambda"] == 0.3
    assert tuned_draw > default_draw


def test_build_report_payload_returns_report_and_effective_config():
    payload = build_report_payload({"risk_modifier": 0.7, "lineup_impact_multiplier": 1.2})

    assert payload["report"]["parameter_set"] == "default"
    assert payload["effective_config"]["risk_modifier"] == 0.7
    assert payload["effective_config"]["lineup_impact_multiplier"] == 1.2
