"""
World Cup Edge Lab — WSGI application for Vercel.

Zero external dependencies. Pure Python standard library.
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
_DATA = str(_ROOT / "data" / "ucl_semifinals_sample.json")
_CONFIG = str(_ROOT / "configs" / "default.json")
_WEB = _ROOT / "web"

_TEXT_EXTS = {".html", ".js", ".css", ".json", ".svg", ".txt", ".xml"}
_CT_MAP = {
    ".js": "application/javascript",
    ".css": "text/css",
    ".html": "text/html",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".woff2": "font/woff2",
}

# ═══════════════════════════════════════════════════════
# WSGI helpers
# ═══════════════════════════════════════════════════════


def _json(start, data, status="200 OK"):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    start(status, [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ])
    return [body]


def _static(environ, start, path):
    rel = "index.html" if path in ("", "/") else path.lstrip("/")
    fp = _WEB / rel
    if not fp.exists() or not fp.is_file():
        return None

    ct = _CT_MAP.get(fp.suffix, "application/octet-stream")
    body = fp.read_bytes()

    start("200 OK", [
        ("Content-Type", ct),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "public, max-age=3600"),
    ])
    return [body]


def _read_body(environ):
    length = int(environ.get("CONTENT_LENGTH", 0))
    if length <= 0:
        return {}
    raw = environ["wsgi.input"].read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


# ═══════════════════════════════════════════════════════
# Algorithm — Poisson / Scorelines
# ═══════════════════════════════════════════════════════


def poisson_pmf(k, lam):
    if k < 0:
        return 0.0
    if lam < 0:
        raise ValueError("lambda must be non-negative")
    return math.exp(-lam) * lam**k / math.factorial(k)


def _norm(m):
    t = sum(sum(r) for r in m)
    if t <= 0:
        raise ValueError("zero probability mass")
    return [[c / t for c in r] for r in m]


def independent_poisson_matrix(xa, xb, mg=10):
    m = []
    for ga in range(mg + 1):
        pa = poisson_pmf(ga, xa)
        m.append([pa * poisson_pmf(gb, xb) for gb in range(mg + 1)])
    return _norm(m)


def bivariate_poisson_matrix(xa, xb, sh=0.0, mg=10):
    if sh < 0 or sh > min(xa, xb):
        raise ValueError("invalid shared_lambda")
    ia, ib = xa - sh, xb - sh
    m = []
    for ga in range(mg + 1):
        row = []
        for gb in range(mg + 1):
            p = 0.0
            for s in range(min(ga, gb) + 1):
                p += poisson_pmf(s, sh) * poisson_pmf(ga - s, ia) * poisson_pmf(gb - s, ib)
            row.append(p)
        m.append(row)
    return _norm(m)


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


# ── Odds ────────────────────────────────────────────────


def dec_to_prob(odds):
    if odds <= 1:
        raise ValueError("decimal_odds must be > 1")
    return 1.0 / odds


def remove_overround(odds_map):
    implied = {k: dec_to_prob(v) for k, v in odds_map.items()}
    t = sum(implied.values())
    if t <= 0:
        raise ValueError("no implied probability")
    return {k: v / t for k, v in implied.items()}


# ── Recommendations ─────────────────────────────────────


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _label(v):
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
    return {"edge": edge, "value": val, "label": _label(val)}


# ── Timegate ────────────────────────────────────────────


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
    cs = set(cats) if cats else {"injury", "lineup", "odds", "result", "weather"}
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


# ── Backtest engine ─────────────────────────────────────


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_config(cfg, overrides=None):
    m = dict(cfg)
    for k, v in (overrides or {}).items():
        if isinstance(v, dict) and isinstance(m.get(k), dict):
            n = dict(m[k])
            n.update(v)
            m[k] = n
        else:
            m[k] = v
    return m


_WDL = ("team_a_win", "draw", "team_b_win")
_TOT = ("over_2_5", "under_2_5")


def _latest(records):
    if not records:
        return None
    return max(records, key=lambda r: _pts(r.get("observed_at")).timestamp())


def _sc_matrix(xa, xb, cfg):
    mg = int(cfg.get("max_goals", 10))
    if cfg.get("scoreline_model") == "bivariate_poisson":
        sl = min(float(cfg.get("shared_lambda", 0.0)), xa, xb)
        return bivariate_poisson_matrix(xa, xb, sh=sl, mg=mg)
    return independent_poisson_matrix(xa, xb, mg=mg)


def _mkp(osnap):
    if osnap is None:
        return {}
    p = {}
    if "h2h" in osnap:
        p.update(remove_overround(osnap["h2h"]))
    if "totals" in osnap:
        p.update(remove_overround(osnap["totals"]))
    return p


def _build_recs(mp, mkp, ls, cn, cfg):
    recs = []
    lc = cfg["lineup_confidence"].get(ls, cfg["lineup_confidence"]["unknown"])
    df = cfg["data_freshness"].get(cn, 0.8)
    for out, mpv in mp.items():
        if out not in mkp:
            continue
        r = score_recommendation(mpv, mkp[out], lc=lc, fr=df,
                                 mc=cfg.get("model_confidence", 1.0),
                                 rk=cfg.get("risk_modifier", 1.0))
        r.update({"market": "h2h" if out in _WDL else "totals",
                  "outcome": out,
                  "model_probability": round(mpv, 6),
                  "market_probability": round(mkp[out], 6),
                  "reason": f"Model edge adjusted by {ls} lineup confidence."})
        recs.append(r)
    if not recs:
        return {"market": None, "outcome": None, "value": None, "label": "unavailable",
                "edge": None, "reason": "No usable market odds."}
    return max(recs, key=lambda x: (x["value"], x["edge"]))


def _vi(match, ct):
    lu, la = filter_available_records(match.get("lineup_updates", []), ct)
    od, oa = filter_available_records(match.get("odds_snapshots", []), ct)
    ij, ia = filter_available_records(match.get("injury_updates", []), ct)
    return lu, od, ij, _ma(la, oa, ia)


def _ck_report(match, ck, cfg):
    lu, od, ij, audit = _vi(match, ck["time"])
    llu = _latest(lu)
    lod = _latest(od)
    im = float(cfg.get("lineup_impact_multiplier", 1.0))
    mx = float(cfg.get("minimum_xg", 0.2))
    xa = float(match["base_xg"]["team_a"])
    xb = float(match["base_xg"]["team_b"])
    if llu is not None:
        xa += float(llu.get("team_a_xg_delta", 0.0)) * im
        xb += float(llu.get("team_b_xg_delta", 0.0)) * im
    for ijr in ij:
        xa += float(ijr.get("team_a_xg_delta", 0.0)) * im
        xb += float(ijr.get("team_b_xg_delta", 0.0)) * im
    xa, xb = max(mx, xa), max(mx, xb)
    matrix = _sc_matrix(xa, xb, cfg)
    mp = aggregate_markets(matrix)
    mkpv = _mkp(lod)
    ls = llu.get("confidence", "unknown") if llu else "unknown"
    return {"time": ck["time"],
            "expected_goals": {"team_a": round(xa, 4), "team_b": round(xb, 4)},
            "lineup_status": ls,
            "lineup_note": llu.get("note") if llu else None,
            "probabilities": {k: round(v, 6) for k, v in mp.items()},
            "market_probabilities": {k: round(v, 6) for k, v in mkpv.items()},
            "best_recommendation": _build_recs(mp, mkpv, ls, ck["name"], cfg),
            "leakage_audit": audit}


def _aw(result):
    if result["team_a_goals"] > result["team_b_goals"]:
        return "team_a_win"
    if result["team_a_goals"] == result["team_b_goals"]:
        return "draw"
    return "team_b_win"


def _at(result):
    return "over_2_5" if result["team_a_goals"] + result["team_b_goals"] > 2.5 else "under_2_5"


def run_backtest(data_path, config_path, overrides=None):
    dataset = load_json(data_path)
    cfg = merge_config(load_json(config_path), overrides)
    matches, audit = [], _ea()
    wb, tb = [], []
    for m in dataset["matches"]:
        cr = {}
        for ck in m["checkpoints"]:
            r = _ck_report(m, ck, cfg)
            cr[ck["name"]] = r
            audit = _ma(audit, r["leakage_audit"])
        fn = m["checkpoints"][-1]["name"]
        fp = cr[fn]["probabilities"]
        wb.append(sum((fp[k] - (1.0 if k == _aw(m["result"]) else 0.0)) ** 2 for k in _WDL))
        tb.append(sum((fp[k] - (1.0 if k == _at(m["result"]) else 0.0)) ** 2 for k in _TOT))
        matches.append({"id": m["id"], "team_a": m["team_a"], "team_b": m["team_b"],
                        "result": m["result"], "checkpoints": cr})
    return {"parameter_set": cfg["parameter_set"],
            "scoreline_model": cfg.get("scoreline_model", "independent_poisson"),
            "effective_config": cfg,
            "matches": matches,
            "metrics": {"brier_wdl": round(sum(wb) / len(wb), 6) if wb else None,
                        "brier_over_under_2_5": round(sum(tb) / len(tb), 6) if tb else None},
            "leakage_audit": audit}


# ═══════════════════════════════════════════════════════
# WSGI Application
# ═══════════════════════════════════════════════════════


def app(environ, start_response):
    """Vercel WSGI entry point."""
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")

    # ── Health ──
    if path == "/api/health":
        return _json(start_response, {"status": "ok", "version": "1.0.0"})

    # ── Config ──
    if path == "/api/config" and method == "GET":
        try:
            return _json(start_response, load_json(_CONFIG))
        except Exception as e:
            return _json(start_response, {"error": str(e)}, "500 Internal Server Error")

    # ── Backtest ──
    if path == "/api/backtest":
        try:
            params = _read_body(environ)
            report = run_backtest(_DATA, _CONFIG, params.get("config_overrides", {}))
            return _json(start_response, {
                "report": report,
                "effective_config": report.get("effective_config", {}),
            })
        except Exception as e:
            return _json(start_response, {"error": str(e)}, "500 Internal Server Error")

    # ── Static files ──
    result = _static(environ, start_response, path)
    if result is not None:
        return result

    # ── 404 ──
    return _json(start_response, {"error": "Not Found"}, "404 Not Found")
