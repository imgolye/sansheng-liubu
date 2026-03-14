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
        self.assertTrue(dashboard["openclaw"]["gateway"]["rpc"]["ok"])
        self.assertEqual(dashboard["openclaw"]["browser"]["profile"], "user")
        self.assertEqual(dashboard["openclaw"]["nativeSkills"]["check"]["summary"]["missingRequirements"], 1)
        self.assertEqual(dashboard["openclaw"]["agentParams"][0]["id"], "taizi")
        self.assertTrue(dashboard["contextHub"]["installed"])
        self.assertEqual(dashboard["contextHub"]["version"], "0.1.2")

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

    def test_events_stream_emits_dashboard_event(self):
        self.request_json("POST", "/api/auth/login", {"mode": "token", "token": TEST_TOKEN})
        request = urllib.request.Request(f"{self.base_url}/events", method="GET")
        response = self.opener.open(request, timeout=10)
        with response:
            chunk = response.read(256).decode("utf-8")
        self.assertIn("event: dashboard", chunk)

    def test_context_hub_search_and_annotate(self):
        auth = self.request_json("POST", "/api/auth/login", {"mode": "token", "token": TEST_TOKEN})
        search = self.request_json(
            "POST",
            "/api/actions/context-hub/search",
            {
                "actionToken": auth["actionToken"],
                "query": "openai",
                "limit": 5,
            },
        )
        self.assertTrue(search["ok"])
        self.assertEqual(search["result"]["results"][0]["id"], "openai/chat")

        annotate = self.request_json(
            "POST",
            "/api/actions/context-hub/annotate",
            {
                "actionToken": auth["actionToken"],
                "id": "openai/chat",
                "note": "Remember the raw body webhook caveat.",
            },
        )
        self.assertTrue(annotate["ok"])
        self.assertEqual(annotate["result"]["id"], "openai/chat")
        self.assertEqual(annotate["dashboard"]["contextHub"]["annotations"]["total"], 1)

    def test_management_rule_channel_and_alert_loop(self):
        auth = self.request_json("POST", "/api/auth/login", {"mode": "token", "token": TEST_TOKEN})
        channel = self.request_json(
            "POST",
            "/api/actions/management/channel/save",
            {
                "actionToken": auth["actionToken"],
                "name": "Fixture Feishu",
                "type": "feishu",
                "target": "fixture://feishu/ops-room",
            },
        )
        self.assertTrue(channel["ok"])

        rule = self.request_json(
            "POST",
            "/api/actions/management/rule/save",
            {
                "actionToken": auth["actionToken"],
                "name": "完成即通知",
                "triggerType": "critical_task_done",
                "severity": "critical",
                "matchText": "JJC-TEST-002",
                "channelIds": [channel["channel"]["id"]],
            },
        )
        self.assertTrue(rule["ok"])
        automation = rule["dashboard"]["management"]["automation"]
        self.assertEqual(automation["summary"]["activeRules"], 1)
        self.assertGreaterEqual(len(automation["alerts"]), 1)
        self.assertEqual(automation["alerts"][0]["deliveries"][0]["outcome"], "success")

    def test_management_bootstrap_and_report_export(self):
        auth = self.request_json("POST", "/api/auth/login", {"mode": "token", "token": TEST_TOKEN})
        bootstrap = self.request_json(
            "POST",
            "/api/actions/management/bootstrap",
            {"actionToken": auth["actionToken"]},
        )
        self.assertTrue(bootstrap["ok"])
        self.assertEqual(bootstrap["result"]["total"], 3)
        self.assertEqual(len(bootstrap["dashboard"]["management"]["automation"]["rules"]), 3)

        exported = self.request_json(
            "POST",
            "/api/actions/management/report/export",
            {"actionToken": auth["actionToken"]},
        )
        self.assertTrue(exported["ok"])
        self.assertTrue(exported["report"]["path"].endswith("weekly-ops-report.md"))

    def test_orchestration_workflow_and_policy_save(self):
        auth = self.request_json("POST", "/api/auth/login", {"mode": "token", "token": TEST_TOKEN})
        workflow = self.request_json(
            "POST",
            "/api/actions/orchestration/workflow/save",
            {
                "actionToken": auth["actionToken"],
                "name": "Engineering -> QA -> Ops",
                "description": "Visual orchestration test flow",
                "lanes": [{"id": "build", "title": "Engineering"}, {"id": "qa", "title": "Quality"}, {"id": "ops", "title": "Ops"}],
                "nodes": [{"id": "build-node", "laneId": "build", "title": "Engineering", "agentId": "taizi"}],
            },
        )
        self.assertTrue(workflow["ok"])
        self.assertEqual(workflow["workflow"]["name"], "Engineering -> QA -> Ops")

        policy = self.request_json(
            "POST",
            "/api/actions/orchestration/policy/save",
            {
                "actionToken": auth["actionToken"],
                "name": "release keyword routes to taizi",
                "strategyType": "keyword_department",
                "keyword": "release",
                "targetAgentId": "taizi",
                "priorityLevel": "high",
                "queueName": "release-fast-lane",
            },
        )
        self.assertTrue(policy["ok"])
        orchestration = policy["dashboard"]["orchestration"]
        self.assertEqual(len(orchestration["workflows"]), 1)
        self.assertEqual(orchestration["routingPolicies"][0]["targetAgentId"], "taizi")

    def test_tenant_api_key_and_rest_platform(self):
        auth = self.request_json("POST", "/api/auth/login", {"mode": "token", "token": TEST_TOKEN})
        tenant = self.request_json(
            "POST",
            "/api/actions/admin/tenant/save",
            {
                "actionToken": auth["actionToken"],
                "name": "Fixture Tenant",
                "slug": "fixture-tenant",
                "primaryOpenclawDir": str(self.openclaw_dir),
            },
        )
        self.assertTrue(tenant["ok"])
        tenant_id = tenant["tenant"]["id"]

        binding = self.request_json(
            "POST",
            "/api/actions/admin/tenant/installation/save",
            {
                "actionToken": auth["actionToken"],
                "tenantId": tenant_id,
                "openclawDir": str(self.openclaw_dir),
                "bindingLabel": "Fixture Tenant Prod",
                "role": "primary",
            },
        )
        self.assertTrue(binding["ok"])

        api_key = self.request_json(
            "POST",
            "/api/actions/admin/tenant/api-key/create",
            {
                "actionToken": auth["actionToken"],
                "tenantId": tenant_id,
                "name": "ci-sync",
                "scopes": ["tenant:read", "dashboard:read", "tasks:read", "tasks:write"],
            },
        )
        self.assertTrue(api_key["ok"])
        raw_key = api_key["apiKey"]["rawKey"]

        headers = {"X-API-Key": raw_key}
        dashboard_request = urllib.request.Request(
            f"{self.base_url}/api/v1/tenants/{tenant_id}/dashboard",
            headers=headers,
            method="GET",
        )
        with urllib.request.urlopen(dashboard_request, timeout=10) as response:
            tenant_dashboard = json.loads(response.read().decode("utf-8"))
        self.assertTrue(tenant_dashboard["ok"])
        self.assertEqual(tenant_dashboard["tenant"]["slug"], "fixture-tenant")
        self.assertGreaterEqual(len(tenant_dashboard["dashboard"]["taskIndex"]), 2)

        task_request = urllib.request.Request(
            f"{self.base_url}/api/v1/tenants/{tenant_id}/tasks",
            data=json.dumps({"title": "通过租户 API 创建任务", "remark": "From CI"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-API-Key": raw_key},
            method="POST",
        )
        with urllib.request.urlopen(task_request, timeout=10) as response:
            created_task = json.loads(response.read().decode("utf-8"))
        self.assertTrue(created_task["ok"])
        self.assertTrue(created_task["taskId"].startswith("JJC-"))


if __name__ == "__main__":
    unittest.main()
