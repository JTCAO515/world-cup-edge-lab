# World Cup Betting Prediction Backtest Design

## Goal

Build a betting-assist prediction lab for football matches. The first version focuses on replaying Champions League knockout matches to tune parameters before applying the same workflow to World Cup matches.

The product should predict:

- 90-minute win/draw/loss probabilities.
- Over/under probabilities, starting with over/under 2.5 goals.
- A recommendation value that says whether a market is worth acting on.

The recommendation value is not the same as probability. It should combine model edge, market price, lineup confidence, data freshness, and risk.

## First Version Scope

The first version is a local backtesting and parameter-tuning tool.

It will:

- Store historical match inputs for Champions League knockout matches.
- Produce baseline predictions before lineups are known.
- Re-run predictions after confirmed lineups are available.
- Compare predictions against final results and market odds.
- Score each run with probability and betting-assist metrics.
- Let parameters be adjusted without changing prediction code.

It will not:

- Execute real bets.
- Claim guaranteed profit.
- Depend on live World Cup data before the backtest workflow is stable.
- Treat extra time or penalties as part of win/draw/loss unless explicitly configured.

## Match Timeline

Each match is replayed through checkpoints:

- `T-48h`: baseline prediction using team strength, recent form, expected injuries, odds, and context.
- `T-6h`: refresh injuries, weather, odds, and match situation.
- `T-75m` to `T-60m`: confirmed lineups trigger a major recalculation.
- `T-30m`: final recommendation check using latest odds.
- `FT`: compare with 90-minute result and settled over/under result.

The same timeline can later be used for World Cup live monitoring.

## Data Inputs

### Core Football Data

Primary candidates:

- Sportmonks: fixtures, lineups, formations, sidelined players, statistics, odds, xG where available.
- API-Football: fixtures, lineups, injuries, odds, and statistics as a fallback.
- FIFA official sources: World Cup schedule, official squads, venue, and confirmed match information.

Historical Champions League backtests can start with manually curated CSV/JSON data if API access is not yet available.

### Market Data

Primary candidates:

- The Odds API for `h2h`, `totals`, and potentially `spreads`.
- Sportmonks or API-Football odds if already used for football data.
- Polymarket as an optional prediction-market signal when relevant markets exist.

The system should store raw odds, bookmaker, market, timestamp, and converted implied probability.

### Context Data

Inputs should include:

- Rest days.
- Home/away or neutral venue.
- Match leg and aggregate score for knockout ties.
- Need-to-win state.
- Weather when relevant.
- Known tactical and lineup notes.

## Prediction Model

The first version should use an interpretable model rather than a black-box model.

### Team Strength

Each team receives attack and defense strength values. These can initially be manually seeded or derived from recent performance.

Useful inputs:

- Recent goals for and against.
- Recent xG and xGA where available.
- Opponent strength adjustment.
- European competition performance.
- Domestic league strength adjustment.

### Expected Goals

The model estimates:

- Home/team A expected goals.
- Away/team B expected goals.

Expected goals are adjusted by:

- Team attack and defense strength.
- Venue advantage.
- Recent form.
- Lineup changes.
- Tactical matchup.
- Match situation.
- Weather and tempo risk.

### Win/Draw/Loss

Use the expected goals values to generate scoreline probabilities with a Poisson-style distribution. From scorelines, aggregate:

- Team A win probability.
- Draw probability.
- Team B win probability.

The first implementation should support two scoreline models:

- Independent Poisson as a simple baseline.
- Bivariate Poisson with a configurable correlation parameter.

The bivariate model is preferred for serious backtests because football scores are not fully independent. Match state, tempo, and tactical incentives can make some low-score draws more common than an independent Poisson model predicts. The correlation parameter should let the system increase or decrease shared scoring-state effects, especially around draw-heavy scorelines such as 0-0 and 1-1.

The selected scoreline model and its parameters must be recorded in every backtest run.

### Over/Under

Use total goal distribution from the same scoreline matrix.

The first supported market is:

- Over 2.5 goals.
- Under 2.5 goals.

The design should allow later support for 1.5, 3.5, Asian totals, and team totals.

## Lineup Adjustment

Confirmed lineups should change both probability and confidence.

Player impact should consider:

- Position.
- Whether the player is a projected starter.
- Attack, defense, and goalkeeper value.
- Fitness uncertainty.
- Replacement quality.
- Tactical role.

Examples:

- Missing starting goalkeeper increases opponent expected goals.
- Missing center back increases opponent scoring probability and may increase over probability.
- Missing elite forward decreases own expected goals.
- More conservative formation lowers tempo and total-goals expectation.

Lineup status should be tracked as:

- Unknown.
- Projected.
- Confirmed.
- Unexpected rotation.

## Recommendation Value

For each candidate bet, calculate:

```text
model_edge = model_probability - market_implied_probability
recommendation_value = edge_score
  * lineup_confidence
  * data_freshness
  * model_confidence
  * risk_modifier
```

The display labels are:

- 85-100: Strong recommendation.
- 70-84: Medium recommendation.
- 55-69: Weak recommendation.
- 40-54: Watch only.
- 0-39: Avoid.

The output should include a compact explanation:

- Main reason for the recommendation.
- Market edge.
- Key lineup change.
- Main risk.
- Whether the recommendation changed after confirmed lineups.

## Parameter Tuning

Parameters should live in a config file.

Initial parameter groups:

