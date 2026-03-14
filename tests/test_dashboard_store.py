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


if __name__ == "__main__":
    unittest.main()
