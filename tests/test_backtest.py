from pathlib import Path

from football_predictor.backtest import run_backtest


ROOT = Path(__file__).resolve().parents[1]


def test_backtest_runs_sample_dataset_and_reports_leakage_audit():
    report = run_backtest(
        ROOT / "data" / "ucl_semifinals_sample.json",
        ROOT / "configs" / "default.json",
    )
    assert report["parameter_set"] == "default"
    assert len(report["matches"]) == 4
    assert report["leakage_audit"]["future_records"] >= 1
    assert "brier_wdl" in report["metrics"]


def test_lineup_checkpoint_changes_at_least_one_recommendation_value():
    report = run_backtest(
        ROOT / "data" / "ucl_semifinals_sample.json",
        ROOT / "configs" / "default.json",
    )
    changed = [
        match
        for match in report["matches"]
        if match["checkpoints"]["T-48h"]["best_recommendation"]["value"]
        != match["checkpoints"]["T-60m"]["best_recommendation"]["value"]
    ]
    assert changed
