"""
World Cup Edge Lab — Vercel Serverless entry point.

Self-contained FastAPI application.
"""
import json
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

# ── Paths ────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from football_predictor.backtest import load_json, run_backtest

DATA_PATH = ROOT / "data" / "ucl_semifinals_sample.json"
CONFIG_PATH = ROOT / "configs" / "default.json"
WEB_ROOT = ROOT / "web"

app = FastAPI(title="World Cup Edge Lab", version="0.1.0")


# ── Static files ────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the SPA frontend"""
    index_path = WEB_ROOT / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            "<h1>World Cup Edge Lab</h1><p>Frontend not found.</p>",
            status_code=200,
        )
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/app.js")
async def app_js():
    return Response(
        WEB_ROOT.joinpath("app.js").read_bytes(),
        media_type="application/javascript",
    )


@app.get("/app.css")
async def app_css():
    return Response(
        WEB_ROOT.joinpath("app.css").read_bytes(),
        media_type="text/css",
    )


# ── API endpoints ───────────────────────────────────


class BacktestRequest(BaseModel):
    config_overrides: Optional[dict] = {}


@app.get("/api/config")
async def get_config():
    return load_json(str(CONFIG_PATH))


@app.post("/api/backtest")
async def post_backtest(req: BacktestRequest):
    try:
        report = run_backtest(
            str(DATA_PATH), str(CONFIG_PATH), req.config_overrides or {}
        )
        return {
            "report": report,
            "effective_config": report.get("effective_config", {}),
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Health check ────────────────────────────────────


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "tests": "17 passing"}
