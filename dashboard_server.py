"""
Dashboard Server: a zero-dependency lightweight web server for the IBKR Trading Bot.
Serves dashboard.html, real-time diagnostic JSONs, active logs, and engine controls.
"""

import os
import sys
import json
import csv
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import subprocess

# Add workspace directory to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
import engine_control
from utils import get_logger, setup_logging

logger = get_logger("dashboard_server")

PORT = 8050
_PROJECT_DIR = Path(__file__).resolve().parent
HEALTH_FILE = _PROJECT_DIR / getattr(config, "HEALTH_STATUS_FILE", "trading_health.json")
LOG_FILE = _PROJECT_DIR / "trading_logs.txt"
HISTORY_FILE = _PROJECT_DIR / "trade_history.csv"
HTML_FILE = _PROJECT_DIR / "dashboard.html"

class DashboardHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Override to suppress noisy request logging in terminal
        pass

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # Serve static dashboard HTML
        if path in ("/", "/index.html", "/dashboard"):
            if not HTML_FILE.exists():
                self.send_error_response(404, "dashboard.html not found.")
                return
            
            try:
                content = HTML_FILE.read_text(encoding="utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
            except Exception as e:
                self.send_error_response(500, f"Error reading dashboard: {e}")
            return

        # Serve dynamic health status
        elif path == "/api/status":
            status_data = {}
            if HEALTH_FILE.exists():
                try:
                    status_data = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass
            
            # Add basic flags if JSON is empty or missing
            status_data.setdefault("connected", False)
            status_data.setdefault("engine_running", engine_control.is_engine_running())
            status_data.setdefault("sentry_status", "UNKNOWN")
            
            self.send_json_response(status_data)
            return

        # Serve recent engine logs (last 100 lines)
        elif path == "/api/logs":
            logs = []
            if LOG_FILE.exists():
                try:
                    with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        logs = lines[-100:]
                except Exception as e:
                    logs = [f"Error reading log file: {e}"]
            else:
                logs = ["No log file found. Engine has not generated trading_logs.txt yet."]
                
            self.send_json_response({"logs": "".join(logs)})
            return

        # Serve dynamic trade history reconstructed
        elif path == "/api/history":
            history = []
            if HISTORY_FILE.exists():
                try:
                    with open(HISTORY_FILE, mode="r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            history.append(dict(row))
                except Exception as e:
                    logger.debug(f"History fetch error: {e}")
            self.send_json_response({"history": history[::-1]}) # Newest first
            return

        else:
            self.send_error_response(404, "Endpoint not found.")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # Control API to start the engine
        if path == "/api/control/start":
            is_running = engine_control.is_engine_running()
            if is_running:
                self.send_json_response({"success": False, "message": "Engine is already running."})
                return

            logger.info("Dashboard API: start requested.")
            # Trigger engine_sentry auto-bind immediately by cleaning lock or launching
            try:
                python_cmd = sys.executable or "python"
                launcher_path = _PROJECT_DIR / "trading_launcher.py"
                
                # Launch detached engine
                if os.name == "nt":
                    subprocess.Popen(
                        [python_cmd, str(launcher_path)],
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                        close_fds=True
                    )
                else:
                    subprocess.Popen(
                        [python_cmd, str(launcher_path)],
                        preexec_fn=os.setpgrp,
                        close_fds=True
                    )
                self.send_json_response({"success": True, "message": "Engine start request dispatched."})
            except Exception as e:
                self.send_json_response({"success": False, "message": f"Failed to dispatch start: {e}"})
            return

        # Control API to gracefully stop the engine
        elif path == "/api/control/stop":
            is_running = engine_control.is_engine_running()
            if not is_running:
                self.send_json_response({"success": False, "message": "Engine is not active."})
                return

            logger.info("Dashboard API: graceful stop requested.")
            engine_control.request_restart() # Sets the exit file which signals engine to stop
            self.send_json_response({"success": True, "message": "Graceful stop signal emitted. Checking PID..."})
            return

        # Control API to force-restart the engine
        elif path == "/api/control/restart":
            logger.info("Dashboard API: restart requested.")
            engine_control.request_restart()
            try:
                python_cmd = sys.executable or "python"
                launcher_path = _PROJECT_DIR / "trading_launcher.py"
                
                if os.name == "nt":
                    subprocess.Popen(
                        [python_cmd, str(launcher_path)],
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                        close_fds=True
                    )
                else:
                    subprocess.Popen(
                        [python_cmd, str(launcher_path)],
                        preexec_fn=os.setpgrp,
                        close_fds=True
                    )
                self.send_json_response({"success": True, "message": "Engine restart sequence coordinated."})
            except Exception as e:
                self.send_json_response({"success": False, "message": f"Restart sequence fail: {e}"})
            return

        else:
            self.send_error_response(404, "Endpoint not found.")

    def send_json_response(self, data):
        try:
            content = json.dumps(data, default=str)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        except Exception as e:
            self.send_error_response(500, f"JSON serialization error: {e}")

    def send_error_response(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode("utf-8"))


def run_server():
    setup_logging()
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, DashboardHTTPHandler)
    logger.info(f"Dashboard Web Server active at http://localhost:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Dashboard Web Server shutting down...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
