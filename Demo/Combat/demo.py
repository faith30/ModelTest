#!/usr/bin/env python3
"""Run the standalone combat reference demo using Python 3.9+ only."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from combat import simulate

ROOT = Path(__file__).resolve().parent
MAX_BODY_BYTES = 65536
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


def reject_constant(value):
    raise ValueError("JSON cannot contain " + value)


def read_json(text):
    return json.loads(text, parse_constant=reject_constant)


def scenarios():
    return read_json((ROOT / "scenarios.json").read_text(encoding="utf-8"))


def scenario_request(scenario):
    return {"initial": scenario["initial"], "actions": scenario["actions"]}


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "CombatDemo/1.0"

    def send_content(self, status, content, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)

    def send_json(self, status, value):
        content = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_content(status, content, "application/json; charset=utf-8")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health":
            self.send_json(200, {"status": "ok", "demo": "combat-reference", "ue_runtime": False})
        elif path == "/api/scenarios":
            self.send_json(200, {"scenarios": scenarios()})
        elif path in STATIC_FILES:
            filename, content_type = STATIC_FILES[path]
            self.send_content(200, (ROOT / "web" / filename).read_bytes(), content_type)
        else:
            self.send_json(404, {"error": "Not found"})

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != "/api/simulate":
            self.send_json(404, {"error": "Not found"})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "Use Content-Type: application/json"})
            return
        if self.headers.get("Transfer-Encoding"):
            self.send_json(400, {"error": "Chunked requests are not supported"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0:
            self.send_json(411, {"error": "A valid Content-Length is required"})
            return
        if length > MAX_BODY_BYTES:
            self.send_json(413, {"error": "Request exceeds 64 KiB"})
            return
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete request body")
            request = read_json(body.decode("utf-8"))
            result = simulate(request)
        except (ValueError, UnicodeError, RecursionError) as error:
            self.send_json(400, {"error": str(error)})
            return
        self.send_json(200, result)

    def log_message(self, format, *args):
        # Deliberately log only request metadata, never request bodies or credentials.
        super().log_message(format, *args)


class DemoServer(ThreadingHTTPServer):
    daemon_threads = True

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        return connection, address


def create_server(host="127.0.0.1", port=8000):
    return DemoServer((host, port), DemoHandler)


def describe_state(state):
    return "health={health:g}/{max_health:g}, immunity={damage_immunity}, death={death_state}".format(**state)


def main(argv=None):
    # Windows console encodings should not prevent the Chinese event log from running.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List included scenarios")
    run = commands.add_parser("scenario", help="Replay a scenario without starting a server")
    source = run.add_mutually_exclusive_group()
    source.add_argument("--name", help="Built-in scenario ID (default: normal)")
    source.add_argument("--file", type=Path, help="JSON file with initial and actions fields")
    run.add_argument("--json", action="store_true", help="Emit machine-readable results")
    server = commands.add_parser("serve", help="Start the interactive web demo")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            for name, item in scenarios().items():
                print(name + ": " + item["title"] + " — " + item["description"])
        elif args.command == "scenario":
            if args.file:
                request = read_json(args.file.read_text(encoding="utf-8"))
            else:
                name = args.name or "normal"
                available = scenarios()
                if name not in available:
                    raise ValueError("Unknown scenario: " + name + ". Use the list command.")
                request = scenario_request(available[name])
            result = simulate(request)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
            else:
                print("Standalone combat reference demo (UE engine is not running)")
                print("Initial: " + describe_state(result["initial"]))
                for step in result["steps"]:
                    print("[{index:02d}] {action[type]} -> ".format(**step) + describe_state(step["after"]))
                    for event in step["events"]:
                        print("     " + event["type"] + ": " + event["message"])
                print("Final: " + describe_state(result["state"]))
        else:
            if not 0 <= args.port <= 65535:
                raise ValueError("Port must be between 0 and 65535")
            with create_server(args.host, args.port) as httpd:
                print("Combat demo: http://{}:{}/".format(args.host, httpd.server_port), flush=True)
                print("Use the platform port proxy for remote access. Press Ctrl+C to stop.", flush=True)
                try:
                    httpd.serve_forever()
                except KeyboardInterrupt:
                    pass
    except (ValueError, OSError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
