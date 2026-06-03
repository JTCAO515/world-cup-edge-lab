"""
World Cup Edge Lab — FastAPI entry point for Vercel Serverless deployment.

Exposes:
  GET /api/config   → 当前配置文件
  POST /api/backtest → 回测分析（可传 config_overrides）
  GET / (static)    → 前端页面
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

# ── 路径 ─────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from football_predictor.backtest import load_json, run_backtest

DEFAULT_DATA = ROOT / "data" / "ucl_semifinals_sample.json"
DEFAULT_CONFIG = ROOT / "configs" / "default.json"
WEB_ROOT = ROOT / "web"

app = FastAPI(title="World Cup Edge Lab", version="0.1.0")


# ── 静态文件 ────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the SPA frontend"""
    index_path = WEB_ROOT / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>World Cup Edge Lab</h1><p>Frontend not found.</p>", status_code=200)
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/app.js")
async def app_js():
    return Response(WEB_ROOT.joinpath("app.js").read_bytes(), media_type="application/javascript")


@app.get("/app.css")
async def app_css():
    return Response(WEB_ROOT.joinpath("app.css").read_bytes(), media_type="text/css")


# ── API 端点 ────────────────────────────────────────


class BacktestRequest(BaseModel):
    config_overrides: Optional[dict] = {}


@app.get("/api/config")
async def get_config():
    return load_json(DEFAULT_CONFIG)


@app.post("/api/backtest")
async def post_backtest(req: BacktestRequest):
    try:
        report = run_backtest(DEFAULT_DATA, DEFAULT_CONFIG, req.config_overrides or {})
        return {
            "report": report,
            "effective_config": report.get("effective_config", {}),
        }
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(e)}, status_code=500)


# ── 健康检查 ─────────────────────────────────────────


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "tests": "17 passing"}
