"""
World Cup Edge Lab — WSGI Prediction API
Zero external dependencies. Pure Python standard library.
"""
import json
from json import dumps, loads
import math as _m
from datetime import datetime as _dt
from pathlib import Path as _Path

# ═══════════════════════════════════════════════════════
# 1. FILE PATHS
# ═══════════════════════════════════════════════════════

THIS_DIR = _Path(__file__).resolve().parent
ROOT = THIS_DIR.parent
DATA_FILE = str(ROOT / "data" / "ucl_semifinals_sample.json")
CONFIG_FILE = str(ROOT / "configs" / "default.json")
WEB_DIR = ROOT / "web"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".woff2": "font/woff2",
}
TEXT_SUFFIXES = {".html", ".js", ".css", ".json", ".svg", ".txt"}

# ═══════════════════════════════════════════════════════
# 2. POISSON CORE — Scoreline Probability Engine
# ═══════════════════════════════════════════════════════


def poisson_prob(k, intensity):
    """P(X=k) for Poisson(intensity)"""
    if k < 0:
        return 0.0
    return _m.exp(-intensity) * (intensity ** k) / _m.factorial(k)


def score_grid(intensity_a, intensity_b, max_g=10):
    """Independent Poisson grid: outer product of two marginals."""
    row_probs = [poisson_prob(g, intensity_a) for g in range(max_g + 1)]
    col_probs = [poisson_prob(g, intensity_b) for g in range(max_g + 1)]
    grid = [[row_probs[i] * col_probs[j] for j in range(max_g + 1)] for i in range(max_g + 1)]
    return grid


def bivariate_grid(intensity_a, intensity_b, shared=0.0, max_g=10):
    """
    Bivariate Poisson: goals share a common shock component.
    Var[X] = Var[Y] = lambda_ind + shared, Cov[X,Y] = shared.
    """
    iz_a = intensity_a - shared
    iz_b = intensity_b - shared
    grid = []
    for ga in range(max_g + 1):
        row = []
        for gb in range(max_g + 1):
            total = 0.0
            for s in range(min(ga, gb) + 1):
                p_shared = poisson_prob(s, shared)
                p_rem_a = poisson_prob(ga - s, iz_a)
                p_rem_b = poisson_prob(gb - s, iz_b)
                total += p_shared * p_rem_a * p_rem_b
            row.append(total)
        grid.append(row)
    return grid


def normalize_grid(grid):
    """Normalize so all cells sum to 1."""
    s = sum(cell for row in grid for cell in row)
    if s <= 0:
        raise ValueError("Zero total probability in grid")
    return [[cell / s for cell in row] for row in grid]


def select_grid_model(intensity_a, intensity_b, config):
    """Pick independent or bivariate Poisson based on config."""
    max_g = int(config.get("max_goals", 10))
    mode = config.get("scoreline_model", "independent_poisson")
    if mode == "bivariate_poisson":
        sh = min(float(config.get("shared_lambda", 0.0)), intensity_a, intensity_b)
        raw = bivariate_grid(intensity_a, intensity_b, shared=sh, max_g=max_g)
    else:
        raw = score_grid(intensity_a, intensity_b, max_g=max_g)
    return normalize_grid(raw)


def aggregate_outcomes(grid):
    """From score grid → win/draw/loss + over/under 2.5."""
    home = draw = away = over = under = 0.0
    for ga, row in enumerate(grid):
        for gb, p in enumerate(row):
            if ga > gb:
                home += p
            elif ga == gb:
                draw += p
            else:
                away += p
            if ga + gb > 2.5:
                over += p
            else:
                under += p
    return {"home_win": home, "draw": draw, "away_win": away, "over_2_5": over, "under_2_5": under}


# ═══════════════════════════════════════════════════════
# 3. ODDS PROCESSING
# ═══════════════════════════════════════════════════════


def odds_to_probability(decimal):
    if decimal <= 1.0:
        raise ValueError(f"Decimal odds must exceed 1, got {decimal}")
    return 1.0 / decimal


