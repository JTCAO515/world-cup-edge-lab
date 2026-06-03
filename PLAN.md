# World Cup Edge Lab — 产品规划

## 定位

世界杯（或其他足球赛事）**概率预测 + 价值下注推荐**工具。
帮助用户在开赛前评估比赛预期、识别模型 vs 市场的差异（Edge）。

## MVP 功能

### 数据层
- 赛事配置（球队 xG、checkpoints）
- 实时/模拟赔率数据（h2h、totals）
- 阵容/伤病更新（影响 xG）

### 算法层
- **Poisson 模型**：基于 xG → 进球数概率分布
  - 独立 Poisson（基本模型）
  - 双变量 Poisson（关联模型，考虑相关性）
- **赔率去水**：从庄家赔率反推真实概率
- **推荐引擎**：对比模型概率 vs 市场概率 → 计算 Edge 和 Value Score
- **回测引擎**：模拟不同时间点的可见信息 → 评估模型准确性（Brier Score）

### API 层
| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/config` | GET | 当前参数配置 |
| `/api/predict` | POST | 执行预测，返回所有比赛的逐 checkpoint 分析 |

### 前端层
- 赛事卡片列表（左右对比布局）
- 每个卡片展示：
  - **预期进球**（xG bar chart）
  - **概率面板**：WDL + O/U 2.5
  - **最佳推荐**：Edge, Value, Label
  - **Checkpoint 切换**：T-48h / T-60m 对比
- 整体设计：深色足球主题

## 数据模型

### Match
```
{
  id, team_a, team_b, kickoff,
  base_xg: {team_a, team_b},
  checkpoints: [{name, time}],
  lineup_updates: [{observed_at, confidence, team_a_xg_delta, team_b_xg_delta, note}],
  odds_snapshots: [{observed_at, h2h: {...}, totals: {...}}],
  injury_updates: [{observed_at, team_a_xg_delta, team_b_xg_delta}],
  result: {team_a_goals, team_b_goals}
}
```

### Prediction Report
```
{
  parameter_set,
  scoreline_model,
  matches: [{
    id, team_a, team_b, result,
    checkpoints: {
      "T-48h": { time, expected_goals, probabilities, market_probabilities, best_recommendation, leakage_audit },
      ...
    }
  }],
  metrics: { brier_wdl, brier_over_under_2_5 },
  leakage_audit
}
```

## 技术栈

- **后端**：Python WSGI（纯 stdlib，零依赖）
- **前端**：纯 HTML + CSS + JS（无框架）
- **部署**：Vercel Serverless（python3.11）
- **数据**：JSON 静态文件

## 非目标（V2 可能）

- 用户登录/历史记录
- 实时数据爬取
- 多语言支持
- 移动端 App
