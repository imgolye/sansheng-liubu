import json
import pathlib
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

from dashboard_test_support import TEST_TOKEN, create_fixture_openclaw_dir, patched_openclaw_path, running_dashboard_server


ROOT = pathlib.Path(__file__).resolve().parents[1]


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.openclaw_dir = create_fixture_openclaw_dir(self.tmpdir.name)
        self.path_patch = patched_openclaw_path(self.openclaw_dir)
        self.path_patch.__enter__()
        self.server_ctx = running_dashboard_server(self.openclaw_dir, frontend_dist=str(ROOT / "frontend" / "dist"))
        self.base_url = self.server_ctx.__enter__()
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def tearDown(self):
        self.server_ctx.__exit__(None, None, None)
        self.path_patch.__exit__(None, None, None)
        self.tmpdir.cleanup()

    def request_json(self, method, path, payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        response = self.opener.open(request, timeout=10)
        with response:
            return json.loads(response.read().decode("utf-8"))

    def test_login_and_dashboard_payload(self):
        auth = self.request_json("POST", "/api/auth/login", {"mode": "token", "token": TEST_TOKEN})
        self.assertTrue(auth["ok"])
        self.assertEqual(auth["session"]["role"], "owner")
        self.assertTrue(auth["actionToken"])

        dashboard = self.request_json("GET", "/api/dashboard")
        self.assertEqual(dashboard["theme"]["language"], "zh-CN")
        self.assertEqual(dashboard["routerAgentId"], "taizi")
        self.assertGreaterEqual(len(dashboard["taskIndex"]), 2)
        self.assertTrue(dashboard["conversations"]["supported"])

    def test_conversation_send_updates_transcript(self):
        auth = self.request_json("POST", "/api/auth/login", {"mode": "token", "token": TEST_TOKEN})
        send = self.request_json(
            "POST",
            "/api/actions/conversations/send",
            {
                "actionToken": auth["actionToken"],
                "agentId": "taizi",
                "sessionId": "main",
                "message": "请回报当前测试状态",
                "thinking": "low",
            },
        )
        self.assertTrue(send["ok"])
        self.assertEqual(send["session"]["sessionId"], "main")
        self.assertIn("已收到", send["message"])
        items = send["conversation"]["items"]
        self.assertTrue(any("请回报当前测试状态" in item.get("text", "") for item in items))
        self.assertTrue(any("已收到：请回报当前测试状态" in item.get("text", "") for item in items))

    def test_requires_auth_for_dashboard(self):
        request = urllib.request.Request(f"{self.base_url}/api/dashboard", method="GET")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(caught.exception.code, 401)


if __name__ == "__main__":
    unittest.main()