def devig(price_book):
    """Remove overround: divide each implied prob by total."""
    implied = {k: odds_to_probability(v) for k, v in price_book.items()}
    total = sum(implied.values())
    if total <= 0:
        raise ValueError("Zero total implied probability")
    return {k: v / total for k, v in implied.items()}


def extract_fair_probs(snapshot):
    """From an odds snapshot dict → devigged probabilities."""
    result = {}
    if not snapshot:
        return result
    if "h2h" in snapshot:
        result.update(devig(snapshot["h2h"]))
    if "totals" in snapshot:
        result.update(devig(snapshot["totals"]))
    return result


# ═══════════════════════════════════════════════════════
# 4. RECOMMENDATION ENGINE
# ═══════════════════════════════════════════════════════


def bound(val, lo=0.0, hi=1.0):
    return max(lo, min(hi, val))


def value_label(score):
    if score >= 85:
        return "strong"
    if score >= 70:
        return "medium"
    if score >= 55:
        return "weak"
    if score >= 40:
        return "watch"
    return "avoid"


def compute_recommendation(model_prob, market_prob,
                           lineup_conf=1.0, data_freshness=1.0,
                           model_confidence=1.0, risk=1.0):
    """
    Edge = model - market (positive = model sees value)
    Score = (60 + edge*500) * confidence multipliers
    """
    edge = round(model_prob - market_prob, 6)
    mult = bound(lineup_conf) * bound(data_freshness) * bound(model_confidence) * bound(risk)
    raw = (60.0 + edge * 500.0) * mult
    score = int(round(bound(raw, 0, 100)))
    return {"edge": edge, "value": score, "label": value_label(score)}


# ═══════════════════════════════════════════════════════
# 5. TIMEGATE — Historical Simulation
# ═══════════════════════════════════════════════════════


def parse_iso(value):
    if value is None:
        return None
    return _dt.fromisoformat(value.replace("Z", "+00:00"))


def fresh_audit():
    return {"future": 0, "untimed": 0, "visible": 0}


def union_audits(*args):
    u = fresh_audit()
    for a in args:
        u["future"] += a.get("future", 0)
        u["untimed"] += a.get("untimed", 0)
        u["visible"] += a.get("visible", 0)
    return u


def filter_to_checkpoint(records, checkpoint_time,
                         categories=None):
    """
    Given a list of records and a checkpoint time,
    return only those that would have been visible at that time.
    """
    ck = parse_iso(checkpoint_time)
    sensitive = categories if categories else {"lineup", "odds", "injury", "result", "weather"}
    visible = []
    audit = fresh_audit()
    for rec in records:
        obs_at = parse_iso(rec.get("observed_at"))
        eff_at = parse_iso(rec.get("effective_at"))
        cat = rec.get("category", "")

        if obs_at is None and cat in sensitive:
            audit["untimed"] += 1
            continue
        if obs_at is not None and obs_at > ck:
            audit["future"] += 1
            continue
        if eff_at is not None and eff_at > ck and rec.get("confidence") != "projected":
            audit["future"] += 1
            continue
        visible.append(rec)
    audit["visible"] = len(visible)
    return visible, audit


# ═══════════════════════════════════════════════════════
# 6. BACKTEST ENGINE
# ═══════════════════════════════════════════════════════


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return loads(f.read())


def deep_merge(base, overrides):
    """Merge overrides into base dict (nested merge for dict values)."""
    result = dict(base)
    for key, val in (overrides or {}).items():
        if isinstance(val, dict) and isinstance(result.get(key), dict):
            merged = dict(result[key])
            merged.update(val)
            result[key] = merged
        else:
            result[key] = val
    return result


def latest_record(records):
    if not records:
        return None
    return max(records, key=lambda r: parse_iso(r["observed_at"]).timestamp())


