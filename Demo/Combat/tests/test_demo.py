"""Exercise the actual HTTP boundary and CLI, including invalid input and isolation."""

import http.client
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from demo import create_server, MAX_BODY_BYTES


class DemoIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def request(self, method, path, body=None, content_type="application/json"):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers={"Content-Type": content_type})
            response = connection.getresponse()
            return response.status, response.getheader("Content-Type"), response.read()
        finally:
            connection.close()

    def test_web_and_health_are_available_but_repository_files_are_not(self):
        for path in ("/", "/app.js", "/style.css"):
            status, _, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertTrue(body)
        status, _, body = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["ue_runtime"])
        for path in ("/../combat.py", "/%2e%2e/combat.py", "/.git/config", "/combat.py"):
            self.assertEqual(self.request("GET", path)[0], 404)

    def test_every_published_scenario_can_be_replayed_through_api(self):
        status, content_type, body = self.request("GET", "/api/scenarios")
        self.assertEqual(status, 200)
        self.assertIn("utf-8", content_type)
        scenarios = json.loads(body)["scenarios"]
        self.assertGreaterEqual(len(scenarios), 4)
        for name, scenario in scenarios.items():
            with self.subTest(scenario=name):
                payload = {key: scenario[key] for key in ("initial", "actions")}
                status, _, result = self.request("POST", "/api/simulate", json.dumps(payload))
                self.assertEqual(status, 200, result)
                self.assertEqual(len(json.loads(result)["steps"]), len(payload["actions"]))

    def test_requests_are_stateless(self):
        status, _, body = self.request("POST", "/api/simulate", '{"actions":[{"type":"damage","amount":80}]}')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["state"]["health"], 20)
        status, _, body = self.request("POST", "/api/simulate", '{"actions":[]}')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["state"]["health"], 100)

    def test_invalid_inputs_return_json_errors(self):
        for body in (b"\xff", b"{", b"[]", b'{"actions":[{"type":"damage","amount":NaN}]}',
                     b'{"actions":[{"type":"heal","amount":true}]}'):
            with self.subTest(body=body):
                status, _, response = self.request("POST", "/api/simulate", body)
                self.assertEqual(status, 400)
                self.assertTrue(json.loads(response)["error"])
        self.assertEqual(self.request("POST", "/api/simulate", "{}", "text/plain")[0], 415)
        self.assertEqual(self.request("POST", "/api/simulate", " " * (MAX_BODY_BYTES + 1))[0], 413)

    def test_cli_json_is_reproducible_and_unknown_scenario_fails(self):
        command = [sys.executable, str(ROOT / "demo.py"), "scenario", "--name", "normal", "--json"]
        first = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=10)
        second = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=10)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        invalid = subprocess.run(command[:-3] + ["--name", "missing"], capture_output=True, encoding="utf-8", timeout=10)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("Unknown scenario", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
