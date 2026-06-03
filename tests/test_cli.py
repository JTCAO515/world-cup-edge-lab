import json
from pathlib import Path

from football_predictor.cli import main


ROOT = Path(__file__).resolve().parents[1]


def test_cli_prints_backtest_report(capsys):
    exit_code = main(
        [
            "--data",
            str(ROOT / "data" / "ucl_semifinals_sample.json"),
            "--config",
            str(ROOT / "configs" / "default.json"),
            "--pretty",
        ]
    )
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert exit_code == 0
    assert report["parameter_set"] == "default"
    assert "metrics" in report
