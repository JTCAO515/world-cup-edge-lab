# Football Prediction Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local football betting-assist backtest lab with adjustable parameters, independent and bivariate Poisson scoreline models, recommendation values, and timestamp-based data leakage defense.

**Architecture:** A small Python package separates scoreline probability, odds conversion, feature filtering, recommendation scoring, and backtest orchestration. Tests drive each behavioral unit before implementation. A sample Champions League knockout dataset proves the whole replay loop can run from config.

**Tech Stack:** Python 3.9+, pytest, standard-library JSON/argparse/dataclasses/math.

---

## File Structure

- Create `pyproject.toml`: package and pytest configuration.
- Create `src/football_predictor/__init__.py`: package marker and version.
- Create `src/football_predictor/scorelines.py`: independent Poisson and bivariate Poisson scoreline matrices.
- Create `src/football_predictor/odds.py`: implied probability and overround removal.
- Create `src/football_predictor/timegate.py`: timestamp cutoff filtering and leakage audit events.
- Create `src/football_predictor/recommendations.py`: recommendation value and label calculation.
- Create `src/football_predictor/backtest.py`: load config/data, replay checkpoints, score metrics, produce report data.
- Create `src/football_predictor/cli.py`: command line entry point.
- Create `configs/default.json`: tunable model and recommendation parameters.
- Create `data/ucl_semifinals_sample.json`: small curated replay dataset with timestamped odds, lineups, results, and one deliberate future-data record.
- Create `tests/test_scorelines.py`: scoreline model tests.
- Create `tests/test_odds.py`: odds conversion tests.
- Create `tests/test_timegate.py`: data leakage defense tests.
- Create `tests/test_recommendations.py`: recommendation tests.
- Create `tests/test_backtest.py`: end-to-end replay tests.

### Task 1: Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `src/football_predictor/__init__.py`

- [ ] **Step 1: Create package configuration**

```toml
[project]
name = "football-predictor"
version = "0.1.0"
description = "Local football betting-assist backtest lab"
requires-python = ">=3.9"

[project.scripts]
football-backtest = "football_predictor.cli:main"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package marker**

```python
__version__ = "0.1.0"
```

- [ ] **Step 3: Verify pytest can start**

Run: `python3 -m pytest -q`
Expected: `no tests ran` or no collected tests yet.

### Task 2: Scoreline Models

**Files:**
- Create: `tests/test_scorelines.py`
- Create: `src/football_predictor/scorelines.py`

- [ ] **Step 1: Write failing tests**

```python
from football_predictor.scorelines import (
    aggregate_markets,
    bivariate_poisson_matrix,
    independent_poisson_matrix,
)


def test_independent_poisson_matrix_sums_close_to_one():
    matrix = independent_poisson_matrix(1.4, 1.1, max_goals=10)
    assert abs(sum(sum(row) for row in matrix) - 1.0) < 0.01


def test_bivariate_poisson_correlation_lifts_draw_probability():
    independent = aggregate_markets(independent_poisson_matrix(1.2, 1.2, max_goals=10))
    bivariate = aggregate_markets(
        bivariate_poisson_matrix(1.2, 1.2, shared_lambda=0.18, max_goals=10)
    )
    assert bivariate["draw"] > independent["draw"]


def test_aggregate_markets_returns_wdl_and_total_probabilities():
    markets = aggregate_markets(independent_poisson_matrix(1.5, 0.9, max_goals=10))
    assert set(markets) == {"team_a_win", "draw", "team_b_win", "over_2_5", "under_2_5"}
    assert abs(markets["team_a_win"] + markets["draw"] + markets["team_b_win"] - 1.0) < 0.01
    assert abs(markets["over_2_5"] + markets["under_2_5"] - 1.0) < 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_scorelines.py -q`
Expected: FAIL because `football_predictor.scorelines` does not exist.

- [ ] **Step 3: Implement scoreline functions**

Implement `poisson_pmf`, `independent_poisson_matrix`, `bivariate_poisson_matrix`, and `aggregate_markets` in `src/football_predictor/scorelines.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_scorelines.py -q`
Expected: 3 passed.

### Task 3: Odds Conversion

**Files:**
- Create: `tests/test_odds.py`
- Create: `src/football_predictor/odds.py`

- [ ] **Step 1: Write failing tests**

```python
from football_predictor.odds import decimal_to_probability, remove_overround


def test_decimal_to_probability():
    assert decimal_to_probability(2.0) == 0.5


