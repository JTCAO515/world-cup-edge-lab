const outcomeLabels = {
  team_a_win: "主胜",
  draw: "平局",
  team_b_win: "客胜",
  over_2_5: "大 2.5",
  under_2_5: "小 2.5"
};

const marketLabels = {
  h2h: "胜平负",
  totals: "大小球"
};

const labelText = {
  strong: "强推",
  medium: "中推",
  weak: "弱推",
  watch: "观望",
  avoid: "避免",
  unavailable: "不可用"
};

const state = {
  report: null,
  effectiveConfig: null,
  currentView: "prediction",
  currentMatchIndex: 0,
  currentCheckpoint: "T-60m",
  controls: {
    scoreline_model: "bivariate_poisson",
    shared_lambda: 0.14,
    lineup_impact_multiplier: 1,
    risk_modifier: 0.86,
    model_confidence: 0.84
  }
};

let debounceTimer = null;

function formatPercent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatSignedPercent(value) {
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${(value * 100).toFixed(2)}%`;
}

function scoreLabel(value) {
  if (value >= 85) return "strong";
  if (value >= 70) return "medium";
  if (value >= 55) return "weak";
  if (value >= 40) return "watch";
  return "avoid";
}

function scoreRecommendation(modelProbability, marketProbability, checkpointName, lineupStatus) {
  const config = state.effectiveConfig;
  const lineupConfidence = config.lineup_confidence[lineupStatus] || config.lineup_confidence.unknown;
  const dataFreshness = config.data_freshness[checkpointName] || 0.8;
  const edge = modelProbability - marketProbability;
  const confidence = lineupConfidence * dataFreshness * config.model_confidence * config.risk_modifier;
  const value = Math.max(0, Math.min(100, Math.round((60 + edge * 500) * confidence)));
  const label = scoreLabel(value);
  return { edge, value, label };
}

async function fetchReport() {
  document.getElementById("runStatus").textContent = "计算中";
  const response = await fetch("/api/backtest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config_overrides: state.controls })
  });
  const payload = await response.json();
  state.report = payload.report;
  state.effectiveConfig = payload.effective_config;
  document.getElementById("runStatus").textContent = "已同步";
  render();
}

function currentMatch() {
  return state.report.matches[state.currentMatchIndex];
}

function checkpointNames(match) {
  return Object.keys(match.checkpoints);
}

function currentCheckpointReport() {
  const match = currentMatch();
  const names = checkpointNames(match);
  if (!match.checkpoints[state.currentCheckpoint]) {
    state.currentCheckpoint = names[names.length - 1];
  }
  return match.checkpoints[state.currentCheckpoint];
}

function marketForOutcome(outcome) {
  return outcome.includes("2_5") ? "totals" : "h2h";
}

function recommendationRows(checkpoint) {
  return Object.entries(checkpoint.probabilities)
    .filter(([outcome]) => checkpoint.market_probabilities[outcome] !== undefined)
    .map(([outcome, modelProbability]) => {
      const marketProbability = checkpoint.market_probabilities[outcome];
      const recommendation = scoreRecommendation(
        modelProbability,
        marketProbability,
        state.currentCheckpoint,
        checkpoint.lineup_status
      );
      return {
        market: marketForOutcome(outcome),
        outcome,
        modelProbability,
        marketProbability,
        ...recommendation
      };
    })
    .sort((a, b) => b.value - a.value || b.edge - a.edge);
}

function bestByMarket(rows, market) {
  return rows.filter((row) => row.market === market)[0];
}

function formatBackendRecommendation(recommendation) {
  if (!recommendation || !recommendation.outcome) {
    return "无可用盘口";
  }
  const market = marketLabels[recommendation.market] || recommendation.market;
  const outcome = outcomeLabels[recommendation.outcome] || recommendation.outcome;
  const label = labelText[recommendation.label] || recommendation.label;
  return `${market} · ${outcome} · ${label} ${recommendation.value}`;
}

function recommendationChanged(before, after) {
  if (!before || !after) return false;
  return before.outcome !== after.outcome || before.value !== after.value || before.label !== after.label;
}

function bindNavigation() {
  document.querySelectorAll(".tabs [data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.currentView = button.dataset.view;
      render();
    });
  });
}

function renderActiveView() {
  document.querySelectorAll(".tabs [data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === state.currentView);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("hidden", view.id !== `${state.currentView}View`);
  });
}

function renderMatches() {
  const list = document.getElementById("matchList");
  list.innerHTML = "";
  state.report.matches.forEach((match, index) => {
    const names = checkpointNames(match);
    const lastCheckpoint = names[names.length - 1];
    const button = document.createElement("button");
    button.type = "button";
    button.className = `match-button${index === state.currentMatchIndex ? " active" : ""}`;
    button.innerHTML = `<strong>${match.team_a} vs ${match.team_b}</strong><span><em>${lastCheckpoint}</em><em>${match.result.team_a_goals}-${match.result.team_b_goals}</em></span>`;
    button.addEventListener("click", () => {
      state.currentMatchIndex = index;
      state.currentCheckpoint = lastCheckpoint;
      render();
    });
    list.appendChild(button);
  });
}

function renderCheckpointTabs(match) {
  const tabs = document.getElementById("checkpointTabs");
  tabs.innerHTML = "";
  checkpointNames(match).forEach((name) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = name;
    button.className = name === state.currentCheckpoint ? "active" : "";
    button.addEventListener("click", () => {
      state.currentCheckpoint = name;
      render();
    });
    tabs.appendChild(button);
  });
}

function renderProbabilities(checkpoint) {
  const rows = [
    ["team_a_win", "主胜"],
    ["draw", "平局"],
    ["team_b_win", "客胜"],
    ["over_2_5", "大 2.5"],
    ["under_2_5", "小 2.5"]
  ];
  document.getElementById("probabilityRows").innerHTML = rows
    .map(([key, label]) => {
      const value = checkpoint.probabilities[key];
      const fillClass = key.includes("2_5") ? "track-fill total" : "track-fill";
      return `<div class="prob-row"><span>${label}</span><div class="track-bar"><div class="${fillClass}" style="width:${Math.max(4, value * 100)}%"></div></div><strong>${formatPercent(value)}</strong></div>`;
    })
    .join("");
}

function renderRecommendations(rows) {
  document.getElementById("recommendationCount").textContent = `${rows.length} 个方向`;
  document.getElementById("recommendationRows").innerHTML = rows
    .map((row) => {
      return `<tr><td>${marketLabels[row.market]}</td><td>${outcomeLabels[row.outcome]}</td><td>${formatSignedPercent(row.edge)}</td><td><span class="rec-pill ${row.label}">${labelText[row.label]} ${row.value}</span></td></tr>`;
    })
    .join("");
}

function renderTimeline(match) {
  const timeline = document.getElementById("timeline");
  timeline.innerHTML = checkpointNames(match)
    .map((name) => {
      const checkpoint = match.checkpoints[name];
      const rec = checkpoint.best_recommendation;
      const direction = rec.outcome ? outcomeLabels[rec.outcome] : "无盘口";
      const label = rec.label ? labelText[rec.label] || rec.label : "不可用";
      return `<div class="timeline-row"><time>${name}</time><div>${direction} · ${label}${rec.value === null ? "" : ` ${rec.value}`} · ${checkpoint.lineup_status}</div></div>`;
    })
    .join("");
}

function renderBacktestView() {
  const report = state.report;
  const matches = report.matches;
  const changes = matches.filter((match) => {
    const before = match.checkpoints["T-48h"] && match.checkpoints["T-48h"].best_recommendation;
    const after = match.checkpoints["T-60m"] && match.checkpoints["T-60m"].best_recommendation;
    return recommendationChanged(before, after);
  });

  document.getElementById("backtestBrierWdl").textContent = report.metrics.brier_wdl.toFixed(4);
  document.getElementById("backtestBrierTotal").textContent = report.metrics.brier_over_under_2_5.toFixed(4);
  document.getElementById("recommendationChanges").textContent = `${changes.length}/${matches.length}`;
  document.getElementById("backtestLeaks").textContent = report.leakage_audit.future_records;

  document.getElementById("backtestRows").innerHTML = matches
    .map((match) => {
      const before = match.checkpoints["T-48h"] && match.checkpoints["T-48h"].best_recommendation;
      const after = match.checkpoints["T-60m"] && match.checkpoints["T-60m"].best_recommendation;
      const changed = recommendationChanged(before, after);
      return `<tr>
        <td><strong>${match.team_a}</strong><br><span class="muted">vs ${match.team_b}</span></td>
        <td>${match.result.team_a_goals}-${match.result.team_b_goals}</td>
        <td>${formatBackendRecommendation(before)}</td>
        <td>${formatBackendRecommendation(after)}</td>
        <td><span class="change-pill ${changed ? "changed" : ""}">${changed ? "已变化" : "稳定"}</span></td>
      </tr>`;
    })
    .join("");

  const config = report.effective_config;
  document.getElementById("parameterImpact").innerHTML = [
    ["进球模型", config.scoreline_model],
    ["平局相关性 λ", Number(config.shared_lambda).toFixed(2)],
    ["阵容影响权重", Number(config.lineup_impact_multiplier).toFixed(2)],
    ["风险修正", Number(config.risk_modifier).toFixed(2)],
    ["模型信心", Number(config.model_confidence).toFixed(2)]
  ]
    .map(([label, value]) => `<div class="impact-row"><span>${label}</span><strong>${value}</strong></div>`)
    .join("");

  document.getElementById("backtestNarrative").textContent =
    `当前参数在 ${matches.length} 场欧冠淘汰赛样例中完成回放，${changes.length} 场在首发确认后改变最佳推荐方向或推荐值。` +
    `系统同时拦截 ${report.leakage_audit.future_records} 条未来记录，避免 T-48h 或 T-60m 预测读到赛后信息。`;
}

function renderAuditView() {
  const audit = state.report.leakage_audit;
  document.getElementById("auditViewFuture").textContent = audit.future_records;
  document.getElementById("auditViewUntimestamped").textContent = audit.untimestamped_records;
  document.getElementById("auditViewVisible").textContent = audit.visible_records;
  document.getElementById("auditViewMatches").textContent = state.report.matches.length;
}

function renderControls() {
  const config = state.effectiveConfig;
  document.getElementById("summaryModel").textContent = config.scoreline_model;
  document.getElementById("summaryLambda").textContent = Number(config.shared_lambda).toFixed(2);
  document.getElementById("summaryLineup").textContent = Number(config.lineup_impact_multiplier).toFixed(2);
  document.getElementById("summaryRisk").textContent = Number(config.risk_modifier).toFixed(2);

  document.getElementById("scorelineModel").value = state.controls.scoreline_model;
  document.getElementById("sharedLambda").value = state.controls.shared_lambda;
  document.getElementById("lineupImpact").value = state.controls.lineup_impact_multiplier;
  document.getElementById("riskModifier").value = state.controls.risk_modifier;
  document.getElementById("modelConfidence").value = state.controls.model_confidence;
  document.getElementById("sharedLambdaValue").textContent = Number(state.controls.shared_lambda).toFixed(2);
  document.getElementById("lineupImpactValue").textContent = Number(state.controls.lineup_impact_multiplier).toFixed(2);
  document.getElementById("riskModifierValue").textContent = Number(state.controls.risk_modifier).toFixed(2);
  document.getElementById("modelConfidenceValue").textContent = Number(state.controls.model_confidence).toFixed(2);
}

function render() {
  if (!state.report) return;

  renderActiveView();
  renderMatches();
  const match = currentMatch();
  const checkpoint = currentCheckpointReport();
  const rows = recommendationRows(checkpoint);
  const wdl = bestByMarket(rows, "h2h");
  const totals = bestByMarket(rows, "totals");

  document.getElementById("fixtureMeta").textContent = `${state.report.scoreline_model} · ${state.currentCheckpoint} · 90 分钟市场`;
  document.getElementById("fixtureTitle").textContent = `${match.team_a} vs ${match.team_b}`;
  renderCheckpointTabs(match);

  document.getElementById("wdlDirection").textContent = wdl ? outcomeLabels[wdl.outcome] : "-";
  document.getElementById("wdlNote").textContent = wdl ? `${labelText[wdl.label]} ${wdl.value} · 边际 ${formatSignedPercent(wdl.edge)}` : "-";
  document.getElementById("totalDirection").textContent = totals ? outcomeLabels[totals.outcome] : "-";
  document.getElementById("totalNote").textContent = totals ? `${labelText[totals.label]} ${totals.value} · 边际 ${formatSignedPercent(totals.edge)}` : "-";
  document.getElementById("expectedGoals").textContent = `${checkpoint.expected_goals.team_a.toFixed(2)} : ${checkpoint.expected_goals.team_b.toFixed(2)}`;
  document.getElementById("xgNote").textContent = checkpoint.lineup_note || "无阵容说明";
  document.getElementById("leakageCount").textContent = checkpoint.leakage_audit.future_records;
  document.getElementById("leakageNote").textContent = `${checkpoint.leakage_audit.visible_records} 条可用记录`;
  document.getElementById("lineupStatus").textContent = checkpoint.lineup_status;

  renderProbabilities(checkpoint);
  renderRecommendations(rows);
  renderTimeline(match);
  renderControls();

  document.getElementById("brierWdl").textContent = state.report.metrics.brier_wdl.toFixed(4);
  document.getElementById("brierTotal").textContent = state.report.metrics.brier_over_under_2_5.toFixed(4);
  document.getElementById("auditFuture").textContent = state.report.leakage_audit.future_records;
  document.getElementById("auditVisible").textContent = state.report.leakage_audit.visible_records;
  renderBacktestView();
  renderAuditView();

  const best = rows[0];
  document.getElementById("explanation").textContent = best
    ? `${marketLabels[best.market]}方向为${outcomeLabels[best.outcome]}，模型概率 ${formatPercent(best.modelProbability)}，市场隐含概率 ${formatPercent(best.marketProbability)}，当前推荐值 ${best.value}。`
    : "当前时间点没有可用盘口，系统只展示模型概率。";
}

function scheduleFetch() {
  window.clearTimeout(debounceTimer);
  debounceTimer = window.setTimeout(fetchReport, 180);
}

function bindControls() {
  document.getElementById("scorelineModel").addEventListener("change", (event) => {
    state.controls.scoreline_model = event.target.value;
    scheduleFetch();
  });

  [
    ["sharedLambda", "shared_lambda"],
    ["lineupImpact", "lineup_impact_multiplier"],
    ["riskModifier", "risk_modifier"],
    ["modelConfidence", "model_confidence"]
  ].forEach(([elementId, key]) => {
    document.getElementById(elementId).addEventListener("input", (event) => {
      state.controls[key] = Number(event.target.value);
      renderControls();
      scheduleFetch();
    });
  });

  document.getElementById("resetButton").addEventListener("click", () => {
    state.controls = {
      scoreline_model: "bivariate_poisson",
      shared_lambda: 0.14,
      lineup_impact_multiplier: 1,
      risk_modifier: 0.86,
      model_confidence: 0.84
    };
    scheduleFetch();
  });
}

bindNavigation();
bindControls();
fetchReport();
