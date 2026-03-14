#!/usr/bin/env python3
"""SQLite-backed storage for Mission Control product data."""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 3
MANAGEMENT_STAGE_ORDER = ("intake", "plan", "execute", "verify", "release")
MANAGEMENT_STAGE_LABELS = {
    "intake": "需求接入",
    "plan": "方案编排",
    "execute": "执行推进",
    "verify": "验证验收",
    "release": "发布收口",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def dashboard_dir(openclaw_dir):
    path = Path(openclaw_dir) / "dashboard"
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_path(openclaw_dir):
    return dashboard_dir(openclaw_dir) / "dashboard.db"


def legacy_users_path(openclaw_dir):
    return dashboard_dir(openclaw_dir) / "product_users.json"


def legacy_audit_path(openclaw_dir):
    return dashboard_dir(openclaw_dir) / "audit-log.jsonl"


def _load_json(path, default):
    file_path = Path(path)
    if not file_path.exists():
        return default
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _connect(openclaw_dir):
    db_path = store_path(openclaw_dir)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(conn)
    _ensure_legacy_migration(openclaw_dir, conn)
    return conn


def _ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS product_users (
            username TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            at TEXT NOT NULL,
            action TEXT NOT NULL,
            outcome TEXT NOT NULL,
            detail TEXT NOT NULL,
            actor_json TEXT NOT NULL,
            meta_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS product_installations (
            openclaw_dir TEXT PRIMARY KEY,
            installation_id TEXT NOT NULL,
            label TEXT NOT NULL,
            project_dir TEXT NOT NULL,
            theme TEXT NOT NULL,
            router_agent_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS management_runs (
            run_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            goal TEXT NOT NULL,
            owner TEXT NOT NULL,
            status TEXT NOT NULL,
            stage_key TEXT NOT NULL,
            linked_task_id TEXT NOT NULL,
            linked_agent_id TEXT NOT NULL,
            linked_session_key TEXT NOT NULL,
            release_channel TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            stages_json TEXT NOT NULL,
            meta_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_events_at ON audit_events(at DESC);
        CREATE INDEX IF NOT EXISTS idx_product_users_created_at ON product_users(created_at);
        CREATE INDEX IF NOT EXISTS idx_product_installations_updated_at ON product_installations(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_management_runs_updated_at ON management_runs(updated_at DESC);
        """
    )
    _set_metadata(conn, "schema_version", str(SCHEMA_VERSION))
    conn.commit()


def _metadata(conn, key, default=""):
    row = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def _set_metadata(conn, key, value):
    conn.execute(
        "INSERT INTO metadata(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def _normalize_username(value):
    return str(value or "").strip().lower()


def _normalize_user_record(user):
    if not isinstance(user, dict):
        return None
    username = _normalize_username(user.get("username"))
    if not username:
        return None
    return {
        "user_id": user.get("id") or user.get("user_id") or secrets.token_hex(8),
        "username": username,
        "display_name": (user.get("displayName") or user.get("display_name") or username).strip(),
        "role": user.get("role") if user.get("role") in {"owner", "operator", "viewer"} else "viewer",
        "password_hash": user.get("passwordHash") or user.get("password_hash") or "",
        "status": user.get("status") if user.get("status") in {"active", "suspended"} else "active",
        "created_at": user.get("createdAt") or user.get("created_at") or now_iso(),
        "last_login_at": user.get("lastLoginAt") or user.get("last_login_at") or "",
    }


def _normalize_audit_event(event):
    if not isinstance(event, dict):
        return None
    actor = event.get("actor") if isinstance(event.get("actor"), dict) else {}
    meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
    return {
        "id": event.get("id") or secrets.token_hex(8),
        "at": event.get("at") or now_iso(),
        "action": str(event.get("action") or "event"),
        "outcome": str(event.get("outcome") or "success"),
        "detail": str(event.get("detail") or ""),
        "actor_json": json.dumps(actor, ensure_ascii=False, separators=(",", ":")),
        "meta_json": json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
    }


def _normalize_installation_record(record):
    if not isinstance(record, dict):
        return None
    openclaw_dir = str(record.get("openclawDir") or record.get("openclaw_dir") or "").strip()
    if not openclaw_dir:
        return None
    created_at = record.get("createdAt") or record.get("created_at") or now_iso()
    updated_at = record.get("updatedAt") or record.get("updated_at") or created_at
    return {
        "openclaw_dir": openclaw_dir,
        "installation_id": record.get("id") or record.get("installation_id") or secrets.token_hex(8),
        "label": str(record.get("label") or record.get("displayName") or Path(openclaw_dir).name or openclaw_dir).strip(),
        "project_dir": str(record.get("projectDir") or record.get("project_dir") or "").strip(),
        "theme": str(record.get("theme") or "").strip(),
        "router_agent_id": str(record.get("routerAgentId") or record.get("router_agent_id") or "").strip(),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _default_management_stages():
    stages = []
    for key in MANAGEMENT_STAGE_ORDER:
        stages.append(
            {
                "key": key,
                "title": MANAGEMENT_STAGE_LABELS[key],
                "status": "pending",
                "note": "",
                "updatedAt": "",
            }
        )
    stages[0]["status"] = "active"
    stages[0]["updatedAt"] = now_iso()
    return stages


def _normalize_management_stage(stage, fallback_key):
    raw_key = str(stage.get("key") or fallback_key or "").strip().lower()
    key = raw_key if raw_key in MANAGEMENT_STAGE_LABELS else fallback_key
    status = str(stage.get("status") or "pending").strip().lower()
    if status not in {"pending", "active", "done", "blocked"}:
        status = "pending"
    return {
        "key": key,
        "title": str(stage.get("title") or MANAGEMENT_STAGE_LABELS.get(key, key)).strip(),
        "status": status,
        "note": str(stage.get("note") or "").strip(),
        "updatedAt": str(stage.get("updatedAt") or "").strip(),
    }


def _normalize_management_record(record):
    if not isinstance(record, dict):
        return None
    title = str(record.get("title") or "").strip()
    if not title:
        return None
    created_at = str(record.get("createdAt") or record.get("created_at") or now_iso()).strip()
    updated_at = str(record.get("updatedAt") or record.get("updated_at") or created_at).strip()
    run_id = str(record.get("id") or record.get("run_id") or secrets.token_hex(6)).strip()
    current_stage = str(record.get("stageKey") or record.get("stage_key") or "intake").strip().lower()
    if current_stage not in MANAGEMENT_STAGE_LABELS:
        current_stage = "intake"
    status = str(record.get("status") or "active").strip().lower()
    if status not in {"active", "blocked", "complete"}:
        status = "active"
    risk_level = str(record.get("riskLevel") or record.get("risk_level") or "medium").strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "medium"
    stages_input = record.get("stages") if isinstance(record.get("stages"), list) else []
    stages = []
    if stages_input:
        for key in MANAGEMENT_STAGE_ORDER:
            existing = next(
                (
                    stage
                    for stage in stages_input
                    if isinstance(stage, dict) and str(stage.get("key") or "").strip().lower() == key
                ),
                {"key": key},
            )
            stages.append(_normalize_management_stage(existing, key))
    else:
        stages = _default_management_stages()
    active_found = False
    for stage in stages:
        if stage["status"] == "active":
            if active_found:
                stage["status"] = "pending"
            else:
                active_found = True
                current_stage = stage["key"]
    if not active_found and status != "complete":
        for stage in stages:
            if stage["key"] == current_stage:
                stage["status"] = "active" if status != "blocked" else "blocked"
                break
    meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
    return {
        "run_id": run_id,
        "title": title,
        "goal": str(record.get("goal") or "").strip(),
        "owner": str(record.get("owner") or "Mission Control").strip(),
        "status": status,
        "stage_key": current_stage,
        "linked_task_id": str(record.get("linkedTaskId") or record.get("linked_task_id") or "").strip(),
        "linked_agent_id": str(record.get("linkedAgentId") or record.get("linked_agent_id") or "").strip(),
        "linked_session_key": str(record.get("linkedSessionKey") or record.get("linked_session_key") or "").strip(),
        "release_channel": str(record.get("releaseChannel") or record.get("release_channel") or "manual").strip(),
        "risk_level": risk_level,
        "created_at": created_at,
        "updated_at": updated_at,
        "started_at": str(record.get("startedAt") or record.get("started_at") or created_at).strip(),
        "completed_at": str(record.get("completedAt") or record.get("completed_at") or "").strip(),
        "stages_json": json.dumps(stages, ensure_ascii=False, separators=(",", ":")),
        "meta_json": json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
    }


def _management_row_to_dict(row):
    try:
        stages = json.loads(row["stages_json"] or "[]")
    except Exception:
        stages = []
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except Exception:
        meta = {}
    return {
        "id": row["run_id"],
        "title": row["title"],
        "goal": row["goal"],
        "owner": row["owner"],
        "status": row["status"],
        "stageKey": row["stage_key"],
        "linkedTaskId": row["linked_task_id"],
        "linkedAgentId": row["linked_agent_id"],
        "linkedSessionKey": row["linked_session_key"],
        "releaseChannel": row["release_channel"],
        "riskLevel": row["risk_level"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "startedAt": row["started_at"],
        "completedAt": row["completed_at"],
        "stages": stages,
        "meta": meta,
    }


def _ensure_legacy_migration(openclaw_dir, conn):
    if _metadata(conn, "legacy_users_migrated") != "1":
        legacy_users = _load_json(legacy_users_path(openclaw_dir), {"users": []})
        for user in legacy_users.get("users", []) if isinstance(legacy_users, dict) else []:
            normalized = _normalize_user_record(user)
            if not normalized:
                continue
            conn.execute(
                """
                INSERT INTO product_users(
                    username, user_id, display_name, role, password_hash, status, created_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    user_id = excluded.user_id,
                    display_name = excluded.display_name,
                    role = excluded.role,
                    password_hash = excluded.password_hash,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    last_login_at = excluded.last_login_at
                """,
                (
                    normalized["username"],
                    normalized["user_id"],
                    normalized["display_name"],
                    normalized["role"],
                    normalized["password_hash"],
                    normalized["status"],
                    normalized["created_at"],
                    normalized["last_login_at"],
                ),
            )
        _set_metadata(conn, "legacy_users_migrated", "1")

    if _metadata(conn, "legacy_audit_migrated") != "1":
        legacy_path = legacy_audit_path(openclaw_dir)
        if legacy_path.exists():
            for line in legacy_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                normalized = _normalize_audit_event(event)
                if not normalized:
                    continue
                conn.execute(
                    """
                    INSERT OR IGNORE INTO audit_events(
                        id, at, action, outcome, detail, actor_json, meta_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized["id"],
                        normalized["at"],
                        normalized["action"],
                        normalized["outcome"],
                        normalized["detail"],
                        normalized["actor_json"],
                        normalized["meta_json"],
                    ),
                )
        _set_metadata(conn, "legacy_audit_migrated", "1")

    conn.commit()


def load_product_users(openclaw_dir):
    with _connect(openclaw_dir) as conn:
        rows = conn.execute(
            """
            SELECT user_id, username, display_name, role, password_hash, status, created_at, last_login_at
            FROM product_users
            ORDER BY created_at ASC, username ASC
            """
        ).fetchall()
    return [
        {
            "id": row["user_id"],
            "username": row["username"],
            "displayName": row["display_name"],
            "role": row["role"],
            "passwordHash": row["password_hash"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "lastLoginAt": row["last_login_at"],
        }
        for row in rows
    ]


def load_product_installations(openclaw_dir):
    with _connect(openclaw_dir) as conn:
        rows = conn.execute(
            """
            SELECT openclaw_dir, installation_id, label, project_dir, theme, router_agent_id, created_at, updated_at
            FROM product_installations
            ORDER BY updated_at DESC, label ASC
            """
        ).fetchall()
    return [
        {
            "id": row["installation_id"],
            "openclawDir": row["openclaw_dir"],
            "label": row["label"],
            "projectDir": row["project_dir"],
            "theme": row["theme"],
            "routerAgentId": row["router_agent_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def upsert_product_installation(openclaw_dir, installation):
    normalized = _normalize_installation_record(installation)
    if not normalized:
        raise RuntimeError("installation record is missing openclawDir")
    with _connect(openclaw_dir) as conn:
        conn.execute(
            """
            INSERT INTO product_installations(
                openclaw_dir, installation_id, label, project_dir, theme, router_agent_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(openclaw_dir) DO UPDATE SET
                label = excluded.label,
                project_dir = excluded.project_dir,
                theme = excluded.theme,
                router_agent_id = excluded.router_agent_id,
                updated_at = excluded.updated_at
            """,
            (
                normalized["openclaw_dir"],
                normalized["installation_id"],
                normalized["label"],
                normalized["project_dir"],
                normalized["theme"],
                normalized["router_agent_id"],
                normalized["created_at"],
                normalized["updated_at"],
            ),
        )
        conn.commit()
    return {
        "id": normalized["installation_id"],
        "openclawDir": normalized["openclaw_dir"],
        "label": normalized["label"],
        "projectDir": normalized["project_dir"],
        "theme": normalized["theme"],
        "routerAgentId": normalized["router_agent_id"],
        "createdAt": normalized["created_at"],
        "updatedAt": normalized["updated_at"],
    }


def delete_product_installation(openclaw_dir, target_openclaw_dir):
    normalized_dir = str(target_openclaw_dir or "").strip()
    if not normalized_dir:
        return False
    with _connect(openclaw_dir) as conn:
        cursor = conn.execute("DELETE FROM product_installations WHERE openclaw_dir = ?", (normalized_dir,))
        conn.commit()
    return cursor.rowcount > 0


def save_product_users(openclaw_dir, users):
    normalized = [record for record in (_normalize_user_record(user) for user in users) if record]
    with _connect(openclaw_dir) as conn:
        conn.execute("DELETE FROM product_users")
        conn.executemany(
            """
            INSERT INTO product_users(
                username, user_id, display_name, role, password_hash, status, created_at, last_login_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record["username"],
                    record["user_id"],
                    record["display_name"],
                    record["role"],
                    record["password_hash"],
                    record["status"],
                    record["created_at"],
                    record["last_login_at"],
                )
                for record in normalized
            ],
        )
        conn.commit()


def append_audit_event(openclaw_dir, action, actor, outcome="success", detail="", meta=None):
    event = _normalize_audit_event(
        {
            "id": secrets.token_hex(8),
            "at": now_iso(),
            "action": action,
            "outcome": outcome,
            "detail": detail,
            "actor": actor or {"displayName": "system", "role": "owner", "kind": "system"},
            "meta": meta or {},
        }
    )
    with _connect(openclaw_dir) as conn:
        conn.execute(
            """
            INSERT INTO audit_events(
                id, at, action, outcome, detail, actor_json, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["id"],
                event["at"],
                event["action"],
                event["outcome"],
                event["detail"],
                event["actor_json"],
                event["meta_json"],
            ),
        )
        conn.commit()
    return {
        "id": event["id"],
        "at": event["at"],
        "action": event["action"],
        "outcome": event["outcome"],
        "detail": event["detail"],
        "actor": json.loads(event["actor_json"]),
        "meta": json.loads(event["meta_json"]),
    }


def load_audit_events(openclaw_dir, limit=80):
    with _connect(openclaw_dir) as conn:
        rows = conn.execute(
            """
            SELECT id, at, action, outcome, detail, actor_json, meta_json
            FROM audit_events
            ORDER BY at DESC, id DESC
            LIMIT ?
            """,
            (max(int(limit or 0), 0),),
        ).fetchall()
    events = []
    for row in rows:
        try:
            actor = json.loads(row["actor_json"] or "{}")
        except Exception:
            actor = {}
        try:
            meta = json.loads(row["meta_json"] or "{}")
        except Exception:
            meta = {}
        events.append(
            {
                "id": row["id"],
                "at": row["at"],
                "action": row["action"],
                "outcome": row["outcome"],
                "detail": row["detail"],
                "actor": actor,
                "meta": meta,
            }
        )
    return events


def list_management_runs(openclaw_dir, limit=32):
    with _connect(openclaw_dir) as conn:
        rows = conn.execute(
            """
            SELECT
                run_id, title, goal, owner, status, stage_key, linked_task_id, linked_agent_id,
                linked_session_key, release_channel, risk_level, created_at, updated_at,
                started_at, completed_at, stages_json, meta_json
            FROM management_runs
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
            """,
            (max(int(limit or 0), 1),),
        ).fetchall()
    return [_management_row_to_dict(row) for row in rows]


def create_management_run(openclaw_dir, payload):
    normalized = _normalize_management_record(payload)
    if not normalized:
        raise RuntimeError("management run title is required")
    with _connect(openclaw_dir) as conn:
        conn.execute(
            """
            INSERT INTO management_runs(
                run_id, title, goal, owner, status, stage_key, linked_task_id, linked_agent_id,
                linked_session_key, release_channel, risk_level, created_at, updated_at,
                started_at, completed_at, stages_json, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["run_id"],
                normalized["title"],
                normalized["goal"],
                normalized["owner"],
                normalized["status"],
                normalized["stage_key"],
                normalized["linked_task_id"],
                normalized["linked_agent_id"],
                normalized["linked_session_key"],
                normalized["release_channel"],
                normalized["risk_level"],
                normalized["created_at"],
                normalized["updated_at"],
                normalized["started_at"],
                normalized["completed_at"],
                normalized["stages_json"],
                normalized["meta_json"],
            ),
        )
        conn.commit()
    return next((item for item in list_management_runs(openclaw_dir, limit=64) if item["id"] == normalized["run_id"]), None)


def update_management_run(openclaw_dir, run_id, action, note="", risk_level="", linked_task_id=""):
    run_id = str(run_id or "").strip()
    if not run_id:
        raise RuntimeError("management run id is required")
    with _connect(openclaw_dir) as conn:
        row = conn.execute(
            """
            SELECT
                run_id, title, goal, owner, status, stage_key, linked_task_id, linked_agent_id,
                linked_session_key, release_channel, risk_level, created_at, updated_at,
                started_at, completed_at, stages_json, meta_json
            FROM management_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if not row:
            raise RuntimeError(f"management run not found: {run_id}")
        record = _management_row_to_dict(row)
        stages = record["stages"] or _default_management_stages()
        stage_index = next((idx for idx, stage in enumerate(stages) if stage["key"] == record["stageKey"]), 0)
        current_stage = stages[stage_index]
        if note:
            current_stage["note"] = str(note).strip()
            current_stage["updatedAt"] = now_iso()
        if linked_task_id:
            record["linkedTaskId"] = str(linked_task_id).strip()
        if risk_level:
            level = str(risk_level).strip().lower()
            if level in {"low", "medium", "high"}:
                record["riskLevel"] = level
        action = str(action or "").strip().lower()
        now = now_iso()
        if action == "advance":
            current_stage["status"] = "done"
            current_stage["updatedAt"] = now
            if stage_index + 1 < len(stages):
                next_stage = stages[stage_index + 1]
                if next_stage["status"] != "done":
                    next_stage["status"] = "active"
                    next_stage["updatedAt"] = now
                record["stageKey"] = next_stage["key"]
                record["status"] = "active"
            else:
                record["stageKey"] = stages[-1]["key"]
                record["status"] = "complete"
                record["completedAt"] = now
        elif action == "block":
            current_stage["status"] = "blocked"
            current_stage["updatedAt"] = now
            record["status"] = "blocked"
        elif action == "resume":
            current_stage["status"] = "active"
            current_stage["updatedAt"] = now
            record["status"] = "active"
        elif action == "complete":
            for stage in stages:
                stage["status"] = "done"
                stage["updatedAt"] = now
            record["stageKey"] = stages[-1]["key"]
            record["status"] = "complete"
            record["completedAt"] = now
        elif action == "note":
            pass
        else:
            raise RuntimeError(f"unsupported management action: {action}")
        record["updatedAt"] = now
        record["stages"] = stages
        normalized = _normalize_management_record(record)
        conn.execute(
            """
            UPDATE management_runs
            SET
                title = ?, goal = ?, owner = ?, status = ?, stage_key = ?, linked_task_id = ?, linked_agent_id = ?,
                linked_session_key = ?, release_channel = ?, risk_level = ?, updated_at = ?, started_at = ?,
                completed_at = ?, stages_json = ?, meta_json = ?
            WHERE run_id = ?
            """,
            (
                normalized["title"],
                normalized["goal"],
                normalized["owner"],
                normalized["status"],
                normalized["stage_key"],
                normalized["linked_task_id"],
                normalized["linked_agent_id"],
                normalized["linked_session_key"],
                normalized["release_channel"],
                normalized["risk_level"],
                normalized["updated_at"],
                normalized["started_at"],
                normalized["completed_at"],
                normalized["stages_json"],
                normalized["meta_json"],
                run_id,
            ),
        )
        conn.commit()
    return next((item for item in list_management_runs(openclaw_dir, limit=64) if item["id"] == run_id), None)