- Team strength weights.
- Recent form weights.
- xG weights.
- Venue advantage.
- Scoreline model selection.
- Bivariate Poisson correlation parameter.
- Lineup impact weights by position.
- Tactical matchup weights.
- Knockout match conservatism.
- Odds edge thresholds.
- Recommendation score thresholds.
- Risk penalties.

Backtest runs should be reproducible. Each run records:

- Parameter set name.
- Match set.
- Prediction checkpoint.
- Inputs used.
- Probabilities.
- Recommendations.
- Scores.

## Backtest Metrics

Use several metrics because no single score is enough.

Probability quality:

- Brier score for win/draw/loss.
- Log loss for win/draw/loss.
- Brier score for over/under.

Betting-assist quality:

- Closing line value when historical closing odds are available.
- Flat-stake return on investment for recommendations.
- Recommendation hit rate by label.
- Average edge by label.

Operational quality:

- How often recommendations change after lineups.
- Whether high recommendation values are too frequent.
- Whether the system overreacts to lineup changes.

## Architecture

### Data Layer

Responsibilities:

- Load match datasets.
- Normalize team names and player names.
- Store odds snapshots.
- Store lineup snapshots.
- Store match results.
- Store `observed_at` and `effective_at` timestamps for every input that can change over time.

### Feature Layer

Responsibilities:

- Convert raw data into model features.
- Calculate rest, form, strength, lineup impact, and market implied probability.
- Track feature freshness and confidence.
- Reject features whose source timestamp is after the replay checkpoint.

### Prediction Layer

Responsibilities:

- Estimate expected goals.
- Generate scoreline probabilities with the configured scoreline model.
- Aggregate win/draw/loss and over/under probabilities.

### Recommendation Layer

Responsibilities:

- Compare model probabilities with market probabilities.
- Apply confidence and risk modifiers.
- Assign recommendation labels.
- Produce human-readable reasons.

### Backtest Layer

Responsibilities:

- Replay matches across checkpoints.
- Run parameter sets.
- Score results.
- Export reports.
- Enforce timestamp cutoffs so a checkpoint can only read data available at or before that checkpoint.

## Data Leakage Defense

Backtest credibility depends on preventing future information from entering earlier checkpoints.

Every time-sensitive record must include:

- `observed_at`: when the system saw the data.
- `effective_at`: when the real-world fact became valid, if different from `observed_at`.
- `source`: where the record came from.
- `confidence`: confirmed, projected, estimated, or disputed.

The backtest engine must enforce this rule:

```text
record.observed_at <= checkpoint_time
```

If a record has an `effective_at` later than the checkpoint, it must also be excluded unless the record represents a projection that was explicitly available before the checkpoint.

Examples:

- A final score cannot be used in `T-48h`, `T-6h`, `T-60m`, or `T-30m` feature generation.
- A confirmed lineup published at `T-65m` cannot affect a `T-6h` prediction.
- A post-match injury report cannot be used as a pre-match injury input.
- Closing odds can be used for post-run evaluation, but not for earlier recommendation generation unless the checkpoint is after the odds timestamp.

The system should fail closed. If a record has no timestamp and belongs to a time-sensitive category, it should be excluded from model input and flagged in the report.

The report should include a leakage audit section listing:

- Number of excluded future records.
- Number of excluded untimestamped records.
- Any match that could not be scored because required timestamps were missing.

## Initial Dataset Plan

Start with Champions League knockout matches because they resemble World Cup knockout incentives more than league matches.

Suggested first dataset:

- 2025/26 Champions League semi-finals.
- Then expand to 2025/26 quarter-finals.
- Then expand across multiple Champions League seasons.

The four semi-final matches are useful as an end-to-end smoke test, not as statistical proof.

## Error Handling

The system should degrade gracefully:

- If odds are missing, output model probability but mark recommendation as unavailable.
- If lineups are missing, use projected lineup and lower confidence.
- If player impact is unknown, fall back to team-level adjustment.
- If data timestamps are stale, reduce recommendation value.
- If time-sensitive data has no timestamp, exclude it from prediction inputs and report the exclusion.
- If future-dated data is requested by a checkpoint, block it and report a leakage-prevention event.
- If team names cannot be matched confidently, stop the run for that match and ask for mapping.

## Testing

The first implementation should include tests for:

- Odds implied-probability conversion.
- Overround removal.
- Poisson scoreline aggregation.
- Bivariate Poisson scoreline aggregation.
- Draw-probability behavior under different correlation parameters.
- Recommendation value calculation.
- Lineup impact calculation.
- Backtest metric calculation.
- Timestamp cutoff enforcement.
- Future-result leakage prevention.
- Untimestamped time-sensitive data exclusion.

Manual verification should include:

- A sample Champions League semi-final replay.
- Before-lineup and after-lineup prediction comparison.
- A parameter adjustment that visibly changes output.
- A deliberate future-data fixture proving the backtest engine blocks leaked information.

## Success Criteria

The first version is successful when:

- A user can run a local backtest over a curated Champions League knockout dataset.
- The output includes win/draw/loss, over/under, recommendation value, and explanation.
- Parameter changes can be made in config and reflected in the next run.
- Lineup-confirmed checkpoints can change recommendations in a traceable way.
- Scoreline model changes, including bivariate Poisson correlation changes, can be tested from config.
- Checkpoint predictions cannot access future results, future lineups, or future injury updates.
- The report shows probability metrics and betting-assist metrics.
- The report includes a leakage audit.
