"""
Vercel Serverless entry point.
FastAPI app lives in api/main.py — re-exported here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.main import app
