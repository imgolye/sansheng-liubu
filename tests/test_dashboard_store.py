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


if __name__ == "__main__":
    unittest.main()