def test_remove_overround_normalizes_market_probabilities():
    fair = remove_overround({"home": 2.0, "draw": 3.4, "away": 4.0})
    assert abs(sum(fair.values()) - 1.0) < 0.000001
    assert fair["home"] > fair["away"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_odds.py -q`
Expected: FAIL because `football_predictor.odds` does not exist.

- [ ] **Step 3: Implement odds helpers**

Implement decimal odds conversion and proportional overround removal in `src/football_predictor/odds.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_odds.py -q`
Expected: 2 passed.

### Task 4: Timestamp Data Leakage Defense

**Files:**
- Create: `tests/test_timegate.py`
- Create: `src/football_predictor/timegate.py`

- [ ] **Step 1: Write failing tests**

```python
from football_predictor.timegate import filter_available_records


def test_filter_blocks_future_observed_records():
    records = [
        {"id": "old", "observed_at": "2026-04-28T18:00:00+00:00"},
        {"id": "future", "observed_at": "2026-04-28T21:00:00+00:00"},
    ]
    visible, audit = filter_available_records(records, "2026-04-28T20:00:00+00:00")
    assert [record["id"] for record in visible] == ["old"]
    assert audit["future_records"] == 1


def test_filter_blocks_untimestamped_time_sensitive_records():
    visible, audit = filter_available_records(
        [{"id": "lineup", "category": "lineup"}],
        "2026-04-28T20:00:00+00:00",
        time_sensitive_categories={"lineup"},
    )
    assert visible == []
    assert audit["untimestamped_records"] == 1


def test_projection_with_future_effective_at_is_allowed_when_observed_before_checkpoint():
    records = [
        {
            "id": "projected_lineup",
            "category": "lineup",
            "confidence": "projected",
            "observed_at": "2026-04-28T12:00:00+00:00",
            "effective_at": "2026-04-28T19:00:00+00:00",
        }
    ]
    visible, audit = filter_available_records(records, "2026-04-28T18:00:00+00:00")
    assert [record["id"] for record in visible] == ["projected_lineup"]
    assert audit["future_records"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_timegate.py -q`
Expected: FAIL because `football_predictor.timegate` does not exist.

- [ ] **Step 3: Implement timestamp filtering**

Implement ISO timestamp parsing, future-record exclusion, untimestamped time-sensitive exclusion, projection allowance, and audit counters in `src/football_predictor/timegate.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_timegate.py -q`
Expected: 3 passed.

### Task 5: Recommendation Values

**Files:**
- Create: `tests/test_recommendations.py`
- Create: `src/football_predictor/recommendations.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_recommendations.py -q`
Expected: FAIL because `football_predictor.recommendations` does not exist.

- [ ] **Step 3: Implement recommendation scoring**

Implement edge scoring, confidence multipliers, clamping, rounded output, and labels in `src/football_predictor/recommendations.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_recommendations.py -q`
Expected: 2 passed.

### Task 6: Backtest Engine and Sample Dataset

**Files:**
- Create: `tests/test_backtest.py`
- Create: `src/football_predictor/backtest.py`
- Create: `configs/default.json`
- Create: `data/ucl_semifinals_sample.json`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_backtest.py -q`
Expected: FAIL because `football_predictor.backtest`, config, and sample data do not exist.

- [ ] **Step 3: Create config and sample data**

Create a default config with bivariate Poisson selected and a sample Champions League semi-final dataset containing four timestamped matches, checkpoint odds, lineup impacts, final 90-minute scores, and one deliberate future-dated injury record.

- [ ] **Step 4: Implement backtest orchestration**

Implement config loading, checkpoint replay, timestamp filtering, expected-goals adjustment, scoreline aggregation, market probability comparison, recommendation selection, Brier metrics, and leakage audit aggregation in `src/football_predictor/backtest.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_backtest.py -q`
Expected: 2 passed.

### Task 7: CLI Report

**Files:**
- Create: `src/football_predictor/cli.py`

- [ ] **Step 1: Add CLI behavior through backtest test coverage**

Use `run_backtest` as the tested core. The CLI only parses arguments and prints JSON, so no separate behavioral test is required in the first version.

- [ ] **Step 2: Implement CLI**

Implement `main()` with `--data`, `--config`, and `--pretty` arguments.

- [ ] **Step 3: Run CLI smoke test**

Run: `PYTHONPATH=src python3 -m football_predictor.cli --data data/ucl_semifinals_sample.json --config configs/default.json --pretty`
Expected: JSON report containing `parameter_set`, `matches`, `metrics`, and `leakage_audit`.

### Task 8: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run all tests**

Run: `python3 -m pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Run sample report**

Run: `PYTHONPATH=src python3 -m football_predictor.cli --data data/ucl_semifinals_sample.json --config configs/default.json --pretty`
Expected: the command exits 0 and prints a JSON backtest report.

- [ ] **Step 3: Review generated files**

Run: `find . -maxdepth 3 -type f | sort`
Expected: source, tests, config, data, spec, and plan files are present.
