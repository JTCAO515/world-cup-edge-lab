"""
World Cup Edge Lab — Single-file Vercel serverless handler.

handler(event, context) is at the top so Vercel's scanner finds it immediately.
All algorithm code inlined below.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

# ═══════════════════════════════════════════════════════
# Paths & helpers (must be before handler)
# ═══════════════════════════════════════════════════════

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_DATA = str(_ROOT / "data" / "ucl_semifinals_sample.json")
_CONFIG = str(_ROOT / "configs" / "default.json")
_WEB = _ROOT / "web"
_CT = {".js": "application/javascript", ".css": "text/css", ".html": "text/html",
       ".json": "application/json", ".svg": "image/svg+xml", ".ico": "image/x-icon"}


def _js(body, status=200):
    return {"statusCode": status, "headers": {"content-type": "application/json"},
            "body": json.dumps(body, ensure_ascii=False)}


def _static(path):
    rel = "index.html" if path in ("", "/") else path.lstrip("/")
    fp = _WEB / rel
    if not fp.exists() or not fp.is_file():
        return None
    ct = _CT.get(fp.suffix, "application/octet-stream")
    b = fp.read_bytes()
    txt = fp.suffix in (".html", ".js", ".css", ".json", ".svg")
    return {"statusCode": 200,
            "headers": {"content-type": ct, "cache-control": "public, max-age=3600"},
            "body": b.decode("utf-8") if txt else b.hex(),
            "encoding": "utf-8" if txt else "base64"}


# ═══════════════════════════════════════════════════════
# Vercel handler — top-level, easy for Vercel to find
# ═══════════════════════════════════════════════════════

def handler(event, context):
    """Vercel serverless function entry point."""
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")

    if path == "/api/health":
        return _js({"status": "ok", "version": "1.0.0"})

    if path == "/api/config" and method == "GET":
        try:
            return _js(load_json(_CONFIG))
        except Exception as e:
            return _js({"error": str(e)}, 500)

    if path == "/api/backtest":
        try:
            body = event.get("body") or "{}"
            params = json.loads(body) if isinstance(body, str) else body
            overrides = params.get("config_overrides", {})
            report = run_backtest(_DATA, _CONFIG, overrides)
            return _js({"report": report, "effective_config": report.get("effective_config", {})})
        except Exception as e:
            return _js({"error": str(e)}, 500)

    r = _static(path)
    if r:
        return r
    return _js({"error": "Not Found"}, 404)


# ═══════════════════════════════════════════════════════
# Algorithm — all code below is called by handler
# ═══════════════════════════════════════════════════════


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


# ── Poisson ──────────────────────────────────────────


def poisson_pmf(k, lam):
    if k < 0:
        return 0.0
    if lam < 0:
        raise ValueError("lambda must be non-negative")
    return math.exp(-lam) * lam**k / math.factorial(k)


def _norm_matrix(m):
    total = sum(sum(r) for r in m)
    if total <= 0:
        raise ValueError("scoreline matrix has no probability mass")
    return [[c / total for c in r] for r in m]


def independent_poisson_matrix(xg_a, xg_b, mg=10):
    m = []
    for ga in range(mg + 1):
        pa = poisson_pmf(ga, xg_a)
        m.append([pa * poisson_pmf(gb, xg_b) for gb in range(mg + 1)])
    return _norm_matrix(m)


def bivariate_poisson_matrix(xg_a, xg_b, shared=0.0, mg=10):
    if shared < 0 or shared > min(xg_a, xg_b):
        raise ValueError("invalid shared_lambda")
    ia, ib = xg_a - shared, xg_b - shared
    m = []
    for ga in range(mg + 1):
        row = []
        for gb in range(mg + 1):
            p = 0.0
            for s in range(min(ga, gb) + 1):
                p += poisson_pmf(s, shared) * poisson_pmf(ga - s, ia) * poisson_pmf(gb - s, ib)
            row.append(p)
        m.append(row)
    return _norm_matrix(m)


def aggregate_markets(matrix):
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


# ── Odds ──────────────────────────────────────────


def dec_to_prob(odds):
    if odds <= 1:
        raise ValueError("decimal_odds must be > 1")
    return 1.0 / odds


def remove_overround(odds_map):
    implied = {k: dec_to_prob(v) for k, v in odds_map.items()}
    total = sum(implied.values())
    if total <= 0:
        raise ValueError("no implied probability")
    return {k: v / total for k, v in implied.items()}


# ── Recommendations ───────────────────────────────


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _rec_label(v):
    if v >= 85:
        return "strong"
    if v >= 70:
        return "medium"
    if v >= 55:
        return "weak"
    if v >= 40:
        return "watch"
    return "avoid"


def score_recommendation(mp, mkp, lc=1.0, fr=1.0, mc=1.0, rk=1.0):
    edge = round(mp - mkp, 6)
    conf = _clamp(lc, 0, 1) * _clamp(fr, 0, 1) * _clamp(mc, 0, 1) * _clamp(rk, 0, 1)
    val = int(round(_clamp((60.0 + edge * 500.0) * conf, 0, 100)))
    return {"edge": edge, "value": val, "label": _rec_label(val)}


# ── Timegate ──────────────────────────────────────

_TS_CATS = {"injury", "lineup", "odds", "result", "weather"}


def _pts(v):
    if v is None:
        return None
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def _ea():
    return {"future_records": 0, "untimestamped_records": 0, "visible_records": 0}


def _ma(*a):
    m = _ea()
    for x in a:
        for k, v in x.items():
            m[k] = m.get(k, 0) + v
    return m


def filter_available_records(records, ck_time, cats=None):
    ck = _pts(ck_time)
    cs = set(cats) if cats else _TS_CATS
    v, a = [], _ea()
    for r in records:
        obs = _pts(r.get("observed_at"))
        eff = _pts(r.get("effective_at"))
        cat = r.get("category")
        if obs is None and cat in cs:
            a["untimestamped_records"] += 1
            continue
        if obs is not None and obs > ck:
            a["future_records"] += 1
            continue
        if eff is not None and eff > ck and r.get("confidence") != "projected":
            a["future_records"] += 1
            continue
        v.append(r)
    a["visible_records"] = len(v)
    return v, a


# ── Backtest engine ──────────────────────────────

_WDL = ("team_a_win", "draw", "team_b_win")
_TOT = ("over_2_5", "under_2_5")


def _latest(records):
    if not records:
        return None
    return max(records, key=lambda r: _pts(r.get("observed_at")).timestamp())


def _sc_matrix(xg_a, xg_b, config):
    mg = int(config.get("max_goals", 10))
    if config.get("scoreline_model") == "bivariate_poisson":
        sl = min(float(config.get("shared_lambda", 0.0)), xg_a, xg_b)
        return bivariate_poisson_matrix(xg_a, xg_b, shared=sl, mg=mg)
    return independent_poisson_matrix(xg_a, xg_b, mg=mg)


def _mkp(odds_snap):
    if odds_snap is None:
        return {}
    p = {}
    if "h2h" in odds_snap:
        p.update(remove_overround(odds_snap["h2h"]))
    if "totals" in odds_snap:
        p.update(remove_overround(odds_snap["totals"]))
    return p


def _mn(outcome):
    return "h2h" if outcome in _WDL else "totals"


def _rp(p):
    return {k: round(v, 6) for k, v in p.items()}


def _build_recs(mp, mkp, ls, cn, config):
    recs = []
    lc = config["lineup_confidence"].get(ls, config["lineup_confidence"]["unknown"])
    df = config["data_freshness"].get(cn, 0.8)
    for out, mpv in mp.items():
        if out not in mkp:
            continue
        r = score_recommendation(mpv, mkp[out], lc=lc, fr=df,
                                 mc=config.get("model_confidence", 1.0),
                                 rk=config.get("risk_modifier", 1.0))
        r.update({"market": _mn(out), "outcome": out,
                  "model_probability": round(mpv, 6),
                  "market_probability": round(mkp[out], 6),
                  "reason": f"Model edge versus de-vigged market probability, adjusted by {ls} lineup confidence."})
        recs.append(r)
    if not recs:
        return {"market": None, "outcome": None, "value": None, "label": "unavailable",
                "edge": None, "reason": "No usable market odds were available."}
    return max(recs, key=lambda x: (x["value"], x["edge"]))


def _vi(match, ct):
    lu, la = filter_available_records(match.get("lineup_updates", []), ct)
    od, oa = filter_available_records(match.get("odds_snapshots", []), ct)
    ij, ia = filter_available_records(match.get("injury_updates", []), ct)
    return lu, od, ij, _ma(la, oa, ia)


def _ck_report(match, ck, config):
    lu, od, ij, audit = _vi(match, ck["time"])
    llu = _latest(lu)
    lod = _latest(od)
    im = float(config.get("lineup_impact_multiplier", 1.0))
    mx = float(config.get("minimum_xg", 0.2))
    xa = float(match["base_xg"]["team_a"])
    xb = float(match["base_xg"]["team_b"])
    if llu is not None:
        xa += float(llu.get("team_a_xg_delta", 0.0)) * im
        xb += float(llu.get("team_b_xg_delta", 0.0)) * im
    for ijr in ij:
        xa += float(ijr.get("team_a_xg_delta", 0.0)) * im
        xb += float(ijr.get("team_b_xg_delta", 0.0)) * im
    xa, xb = max(mx, xa), max(mx, xb)
    matrix = _sc_matrix(xa, xb, config)
    mp = aggregate_markets(matrix)
    mkp_v = _mkp(lod)
    ls = llu.get("confidence", "unknown") if llu else "unknown"
    return {"time": ck["time"],
            "expected_goals": {"team_a": round(xa, 4), "team_b": round(xb, 4)},
            "lineup_status": ls,
            "lineup_note": llu.get("note") if llu else None,
            "probabilities": _rp(mp),
            "market_probabilities": _rp(mkp_v),
            "best_recommendation": _build_recs(mp, mkp_v, ls, ck["name"], config),
            "leakage_audit": audit}


def run_backtest(data_path, config_path, overrides=None):
    dataset = load_json(data_path)
    config = merge_config(load_json(config_path), overrides)
    matches, audit = [], {"future_records": 0, "untimestamped_records": 0, "visible_records": 0}
    wb, tb = [], []
    for m in dataset["matches"]:
        cr = {}
        for ck in m["checkpoints"]:
            r = _ck_report(m, ck, config)
            cr[ck["name"]] = r
            audit = _ma(audit, r["leakage_audit"])
        fn = m["checkpoints"][-1]["name"]
        fp = cr[fn]["probabilities"]
        wb.append(sum((fp[k] - (1.0 if k == (_aw(m["result"])) else 0.0)) ** 2 for k in _WDL))
        tb.append(sum((fp[k] - (1.0 if k == (_at(m["result"])) else 0.0)) ** 2 for k in _TOT))
        matches.append({"id": m["id"], "team_a": m["team_a"], "team_b": m["team_b"],
                        "result": m["result"], "checkpoints": cr})
    return {"parameter_set": config["parameter_set"],
            "scoreline_model": config.get("scoreline_model", "independent_poisson"),
            "effective_config": config,
            "matches": matches,
            "metrics": {"brier_wdl": round(sum(wb) / len(wb), 6) if wb else None,
                        "brier_over_under_2_5": round(sum(tb) / len(tb), 6) if tb else None},
            "leakage_audit": audit}


def _aw(result):
    if result["team_a_goals"] > result["team_b_goals"]:
        return "team_a_win"
    if result["team_a_goals"] == result["team_b_goals"]:
        return "draw"
    return "team_b_win"


def _at(result):
    return "over_2_5" if result["team_a_goals"] + result["team_b_goals"] > 2.5 else "under_2_5"
