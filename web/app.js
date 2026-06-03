/* ═══════════════════════════════════════════
   World Cup Edge Lab — App
   ═══════════════════════════════════════════ */

(function () {
  "use strict";

  let report = null;
  let activeCheckpoint = null;

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  /* ─── API ─── */

  async function fetchPredictions() {
    const res = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    const data = await res.json();
    return data.report;
  }

  /* ─── Render ─── */

  function render(reportData) {
    report = reportData;
    const matches = report.matches;
    if (!matches || matches.length === 0) {
      $("#loading").style.display = "none";
      $("#matches").style.display = "block";
      $("#matches").innerHTML = "<p>暂无比赛数据</p>";
      return;
    }

    const allCks = new Set();
    matches.forEach((m) => {
      Object.keys(m.checkpoints).forEach((ck) => allCks.add(ck));
    });
    const ckNames = Array.from(allCks);
    activeCheckpoint = ckNames[ckNames.length - 1];

    $("#loading").style.display = "none";
    $("#summary").style.display = "flex";
    $("#controls").style.display = "block";
    $("#matches").style.display = "block";

    $("#sum-model").textContent =
      report.scoreline_model === "bivariate_poisson" ? "双变量 Poisson" : "独立 Poisson";
    $("#sum-brier-wdl").textContent = report.accuracy?.brier_wdl?.toFixed(4) ?? "—";
    $("#sum-brier-ou").textContent = report.accuracy?.brier_ou?.toFixed(4) ?? "—";

    renderCheckpointTabs(ckNames);
    renderMatches();
  }

  function renderCheckpointTabs(names) {
    const container = $("#checkpoint-tabs");
    container.innerHTML = "";
    names.forEach((name) => {
      const btn = document.createElement("button");
      btn.className = "checkpoint-tab" + (name === activeCheckpoint ? " active" : "");
      btn.textContent = name;
      btn.dataset.ck = name;
      btn.addEventListener("click", () => {
        activeCheckpoint = name;
        document.querySelectorAll(".checkpoint-tab").forEach((t) => t.classList.remove("active"));
        btn.classList.add("active");
        renderMatches();
      });
      container.appendChild(btn);
    });
  }

  function renderMatches() {
    const container = $("#matches");
    container.innerHTML = "";
    report.matches.forEach((m) => {
      const ck = m.checkpoints[activeCheckpoint];
      if (!ck) return;
      container.appendChild(buildMatchCard(m, ck));
    });
  }

  function buildMatchCard(match, ck) {
    const card = document.createElement("div");
    card.className = "match-card";

    const resultText = match.result
      ? `${match.result.team_a_goals} - ${match.result.team_b_goals}`
      : "未进行";

    card.innerHTML = `
      <div class="match-header">
        <div class="match-teams">
          <span class="home-team">${esc(match.home)}</span>
          <span class="vs">vs</span>
          <span class="away-team">${esc(match.away)}</span>
        </div>
        <span class="match-result-badge">${resultText}</span>
      </div>
      <div class="xg-section">
        <div class="xg-row">
          <span class="xg-label">${esc(match.home)}</span>
          <div class="xg-bar-track">
            <div class="xg-bar-fill home" style="width:${pct(ck.expected_goals.home, 3)}%"></div>
          </div>
          <span class="xg-value">${ck.expected_goals.home.toFixed(2)}</span>
        </div>
        <div class="xg-row">
          <span class="xg-label">${esc(match.away)}</span>
          <div class="xg-bar-track">
            <div class="xg-bar-fill away" style="width:${pct(ck.expected_goals.away, 3)}%"></div>
          </div>
          <span class="xg-value">${ck.expected_goals.away.toFixed(2)}</span>
        </div>
      </div>
      <div class="probs-section">
        ${probBlock("胜平负", ck.probabilities, [
          { k: "home_win", l: match.home, c: "green" },
          { k: "draw", l: "平局", c: "amber" },
          { k: "away_win", l: match.away, c: "red" },
        ])}
        ${probBlock("大小球", ck.probabilities, [
          { k: "over_2_5", l: "大 2.5", c: "blue" },
          { k: "under_2_5", l: "小 2.5", c: "blue" },
        ])}
      </div>
      <div class="rec-section">
        ${recommendation(ck.recommendation)}
      </div>
    `;
    return card;
  }

  function probBlock(title, probs, items) {
    let rows = "";
    items.forEach(({ k, l, c }) => {
      const p = probs[k] ?? 0;
      rows += `<div class="prob-item">
        <span class="prob-name">${l}</span>
        <div class="prob-bar-track">
          <div class="prob-bar-fill ${c}" style="width:${(p * 100).toFixed(0)}%"></div>
        </div>
        <span class="prob-value">${(p * 100).toFixed(1)}%</span>
      </div>`;
    });
    return `<div class="prob-block"><h4>${title}</h4>${rows}</div>`;
  }

  function recommendation(rec) {
    if (!rec || !rec.outcome) {
      return `<div class="rec-badge unavailable">无推荐</div>`;
    }
    const labels = {
      home_win: "主胜", away_win: "客胜", draw: "平局",
      over_2_5: "大 2.5", under_2_5: "小 2.5",
    };
    const ol = labels[rec.outcome] ?? rec.outcome;
    return `
      <div class="rec-badge ${rec.label}">${rec.label} · ${ol}</div>
      <div class="rec-detail">
        <span>Edge: <strong>${(rec.edge * 100).toFixed(2)}%</strong></span>
        <span>Value: <strong>${rec.value}</strong></span>
        <span>模型: <strong>${(rec.model_prob * 100).toFixed(1)}%</strong></span>
        <span>市场: <strong>${(rec.market_prob * 100).toFixed(1)}%</strong></span>
      </div>
    `;
  }

  function pct(val, max) {
    return Math.min(100, (val / max) * 100);
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  /* ─── Init ─── */

  fetchPredictions()
    .then(render)
    .catch((err) => {
      $("#loading").innerHTML = `<p style="color:var(--red)">加载失败: ${err.message}</p>`;
    });
})();
