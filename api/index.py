"""
World Cup Edge Lab — Single-file Vercel serverless handler.

Zero framework dependencies. Zero import hacks. All algorithm code inlined.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

# ═══════════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════════

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_DATA = _ROOT / "data" / "ucl_semifinals_sample.json"
_CONFIG = _ROOT / "configs" / "default.json"
_WEB = _ROOT / "web"

# ═══════════════════════════════════════════════════════
# Algorithm — Math & Statistics
# ═══════════════════════════════════════════════════════


def poisson_pmf(k, lam):
    """Poisson probability mass function: P(X=k) for X~Pois(lam)."""
    if k < 0:
        return 0.0
    if lam < 0:
        raise ValueError("lambda must be non-negative")
    return math.exp(-lam) * lam**k / math.factorial(k)


def normalize_matrix(matrix):
    """Divide every cell by the sum so rows+cols sum to 1."""
    total = sum(sum(r) for r in matrix)
    if total <= 0:
        raise ValueError("scoreline matrix has no probability mass")
    return [[c / total for c in r] for r in matrix]


def independent_poisson_matrix(xg_a, xg_b, max_goals=10):
    """Scoreline probability matrix assuming independent Poisson goals."""
    m = []
    for ga in range(max_goals + 1):
        pa = poisson_pmf(ga, xg_a)
        row = [pa * poisson_pmf(gb, xg_b) for gb in range(max_goals + 1)]
        m.append(row)
    return normalize_matrix(m)


def bivariate_poisson_matrix(xg_a, xg_b, shared=0.0, max_goals=10):
    """Scoreline probability matrix with shared correlation factor."""
    if shared < 0 or shared > min(xg_a, xg_b):
        raise ValueError("invalid shared_lambda")
    ind_a, ind_b = xg_a - shared, xg_b - shared
    m = []
    for ga in range(max_goals + 1):
        row = []
        for gb in range(max_goals + 1):
            p = 0.0
            for s in range(min(ga, gb) + 1):
                p += poisson_pmf(s, shared) * poisson_pmf(ga - s, ind_a) * poisson_pmf(gb - s, ind_b)
            row.append(p)
        m.append(row)
    return normalize_matrix(m)


def aggregate_markets(matrix):
    """From scoreline matrix → market probabilities (WDL, O/U 2.5)."""
    aw = dr = bw = ov = un = 0.0
    for ga, row in enumerate(matrix):
        for gb, p in enumerate(row):
            if ga > gb:
                aw += p
            elif ga == gb:
                dr += p
            else:
                bw += p
            if ga + gb > 2.5:
                ov += p
            else:
                un += p
    return {"team_a_win": aw, "draw": dr, "team_b_win": bw, "over_2_5": ov, "under_2_5": un}


# ── Odds ───────────────────────────────────────────


def dec_to_prob(odds):
    if odds <= 1:
        raise ValueError("decimal_odds must be > 1")
    return 1.0 / odds


def remove_overround(odds_by_outcome):
    """Remove bookmaker overround from a set of decimal odds."""
    implied = {k: dec_to_prob(v) for k, v in odds_by_outcome.items()}
    total = sum(implied.values())
    if total <= 0:
        raise ValueError("no implied probability")
    return {k: v / total for k, v in implied.items()}


# ── Recommendations ───────────────────────────────


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def rec_label(value):
    if value >= 85:
        return "strong"
    if value >= 70:
        return "medium"
    if value >= 55:
        return "weak"
    if value >= 40:
        return "watch"
    return "avoid"


def score_recommendation(model_p, market_p, lineup_c=1.0, freshness=1.0, model_c=1.0, risk=1.0):
    edge = round(model_p - market_p, 6)
    conf = _clamp(lineup_c, 0, 1) * _clamp(freshness, 0, 1) * _clamp(model_c, 0, 1) * _clamp(risk, 0, 1)
    val = int(round(_clamp((60.0 + edge * 500.0) * conf, 0, 100)))
    return {"edge": edge, "value": val, "label": rec_label(val)}


# ═══════════════════════════════════════════════════════
# Algorithm — Timegate
# ═══════════════════════════════════════════════════════

_TIME_SENSITIVE = {"injury", "lineup", "odds", "result", "weather"}


def _parse_ts(value):
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _empty_audit():
    return {"future_records": 0, "untimestamped_records": 0, "visible_records": 0}


def _merge_audits(*audits):
    merged = _empty_audit()
    for a in audits:
        for k, v in a.items():
            merged[k] = merged.get(k, 0) + v
    return merged


def filter_available_records(records, checkpoint_time, categories=None):
    checkpoint = _parse_ts(checkpoint_time)
    cats = set(categories) if categories else _TIME_SENSITIVE
    visible, audit = [], _empty_audit()
    for rec in records:
        obs = _parse_ts(rec.get("observed_at"))
        eff = _parse_ts(rec.get("effective_at"))
        cat = rec.get("category")
        if obs is None and cat in cats:
            audit["untimestamped_records"] += 1
            continue
        if obs is not None and obs > checkpoint:
            audit["future_records"] += 1
            continue
        if eff is not None and eff > checkpoint and rec.get("confidence") != "projected":
            audit["future_records"] += 1
            continue
        visible.append(rec)
    audit["visible_records"] = len(visible)
    return visible, audit


# ═══════════════════════════════════════════════════════
# Algorithm — Backtest Engine
# ═══════════════════════════════════════════════════════

WDL_KEYS = ("team_a_win", "draw", "team_b_win")
TOTAL_KEYS = ("over_2_5", "under_2_5")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_config(config, overrides=None):
    merged = dict(config)
    for k, v in (overrides or {}).items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            n = dict(merged[k])
            n.update(v)
            merged[k] = n
        else:
            merged[k] = v
    return merged


def _latest(records):
    if not records:
        return None
    return max(records, key=lambda r: _parse_ts(r.get("observed_at")).timestamp())


def _scoreline_matrix(xg_a, xg_b, config):
    mg = int(config.get("max_goals", 10))
    if config.get("scoreline_model") == "bivariate_poisson":
        sl = min(float(config.get("shared_lambda", 0.0)), xg_a, xg_b)
        return bivariate_poisson_matrix(xg_a, xg_b, shared=sl, max_goals=mg)
    return independent_poisson_matrix(xg_a, xg_b, max_goals=mg)


def _market_probs(odds_snap):
    if odds_snap is None:
        return {}
    p = {}
    if "h2h" in odds_snap:
        p.update(remove_overround(odds_snap["h2h"]))
    if "totals" in odds_snap:
        p.update(remove_overround(odds_snap["totals"]))
    return p


def _market_name(outcome):
    return "h2h" if outcome in WDL_KEYS else "totals"


def _round_probs(p):
    return {k: round(v, 6) for k, v in p.items()}


def _build_recs(model_p, market_p, lineup_status, ck_name, config):
    recs = []
    lc = config["lineup_confidence"].get(lineup_status, config["lineup_confidence"]["unknown"])
    df = config["data_freshness"].get(ck_name, 0.8)
    for out, mp in model_p.items():
        if out not in market_p:
            continue
        r = score_recommendation(mp, market_p[out], lineup_c=lc, freshness=df,
                                  model_c=config.get("model_confidence", 1.0),
                                  risk=config.get("risk_modifier", 1.0))
        r.update({"market": _market_name(out), "outcome": out,
                   "model_probability": round(mp, 6),
                   "market_probability": round(market_p[out], 6),
                   "reason": f"Model edge versus de-vigged market probability, adjusted by {lineup_status} lineup confidence."})
        recs.append(r)
    if not recs:
        return {"market": None, "outcome": None, "value": None, "label": "unavailable", "edge": None,
                "reason": "No usable market odds were available at this checkpoint."}
    return max(recs, key=lambda x: (x["value"], x["edge"]))


def _visible_inputs(match, ck_time):
    lu, la = filter_available_records(match.get("lineup_updates", []), ck_time)
    od, oa = filter_available_records(match.get("odds_snapshots", []), ck_time)
    ij, ia = filter_available_records(match.get("injury_updates", []), ck_time)
    return lu, od, ij, _merge_audits(la, oa, ia)


def _ck_report(match, ck, config):
    lu, od, ij, audit = _visible_inputs(match, ck["time"])
    llu = _latest(lu)
    lod = _latest(od)
    im = float(config.get("lineup_impact_multiplier", 1.0))
    mx = float(config.get("minimum_xg", 0.2))
    xg_a = float(match["base_xg"]["team_a"])
    xg_b = float(match["base_xg"]["team_b"])
    if llu is not None:
        xg_a += float(llu.get("team_a_xg_delta", 0.0)) * im
        xg_b += float(llu.get("team_b_xg_delta", 0.0)) * im
    for inj in ij:
        xg_a += float(inj.get("team_a_xg_delta", 0.0)) * im
        xg_b += float(inj.get("team_b_xg_delta", 0.0)) * im
    xg_a = max(mx, xg_a)
    xg_b = max(mx, xg_b)
    matrix = _scoreline_matrix(xg_a, xg_b, config)
    mp = aggregate_markets(matrix)
    mkp = _market_probs(lod)
    ls = llu.get("confidence", "unknown") if llu else "unknown"
    return {"time": ck["time"],
            "expected_goals": {"team_a": round(xg_a, 4), "team_b": round(xg_b, 4)},
            "lineup_status": ls,
            "lineup_note": llu.get("note") if llu else None,
            "probabilities": _round_probs(mp),
            "market_probabilities": _round_probs(mkp),
            "best_recommendation": _build_recs(mp, mkp, ls, ck["name"], config),
            "leakage_audit": audit}


def run_backtest(data_path, config_path, overrides=None):
    dataset = load_json(data_path)
    config = merge_config(load_json(config_path), overrides)
    matches, audit = [], {"future_records": 0, "untimestamped_records": 0, "visible_records": 0}
    wdl_b, tot_b = [], []
    for m in dataset["matches"]:
        ck_reports = {}
        for ck in m["checkpoints"]:
            r = _ck_report(m, ck, config)
            ck_reports[ck["name"]] = r
            audit = _merge_audits(audit, r["leakage_audit"])
        fn = m["checkpoints"][-1]["name"]
        fp = ck_reports[fn]["probabilities"]
        wdl_b.append(sum((fp[k] - (1.0 if k == _actual_wdl(m["result"]) else 0.0)) ** 2 for k in WDL_KEYS))
        tot_b.append(sum((fp[k] - (1.0 if k == _actual_total(m["result"]) else 0.0)) ** 2 for k in TOTAL_KEYS))
        matches.append({"id": m["id"], "team_a": m["team_a"], "team_b": m["team_b"],
                         "result": m["result"], "checkpoints": ck_reports})
    return {"parameter_set": config["parameter_set"],
            "scoreline_model": config.get("scoreline_model", "independent_poisson"),
            "effective_config": config,
            "matches": matches,
            "metrics": {"brier_wdl": round(sum(wdl_b) / len(wdl_b), 6) if wdl_b else None,
                        "brier_over_under_2_5": round(sum(tot_b) / len(tot_b), 6) if tot_b else None},
            "leakage_audit": audit}


def _actual_wdl(result):
    if result["team_a_goals"] > result["team_b_goals"]:
        return "team_a_win"
    if result["team_a_goals"] == result["team_b_goals"]:
        return "draw"
    return "team_b_win"


def _actual_total(result):
    return "over_2_5" if result["team_a_goals"] + result["team_b_goals"] > 2.5 else "under_2_5"


# ═══════════════════════════════════════════════════════
# Vercel handler
# ═══════════════════════════════════════════════════════

_CONTENT_TYPES = {".js": "application/javascript", ".css": "text/css",
                   ".html": "text/html", ".json": "application/json",
                   ".svg": "image/svg+xml", ".ico": "image/x-icon",
                   ".png": "image/png", ".jpg": "image/jpeg"}


def _json_resp(data, status=200):
    return {"statusCode": status, "headers": {"content-type": "application/json"},
            "body": json.dumps(data, ensure_ascii=False)}


def _static_resp(path):
    """Serve a file from web/ or return None."""
    rel = "index.html" if path in ("", "/") else path.lstrip("/")
    fp = _WEB / rel
    if not fp.exists() or not fp.is_file():
        return None
    ct = _CONTENT_TYPES.get(fp.suffix, "application/octet-stream")
    b = fp.read_bytes()
    is_text = fp.suffix in (".html", ".js", ".css", ".json", ".svg")
    return {"statusCode": 200,
            "headers": {"content-type": ct, "cache-control": "public, max-age=3600"},
            "body": b.decode("utf-8") if is_text else b.hex(),
            "encoding": "utf-8" if is_text else "base64"}


def handler(event, context):
    """Vercel serverless function entry point."""
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")

    # Health
    if path == "/api/health":
        return _json_resp({"status": "ok", "version": "1.0.0"})

    # Config
    if path == "/api/config" and method == "GET":
        try:
            return _json_resp(load_json(str(_CONFIG)))
        except Exception as e:
            return _json_resp({"error": str(e)}, 500)

    # Backtest
    if path == "/api/backtest":
        try:
            body = event.get("body") or "{}"
            params = json.loads(body) if isinstance(body, str) else body
            overrides = params.get("config_overrides", {})
            report = run_backtest(str(_DATA), str(_CONFIG), overrides)
            return _json_resp({"report": report, "effective_config": report.get("effective_config", {})})
        except Exception as e:
            return _json_resp({"error": str(e)}, 500)

    # Static files
    resp = _static_resp(path)
    if resp:
        return resp

    return _json_resp({"error": "Not Found"}, 404)
