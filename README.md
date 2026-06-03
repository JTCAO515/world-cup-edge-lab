# World Cup Edge Lab

Local football betting-assist backtest lab for win/draw/loss, over/under 2.5, recommendation scoring, bivariate Poisson tuning, and timestamp-based data leakage defense.

## Run Tests

```bash
python3 -m pytest -q
```

## Run CLI Backtest

```bash
PYTHONPATH=src python3 -m football_predictor.cli --data data/ucl_semifinals_sample.json --config configs/default.json --pretty
```

## Run Web Dashboard

```bash
PYTHONPATH=src python3 -m football_predictor.webapp --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

## Current Dataset

The included dataset is a small UEFA Champions League knockout sample used to validate the workflow. Replace it with sourced historical data before drawing statistical conclusions.
