import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from state import StateStore
from utils import load_env, load_json


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"
BOT_PROCESS = None


def read_tail(path, lines=80):
    try:
        content = Path(path).read_text(encoding="utf-8").splitlines()
        return "\n".join(content[-lines:])
    except FileNotFoundError:
        return ""


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        content_type = "text/html; charset=utf-8" if path.suffix == ".html" else "text/plain; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/status":
            load_env()
            config = load_json(CONFIG)
            store = StateStore(config["state_path"])
            state = store.load()
            global BOT_PROCESS
            running = BOT_PROCESS is not None and BOT_PROCESS.poll() is None
            self.send_json(
                200,
                {
                    "config": config,
                    "state": state,
                    "bot_running": running,
                    "live_enabled": __import__("os").getenv("ONDO_LIVE_ENABLED") == "1",
                    "key_present": bool(__import__("os").getenv("ONDO_KEY_ID")),
                    "secret_present": bool(__import__("os").getenv("ONDO_API_SECRET")),
                    "log_tail": read_tail(config["log_path"]),
                },
            )
            return
        route = unquote(self.path.split("?", 1)[0])
        if route in {"/", "/console"}:
            self.send_file(ROOT / "web_console.html")
            return
        safe = route.strip("/").replace("\\", "/")
        if ".." in safe:
            self.send_error(403)
            return
        self.send_file(ROOT / safe)

    def do_POST(self):
        global BOT_PROCESS
        if self.path == "/api/run-once":
            config = load_json(CONFIG)
            completed = subprocess.run(
                [sys.executable, "main.py", "--config", "config.json", "--once"],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                timeout=60,
            )
            self.send_json(
                200,
                {
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "market": config.get("market"),
                    "market_url": f"https://app.ondoperps.xyz/trade/perps/{config.get('market')}",
                },
            )
            return
        if self.path == "/api/start":
            if BOT_PROCESS is not None and BOT_PROCESS.poll() is None:
                self.send_json(200, {"status": "already_running"})
                return
            BOT_PROCESS = subprocess.Popen(
                [sys.executable, "main.py", "--config", "config.json"],
                cwd=str(ROOT),
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.send_json(200, {"status": "started", "pid": BOT_PROCESS.pid})
            return
        if self.path == "/api/stop":
            if BOT_PROCESS is None or BOT_PROCESS.poll() is not None:
                self.send_json(200, {"status": "not_running"})
                return
            BOT_PROCESS.terminate()
            self.send_json(200, {"status": "stopping"})
            return
        self.send_error(404)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def main():
    port = int(os.getenv("LLV_WEB_PORT", "8780"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Low Loss Volume Maker console: http://127.0.0.1:{port}/console")
    server.serve_forever()


if __name__ == "__main__":
    main()
