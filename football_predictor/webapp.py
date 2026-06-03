import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from football_predictor.backtest import load_json, run_backtest


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_PATH = ROOT / "data" / "ucl_semifinals_sample.json"
DEFAULT_CONFIG_PATH = ROOT / "configs" / "default.json"
WEB_ROOT = ROOT / "web"


def build_report_payload(config_overrides=None, data_path=DEFAULT_DATA_PATH, config_path=DEFAULT_CONFIG_PATH):
    report = run_backtest(data_path, config_path, config_overrides or {})
    return {
        "report": report,
        "effective_config": report["effective_config"],
    }


class DashboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            self._send_json(load_json(DEFAULT_CONFIG_PATH))
            return
        if parsed.path == "/api/backtest":
            self._send_json(build_report_payload())
            return

        static_path = "index.html" if parsed.path in {"", "/"} else parsed.path.lstrip("/")
        self._send_file(WEB_ROOT / static_path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/backtest":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON body"}, status=400)
            return

        self._send_json(build_report_payload(payload.get("config_overrides", {})))

    def log_message(self, format, *args):
        return


def build_parser():
    parser = argparse.ArgumentParser(description="Run the local football prediction dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