def build_checkpoint(match, checkpoint, config):
    """Run the full prediction pipeline for one checkpoint of one match."""
    # Timegate: filter to visible data
    lineups, odds, injuries, audit_trio = [], [], [], []
    ld, la = filter_to_checkpoint(match.get("lineup_updates", []), checkpoint["time"])
    od, oa = filter_to_checkpoint(match.get("odds_snapshots", []), checkpoint["time"])
    ij, ia = filter_to_checkpoint(match.get("injury_updates", []), checkpoint["time"])
    audit = union_audits(la, oa, ia)

    # Latest available data
    best_lineup = latest_record(ld)
    best_odds = latest_record(od)

    # Apply xG adjustments
    impact = float(config.get("lineup_impact_multiplier", 1.0))
    floor_xg = float(config.get("minimum_xg", 0.2))
    xg_h = float(match["base_xg"]["team_a"])
    xg_a = float(match["base_xg"]["team_b"])

    if best_lineup:
        xg_h += float(best_lineup.get("team_a_xg_delta", 0.0)) * impact
        xg_a += float(best_lineup.get("team_b_xg_delta", 0.0)) * impact
    for injury in ij:
        xg_h += float(injury.get("team_a_xg_delta", 0.0)) * impact
        xg_a += float(injury.get("team_b_xg_delta", 0.0)) * impact

    xg_h = max(floor_xg, xg_h)
    xg_a = max(floor_xg, xg_a)

    # Scoreline grid
    grid = select_grid_model(xg_h, xg_a, config)
    model_probs = aggregate_outcomes(grid)

    # Market probabilities
    market_probs = extract_fair_probs(best_odds)

    # Build recommendations
    lineup_status = best_lineup.get("confidence", "unknown") if best_lineup else "unknown"
    lineup_conf_map = config["lineup_confidence"]
    lc = lineup_conf_map.get(lineup_status, lineup_conf_map.get("unknown", 0.5))
    freshness = config["data_freshness"].get(checkpoint["name"], 0.8)
    mc = float(config.get("model_confidence", 1.0))
    rk = float(config.get("risk_modifier", 1.0))

    recs = []
    for outcome, model_val in model_probs.items():
        if outcome not in market_probs:
            continue
        rec = compute_recommendation(model_val, market_probs[outcome],
                                     lineup_conf=lc, data_freshness=freshness,
                                     model_confidence=mc, risk=rk)
        rec["market"] = "h2h" if outcome in ("home_win", "draw", "away_win") else "totals"
        rec["outcome"] = outcome
        rec["model_prob"] = round(model_val, 6)
        rec["market_prob"] = round(market_probs[outcome], 6)
        rec["reason"] = f"Model edge vs market, adjusted for {lineup_status} lineup"
        recs.append(rec)

    best_rec = max(recs, key=lambda x: (x["value"], x["edge"])) if recs else {
        "market": None, "outcome": None, "value": None, "label": "unavailable",
        "edge": None, "reason": "No market odds at this checkpoint"
    }

    return {
        "time": checkpoint["time"],
        "expected_goals": {"home": round(xg_h, 4), "away": round(xg_a, 4)},
        "lineup_status": lineup_status,
        "lineup_note": best_lineup.get("note") if best_lineup else None,
        "probabilities": {k: round(v, 6) for k, v in model_probs.items()},
        "market_probs": {k: round(v, 6) for k, v in market_probs.items()},
        "recommendation": best_rec,
        "data_audit": audit,
    }


def actual_outcome(result):
    if result["team_a_goals"] > result["team_b_goals"]:
        return "home_win"
    if result["team_a_goals"] == result["team_b_goals"]:
        return "draw"
    return "away_win"


def actual_total(result):
    return "over_2_5" if result["team_a_goals"] + result["team_b_goals"] > 2.5 else "under_2_5"


def brier_score(prob_vec, correct_key, category_keys):
    """Lower is better. Sum of squared errors."""
    return sum((prob_vec[k] - (1.0 if k == correct_key else 0.0)) ** 2 for k in category_keys)


