"""
World Cup Edge Lab — Vercel raw serverless handler.

Uses Vercel's native handler(event, context) interface.
No FastAPI, no ASGI/WSGI detection issues.
"""
import json
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from football_predictor.backtest import load_json, run_backtest

DATA_PATH = ROOT / "data" / "ucl_semifinals_sample.json"
CONFIG_PATH = ROOT / "configs" / "default.json"
WEB_ROOT = ROOT / "web"
STATIC_TYPES = {
    ".js": "application/javascript",
    ".css": "text/css",
    ".html": "text/html",
    ".json": "application/json",
}


def _static_file(path):
    """Serve a static file from web/. Returns (body, content_type)."""
    if path in ("", "/"):
        path = "index.html"
    elif path.startswith("/"):
        path = path[1:]

    file_path = WEB_ROOT / path
    if not file_path.exists() or not file_path.is_file():
        return None, None

    suffix = file_path.suffix
    ct = STATIC_TYPES.get(suffix, "application/octet-stream")
    return file_path.read_bytes(), ct


def handler(event, context):
    """Vercel raw serverless handler."""
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")

    # ── Health ──
    if path == "/api/health":
        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"status": "ok", "version": "0.1.0"}),
        }

    # ── Config ──
    if path == "/api/config" and method == "GET":
        try:
            config = load_json(str(CONFIG_PATH))
            return {
                "statusCode": 200,
                "headers": {"content-type": "application/json"},
                "body": json.dumps(config),
            }
        except Exception as e:
            return {
                "statusCode": 500,
                "headers": {"content-type": "application/json"},
                "body": json.dumps({"error": str(e)}),
            }

    # ── Backtest ──
    if path == "/api/backtest" and method == "POST":
        try:
            overrides = {}
            if event.get("body"):
                body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
                overrides = body.get("config_overrides", {})
            report = run_backtest(str(DATA_PATH), str(CONFIG_PATH), overrides)
            return {
                "statusCode": 200,
                "headers": {"content-type": "application/json"},
                "body": json.dumps({"report": report, "effective_config": report.get("effective_config", {})}, ensure_ascii=False),
            }
        except Exception as e:
            return {
                "statusCode": 500,
                "headers": {"content-type": "application/json"},
                "body": json.dumps({"error": str(e)}),
            }

    # ── Static files ──
    body, ct = _static_file(path)
    if body is not None:
        return {
            "statusCode": 200,
            "headers": {
                "content-type": ct,
                "cache-control": "public, max-age=3600",
            },
            "body": body if isinstance(body, str) else body.decode("utf-8"),
        }

    return {
        "statusCode": 404,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": "Not Found"}),
    }
