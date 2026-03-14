import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "templates" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import dashboard_store


class DashboardStoreTests(unittest.TestCase):
    def test_migrates_legacy_json_files_into_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            openclaw_dir = Path(tmpdir)
            dashboard = openclaw_dir / "dashboard"
            dashboard.mkdir(parents=True, exist_ok=True)

            (dashboard / "product_users.json").write_text(
                json.dumps(
                    {
                        "users": [
                            {
                                "id": "u-1",
                                "username": "Owner",
                                "displayName": "Main Owner",
                                "role": "owner",
                                "passwordHash": "hash-1",
                                "status": "active",
                                "createdAt": "2026-03-14T00:00:00Z",
                                "lastLoginAt": "",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (dashboard / "audit-log.jsonl").write_text(
                json.dumps(
                    {
                        "id": "evt-1",
                        "at": "2026-03-14T01:00:00Z",
                        "action": "login",
                        "outcome": "success",
                        "detail": "Owner logged in",
                        "actor": {"displayName": "Main Owner", "role": "owner"},
                        "meta": {"mode": "password"},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            users = dashboard_store.load_product_users(openclaw_dir)
            events = dashboard_store.load_audit_events(openclaw_dir, limit=10)

            self.assertEqual(len(users), 1)
            self.assertEqual(users[0]["username"], "owner")
            self.assertEqual(users[0]["displayName"], "Main Owner")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["action"], "login")
            self.assertTrue((dashboard / "dashboard.db").exists())

    def test_roundtrip_users_and_audit_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            openclaw_dir = Path(tmpdir)

            dashboard_store.save_product_users(
                openclaw_dir,
                [
                    {
                        "id": "u-1",
                        "username": "ops",
                        "displayName": "Ops Lead",
                        "role": "operator",
                        "passwordHash": "hash-ops",
                        "status": "active",
                        "createdAt": "2026-03-14T02:00:00Z",
                        "lastLoginAt": "",
                    }
                ],
            )
            users = dashboard_store.load_product_users(openclaw_dir)
            self.assertEqual(len(users), 1)
            self.assertEqual(users[0]["role"], "operator")

            event = dashboard_store.append_audit_event(
                openclaw_dir,
                "task_create",
                {"displayName": "Ops Lead", "role": "operator"},
                detail="Created task T-1",
                meta={"taskId": "T-1"},
            )
            events = dashboard_store.load_audit_events(openclaw_dir, limit=5)

            self.assertEqual(event["action"], "task_create")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["meta"]["taskId"], "T-1")

    def test_roundtrip_installation_registry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            openclaw_dir = Path(tmpdir)

            current = dashboard_store.upsert_product_installation(
                openclaw_dir,
                {
                    "openclawDir": "/tmp/openclaw-a",
                    "label": "Imperial HQ",
                    "projectDir": "/repo/a",
                    "theme": "imperial",
                    "routerAgentId": "taizi",
                },
            )
            dashboard_store.upsert_product_installation(
                openclaw_dir,
                {
                    "openclawDir": "/tmp/openclaw-b",
                    "label": "Corporate Ops",
                    "projectDir": "/repo/b",
                    "theme": "corporate",
                    "routerAgentId": "secretary",
                },
            )
            installations = dashboard_store.load_product_installations(openclaw_dir)

            self.assertEqual(len(installations), 2)
            self.assertEqual({item["theme"] for item in installations}, {"imperial", "corporate"})
            self.assertTrue(
                dashboard_store.delete_product_installation(openclaw_dir, current["openclawDir"])
            )
            self.assertEqual(len(dashboard_store.load_product_installations(openclaw_dir)), 1)

    def test_management_run_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            openclaw_dir = Path(tmpdir)

            created = dashboard_store.create_management_run(
                openclaw_dir,
                {
                    "title": "商城交付闭环",
                    "goal": "从需求到发布一路可追踪",
                    "owner": "Ops Lead",
                    "linkedTaskId": "TASK-001",
                    "riskLevel": "high",
                },
            )
            self.assertEqual(created["stageKey"], "intake")
            self.assertEqual(created["stages"][0]["status"], "active")

            advanced = dashboard_store.update_management_run(
                openclaw_dir,
                created["id"],
                "advance",
                note="需求已完成对齐",
            )
            self.assertEqual(advanced["stageKey"], "plan")
            self.assertEqual(advanced["stages"][0]["status"], "done")
            self.assertEqual(advanced["stages"][1]["status"], "active")

            blocked = dashboard_store.update_management_run(
                openclaw_dir,
                created["id"],
                "block",
                note="等待联调环境",
            )
            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(blocked["stages"][1]["status"], "blocked")

            resumed = dashboard_store.update_management_run(
                openclaw_dir,
                created["id"],
                "resume",
                note="联调环境已恢复",
            )
            self.assertEqual(resumed["status"], "active")
            self.assertEqual(resumed["stages"][1]["status"], "active")

            completed = dashboard_store.update_management_run(openclaw_dir, created["id"], "complete")
            self.assertEqual(completed["status"], "complete")
            self.assertTrue(completed["completedAt"])

    def test_automation_rules_channels_and_alerts_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            openclaw_dir = Path(tmpdir)

            channel = dashboard_store.save_notification_channel(
                openclaw_dir,
                {
                    "name": "Ops Feishu",
                    "type": "feishu",
                    "target": "fixture://feishu/ops-room",
                },
            )
            rule = dashboard_store.save_automation_rule(
                openclaw_dir,
                {
                    "name": "关键任务完成通知",
                    "triggerType": "critical_task_done",
                    "severity": "critical",
                    "matchText": "S级",
                    "channelIds": [channel["id"]],
                },
            )
            alert = dashboard_store.upsert_automation_alert(
                openclaw_dir,
                {
                    "ruleId": rule["id"],
                    "eventKey": "TASK-001",
                    "title": "关键任务 TASK-001 已完成",
                    "detail": "请同步到值班群。",
                    "severity": "critical",
                    "sourceType": "task",
                    "sourceId": "TASK-001",
                },
            )
            delivery = dashboard_store.save_notification_delivery(
                openclaw_dir,
                alert["id"],
                channel["id"],
                "success",
                detail="fixture delivered",
            )

            self.assertEqual(dashboard_store.list_automation_rules(openclaw_dir)[0]["channelIds"], [channel["id"]])
            self.assertEqual(dashboard_store.list_notification_channels(openclaw_dir)[0]["name"], "Ops Feishu")
            self.assertEqual(dashboard_store.list_automation_alerts(openclaw_dir)[0]["eventKey"], "TASK-001")
            self.assertEqual(dashboard_store.list_notification_deliveries(openclaw_dir)[0]["channelId"], channel["id"])
            self.assertEqual(delivery["outcome"], "success")

    def test_orchestration_workflow_and_routing_policy_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            openclaw_dir = Path(tmpdir)

            workflow = dashboard_store.save_orchestration_workflow(
                openclaw_dir,
                {
                    "name": "Engineering to QA",
                    "description": "A starter orchestration flow",
                    "lanes": [{"id": "build", "title": "Engineering"}, {"id": "qa", "title": "Quality"}],
                    "nodes": [{"id": "node-build", "laneId": "build", "title": "Engineering", "agentId": "gongbu"}],
                },
            )
            policy = dashboard_store.save_routing_policy(
                openclaw_dir,
                {
                    "name": "Bugfix to Gongbu",
                    "strategyType": "keyword_department",
                    "keyword": "bugfix",
                    "targetAgentId": "gongbu",
                    "priorityLevel": "high",
                    "queueName": "release-fast-lane",
                },
            )

            self.assertEqual(dashboard_store.list_orchestration_workflows(openclaw_dir)[0]["name"], "Engineering to QA")
            self.assertEqual(dashboard_store.list_orchestration_workflows(openclaw_dir)[0]["nodes"][0]["agentId"], "gongbu")
            self.assertEqual(dashboard_store.list_routing_policies(openclaw_dir)[0]["targetAgentId"], "gongbu")
            self.assertEqual(workflow["status"], "active")
            self.assertEqual(policy["priorityLevel"], "high")

    def test_tenant_registry_and_api_key_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            openclaw_dir = Path(tmpdir)

            tenant = dashboard_store.save_tenant(
                openclaw_dir,
                {
                    "name": "Team North",
                    "slug": "team-north",
                    "primaryOpenclawDir": "/srv/openclaw/team-north",
                },
            )
            binding = dashboard_store.save_tenant_installation(
                openclaw_dir,
                {
                    "tenantId": tenant["id"],
                    "openclawDir": "/srv/openclaw/team-north",
                    "label": "Team North Prod",
                    "role": "primary",
                },
            )
            created = dashboard_store.create_tenant_api_key(
                openclaw_dir,
                tenant["id"],
                "ci-deploy",
                scopes=["tenant:read", "tasks:write"],
            )
            resolved = dashboard_store.resolve_tenant_api_key(openclaw_dir, created["rawKey"])

            self.assertEqual(dashboard_store.list_tenants(openclaw_dir)[0]["slug"], "team-north")
            self.assertEqual(dashboard_store.list_tenant_installations(openclaw_dir, tenant["id"])[0]["label"], binding["label"])
            self.assertEqual(resolved["tenantId"], tenant["id"])
            self.assertIn("tasks:write", resolved["scopes"])


if __name__ == "__main__":
    unittest.main()