def run_predictions(data_path, config_path, overrides=None):
    """
    Execute full backtest: for each match × checkpoint,
    simulate what was knowable → generate predictions → compare to actuals.
    """
    dataset = read_json(data_path)
    config = deep_merge(read_json(config_path), overrides)
    total_audit = fresh_audit()
    match_results = []
    brier_wdl_list = []
    brier_total_list = []
    WDL = ("home_win", "draw", "away_win")
    TOT = ("over_2_5", "under_2_5")

    for match in dataset["matches"]:
        ck_reports = {}
        for ck in match["checkpoints"]:
            report = build_checkpoint(match, ck, config)
            ck_reports[ck["name"]] = report
            total_audit = union_audits(total_audit, report["data_audit"])

        # Evaluate final checkpoint
        last_ck = match["checkpoints"][-1]["name"]
        final_probs = ck_reports[last_ck]["probabilities"]
        brier_wdl_list.append(brier_score(final_probs, actual_outcome(match["result"]), WDL))
        brier_total_list.append(brier_score(final_probs, actual_total(match["result"]), TOT))

        match_results.append({
            "id": match["id"],
            "home": match["team_a"],
            "away": match["team_b"],
            "result": match["result"],
            "checkpoints": ck_reports,
        })

    def avg_careful(lst):
        return round(sum(lst) / len(lst), 6) if lst else None

    return {
        "model": config["parameter_set"],
        "scoreline_model": config.get("scoreline_model", "independent_poisson"),
        "config_used": config,
        "matches": match_results,
        "accuracy": {
            "brier_wdl": avg_careful(brier_wdl_list),
            "brier_ou": avg_careful(brier_total_list),
        },
        "data_quality": total_audit,
    }


# ═══════════════════════════════════════════════════════
# 7. WSGI APPLICATION
# ═══════════════════════════════════════════════════════


def json_ok(start, data):
    body = dumps(data, ensure_ascii=False).encode("utf-8")
    start("200 OK", [("Content-Type", "application/json; charset=utf-8"),
                     ("Content-Length", str(len(body)))])
    return [body]


def json_error(start, msg, status="500"):
    body = dumps({"error": msg}, ensure_ascii=False).encode("utf-8")
    start(f"{status}", [("Content-Type", "application/json; charset=utf-8"),
                        ("Content-Length", str(len(body)))])
    return [body]


def read_post_body(environ):
    length = int(environ.get("CONTENT_LENGTH", "0"))
    if length <= 0:
        return {}
    raw = environ["wsgi.input"].read(length)
    return loads(raw.decode("utf-8")) if raw else {}


def serve_static(environ, start, filepath):
    """Try to serve a static file. Returns response or None."""
    if filepath in ("", "/"):
        filepath = "index.html"
    target = WEB_DIR / filepath.lstrip("/")
    if not target.exists() or not target.is_file():
        return None

    body = target.read_bytes()
    ct = MIME.get(target.suffix, "application/octet-stream")

    # Handle text vs binary
    if target.suffix in TEXT_SUFFIXES:
        body_str = body.decode("utf-8")
        start("200 OK", [("Content-Type", ct),
                         ("Content-Length", str(len(body_str))),
                         ("Cache-Control", "public, max-age=3600")])
        return [body_str.encode("utf-8")]
    else:
        start("200 OK", [("Content-Type", ct),
                         ("Content-Length", str(len(body))),
                         ("Cache-Control", "public, max-age=3600")])
        return [body]


def app(environ, start_response):
    """WSGI entry point for Vercel."""
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")

    # Health check
    if path == "/api/health":
        return json_ok(start_response, {"status": "alive", "version": "1.0.0"})

    # Get config
    if path == "/api/config" and method == "GET":
        try:
            return json_ok(start_response, read_json(CONFIG_FILE))
        except Exception as ex:
            return json_error(start_response, str(ex))

    # Run predictions
    if path == "/api/predict":
        try:
            params = read_post_body(environ)
            report = run_predictions(DATA_FILE, CONFIG_FILE, params.get("overrides", {}))
            return json_ok(start_response, {
                "report": report,
                "config": report.get("config_used", {}),
            })
        except Exception as ex:
            return json_error(start_response, str(ex))

    # Static files
    result = serve_static(environ, start_response, path)
    if result is not None:
        return result

    # 404
    return json_error(start_response, "Not found", "404")
