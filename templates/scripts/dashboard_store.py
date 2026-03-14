#!/usr/bin/env python3
"""SQLite-backed storage for Mission Control product data."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 6
MANAGEMENT_STAGE_ORDER = ("intake", "plan", "execute", "verify", "release")
MANAGEMENT_STAGE_LABELS = {
    "intake": "需求接入",
    "plan": "方案编排",
    "execute": "执行推进",
    "verify": "验证验收",
    "release": "发布收口",
}
AUTOMATION_RULE_TYPES = {
    "blocked_task_timeout",
    "critical_task_done",
    "agent_offline",
}
NOTIFICATION_CHANNEL_TYPES = {"telegram", "feishu", "webhook"}
ROUTING_STRATEGY_TYPES = {"keyword_department", "load_balance", "priority_queue"}


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hash_api_key(raw_key):
    return hashlib.sha256(str(raw_key or "").encode("utf-8")).hexdigest()


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

        CREATE TABLE IF NOT EXISTS automation_rules (
            rule_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            threshold_minutes INTEGER NOT NULL,
            cooldown_minutes INTEGER NOT NULL,
            severity TEXT NOT NULL,
            match_text TEXT NOT NULL,
            channel_ids_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            meta_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notification_channels (
            channel_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            channel_type TEXT NOT NULL,
            status TEXT NOT NULL,
            target TEXT NOT NULL,
            secret TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            meta_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS automation_alerts (
            alert_id TEXT PRIMARY KEY,
            rule_id TEXT NOT NULL,
            event_key TEXT NOT NULL,
            title TEXT NOT NULL,
            detail TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            triggered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT NOT NULL,
            meta_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notification_deliveries (
            delivery_id TEXT PRIMARY KEY,
            alert_id TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            outcome TEXT NOT NULL,
            detail TEXT NOT NULL,
            delivered_at TEXT NOT NULL,
            meta_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orchestration_workflows (
            workflow_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL,
            lanes_json TEXT NOT NULL,
            nodes_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            meta_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS routing_policies (
            policy_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            strategy_type TEXT NOT NULL,
            keyword TEXT NOT NULL,
            target_agent_id TEXT NOT NULL,
            priority_level TEXT NOT NULL,
            queue_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            meta_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tenants (
            tenant_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            primary_openclaw_dir TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            meta_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tenant_installations (
            tenant_id TEXT NOT NULL,
            openclaw_dir TEXT NOT NULL,
            label TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            meta_json TEXT NOT NULL,
            PRIMARY KEY (tenant_id, openclaw_dir)
        );

        CREATE TABLE IF NOT EXISTS tenant_api_keys (
            key_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            prefix TEXT NOT NULL,
            status TEXT NOT NULL,
            scopes_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL,
            meta_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_events_at ON audit_events(at DESC);
        CREATE INDEX IF NOT EXISTS idx_product_users_created_at ON product_users(created_at);
        CREATE INDEX IF NOT EXISTS idx_product_installations_updated_at ON product_installations(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_management_runs_updated_at ON management_runs(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_automation_rules_updated_at ON automation_rules(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_notification_channels_updated_at ON notification_channels(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_automation_alerts_updated_at ON automation_alerts(updated_at DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_automation_alerts_unique_event ON automation_alerts(rule_id, event_key);
        CREATE INDEX IF NOT EXISTS idx_notification_deliveries_alert_id ON notification_deliveries(alert_id, delivered_at DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_delivery_unique_channel ON notification_deliveries(alert_id, channel_id);
        CREATE INDEX IF NOT EXISTS idx_orchestration_workflows_updated_at ON orchestration_workflows(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_routing_policies_updated_at ON routing_policies(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_tenants_updated_at ON tenants(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_tenant_installations_tenant ON tenant_installations(tenant_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_tenant_api_keys_tenant ON tenant_api_keys(tenant_id, created_at DESC);
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


def _normalize_automation_rule(record):
    if not isinstance(record, dict):
        return None
    name = str(record.get("name") or "").strip()
    if not name:
        return None
    trigger_type = str(record.get("triggerType") or record.get("trigger_type") or "").strip().lower()
    if trigger_type not in AUTOMATION_RULE_TYPES:
        raise RuntimeError(f"unsupported automation trigger type: {trigger_type or 'unknown'}")
    severity = str(record.get("severity") or "warning").strip().lower()
    if severity not in {"info", "warning", "critical"}:
        severity = "warning"
    status = str(record.get("status") or "active").strip().lower()
    if status not in {"active", "disabled"}:
        status = "active"
    threshold_minutes = max(int(record.get("thresholdMinutes") or record.get("threshold_minutes") or 0), 0)
    cooldown_minutes = max(int(record.get("cooldownMinutes") or record.get("cooldown_minutes") or 60), 0)
    channel_ids = record.get("channelIds") or record.get("channel_ids") or []
    if not isinstance(channel_ids, list):
        channel_ids = []
    meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
    created_at = str(record.get("createdAt") or record.get("created_at") or now_iso()).strip()
    updated_at = str(record.get("updatedAt") or record.get("updated_at") or created_at).strip()
    return {
        "rule_id": str(record.get("id") or record.get("rule_id") or secrets.token_hex(6)).strip(),
        "name": name,
        "description": str(record.get("description") or "").strip(),
        "status": status,
        "trigger_type": trigger_type,
        "threshold_minutes": threshold_minutes,
        "cooldown_minutes": cooldown_minutes,
        "severity": severity,
        "match_text": str(record.get("matchText") or record.get("match_text") or "").strip(),
        "channel_ids_json": json.dumps([str(item).strip() for item in channel_ids if str(item).strip()], ensure_ascii=False, separators=(",", ":")),
        "created_at": created_at,
        "updated_at": updated_at,
        "meta_json": json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
    }


def _automation_rule_row_to_dict(row):
    try:
        channel_ids = json.loads(row["channel_ids_json"] or "[]")
    except Exception:
        channel_ids = []
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except Exception:
        meta = {}
    return {
        "id": row["rule_id"],
        "name": row["name"],
        "description": row["description"],
        "status": row["status"],
        "triggerType": row["trigger_type"],
        "thresholdMinutes": row["threshold_minutes"],
        "cooldownMinutes": row["cooldown_minutes"],
        "severity": row["severity"],
        "matchText": row["match_text"],
        "channelIds": channel_ids if isinstance(channel_ids, list) else [],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "meta": meta,
    }


def _normalize_notification_channel(record):
    if not isinstance(record, dict):
        return None
    name = str(record.get("name") or "").strip()
    channel_type = str(record.get("type") or record.get("channelType") or record.get("channel_type") or "").strip().lower()
    if not name or channel_type not in NOTIFICATION_CHANNEL_TYPES:
        return None
    status = str(record.get("status") or "active").strip().lower()
    if status not in {"active", "disabled"}:
        status = "active"
    created_at = str(record.get("createdAt") or record.get("created_at") or now_iso()).strip()
    updated_at = str(record.get("updatedAt") or record.get("updated_at") or created_at).strip()
    meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
    return {
        "channel_id": str(record.get("id") or record.get("channel_id") or secrets.token_hex(6)).strip(),
        "name": name,
        "channel_type": channel_type,
        "status": status,
        "target": str(record.get("target") or "").strip(),
        "secret": str(record.get("secret") or "").strip(),
        "created_at": created_at,
        "updated_at": updated_at,
        "meta_json": json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
    }


def _notification_channel_row_to_dict(row):
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except Exception:
        meta = {}
    return {
        "id": row["channel_id"],
        "name": row["name"],
        "type": row["channel_type"],
        "status": row["status"],
        "target": row["target"],
        "secret": row["secret"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "meta": meta,
    }


def _normalize_automation_alert(record):
    if not isinstance(record, dict):
        return None
    rule_id = str(record.get("ruleId") or record.get("rule_id") or "").strip()
    event_key = str(record.get("eventKey") or record.get("event_key") or "").strip()
    title = str(record.get("title") or "").strip()
    if not rule_id or not event_key or not title:
        return None
    severity = str(record.get("severity") or "warning").strip().lower()
    if severity not in {"info", "warning", "critical"}:
        severity = "warning"
    status = str(record.get("status") or "open").strip().lower()
    if status not in {"open", "notified", "resolved", "error"}:
        status = "open"
    triggered_at = str(record.get("triggeredAt") or record.get("triggered_at") or now_iso()).strip()
    updated_at = str(record.get("updatedAt") or record.get("updated_at") or triggered_at).strip()
    meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
    return {
        "alert_id": str(record.get("id") or record.get("alert_id") or secrets.token_hex(8)).strip(),
        "rule_id": rule_id,
        "event_key": event_key,
        "title": title,
        "detail": str(record.get("detail") or "").strip(),
        "severity": severity,
        "status": status,
        "source_type": str(record.get("sourceType") or record.get("source_type") or "").strip(),
        "source_id": str(record.get("sourceId") or record.get("source_id") or "").strip(),
        "triggered_at": triggered_at,
        "updated_at": updated_at,
        "resolved_at": str(record.get("resolvedAt") or record.get("resolved_at") or "").strip(),
        "meta_json": json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
    }


def _automation_alert_row_to_dict(row):
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except Exception:
        meta = {}
    return {
        "id": row["alert_id"],
        "ruleId": row["rule_id"],
        "eventKey": row["event_key"],
        "title": row["title"],
        "detail": row["detail"],
        "severity": row["severity"],
        "status": row["status"],
        "sourceType": row["source_type"],
        "sourceId": row["source_id"],
        "triggeredAt": row["triggered_at"],
        "updatedAt": row["updated_at"],
        "resolvedAt": row["resolved_at"],
        "meta": meta,
    }


def _normalize_orchestration_workflow(record):
    if not isinstance(record, dict):
        return None
    name = str(record.get("name") or "").strip()
    if not name:
        return None
    status = str(record.get("status") or "active").strip().lower()
    if status not in {"active", "draft", "disabled"}:
        status = "active"
    lanes = record.get("lanes") if isinstance(record.get("lanes"), list) else []
    nodes = record.get("nodes") if isinstance(record.get("nodes"), list) else []
    meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
    created_at = str(record.get("createdAt") or record.get("created_at") or now_iso()).strip()
    updated_at = str(record.get("updatedAt") or record.get("updated_at") or created_at).strip()
    return {
        "workflow_id": str(record.get("id") or record.get("workflow_id") or secrets.token_hex(6)).strip(),
        "name": name,
        "description": str(record.get("description") or "").strip(),
        "status": status,
        "lanes_json": json.dumps(lanes, ensure_ascii=False, separators=(",", ":")),
        "nodes_json": json.dumps(nodes, ensure_ascii=False, separators=(",", ":")),
        "created_at": created_at,
        "updated_at": updated_at,
        "meta_json": json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
    }


def _orchestration_workflow_row_to_dict(row):
    try:
        lanes = json.loads(row["lanes_json"] or "[]")
    except Exception:
        lanes = []
    try:
        nodes = json.loads(row["nodes_json"] or "[]")
    except Exception:
        nodes = []
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except Exception:
        meta = {}
    return {
        "id": row["workflow_id"],
        "name": row["name"],
        "description": row["description"],
        "status": row["status"],
        "lanes": lanes if isinstance(lanes, list) else [],
        "nodes": nodes if isinstance(nodes, list) else [],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "meta": meta,
    }


def _normalize_routing_policy(record):
    if not isinstance(record, dict):
        return None
    name = str(record.get("name") or "").strip()
    if not name:
        return None
    status = str(record.get("status") or "active").strip().lower()
    if status not in {"active", "disabled"}:
        status = "active"
    strategy_type = str(record.get("strategyType") or record.get("strategy_type") or "").strip().lower()
    if strategy_type not in ROUTING_STRATEGY_TYPES:
        raise RuntimeError(f"unsupported routing strategy type: {strategy_type or 'unknown'}")
    priority_level = str(record.get("priorityLevel") or record.get("priority_level") or "normal").strip().lower()
    if priority_level not in {"low", "normal", "high", "critical"}:
        priority_level = "normal"
    meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
    created_at = str(record.get("createdAt") or record.get("created_at") or now_iso()).strip()
    updated_at = str(record.get("updatedAt") or record.get("updated_at") or created_at).strip()
    return {
        "policy_id": str(record.get("id") or record.get("policy_id") or secrets.token_hex(6)).strip(),
        "name": name,
        "status": status,
        "strategy_type": strategy_type,
        "keyword": str(record.get("keyword") or "").strip(),
        "target_agent_id": str(record.get("targetAgentId") or record.get("target_agent_id") or "").strip(),
        "priority_level": priority_level,
        "queue_name": str(record.get("queueName") or record.get("queue_name") or "").strip(),
        "created_at": created_at,
        "updated_at": updated_at,
        "meta_json": json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
    }


def _routing_policy_row_to_dict(row):
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except Exception:
        meta = {}
    return {
        "id": row["policy_id"],
        "name": row["name"],
        "status": row["status"],
        "strategyType": row["strategy_type"],
        "keyword": row["keyword"],
        "targetAgentId": row["target_agent_id"],
        "priorityLevel": row["priority_level"],
        "queueName": row["queue_name"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "meta": meta,
    }


def _slugify(value):
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "").strip())
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-")


def _normalize_tenant(record):
    if not isinstance(record, dict):
        return None
    name = str(record.get("name") or "").strip()
    if not name:
        return None
    slug = _slugify(record.get("slug") or name)
    status = str(record.get("status") or "active").strip().lower()
    if status not in {"active", "suspended"}:
        status = "active"
    primary_dir = str(record.get("primaryOpenclawDir") or record.get("primary_openclaw_dir") or "").strip()
    meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
    created_at = str(record.get("createdAt") or record.get("created_at") or now_iso()).strip()
    updated_at = str(record.get("updatedAt") or record.get("updated_at") or created_at).strip()
    return {
        "tenant_id": str(record.get("id") or record.get("tenant_id") or secrets.token_hex(6)).strip(),
        "name": name,
        "slug": slug,
        "status": status,
        "primary_openclaw_dir": primary_dir,
        "created_at": created_at,
        "updated_at": updated_at,
        "meta_json": json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
    }


def _tenant_row_to_dict(row):
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except Exception:
        meta = {}
    return {
        "id": row["tenant_id"],
        "name": row["name"],
        "slug": row["slug"],
        "status": row["status"],
        "primaryOpenclawDir": row["primary_openclaw_dir"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "meta": meta,
    }


def _normalize_tenant_installation(record):
    if not isinstance(record, dict):
        return None
    tenant_id = str(record.get("tenantId") or record.get("tenant_id") or "").strip()
    openclaw_dir = str(record.get("openclawDir") or record.get("openclaw_dir") or "").strip()
    if not tenant_id or not openclaw_dir:
        return None
    created_at = str(record.get("createdAt") or record.get("created_at") or now_iso()).strip()
    updated_at = str(record.get("updatedAt") or record.get("updated_at") or created_at).strip()
    meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
    return {
        "tenant_id": tenant_id,
        "openclaw_dir": openclaw_dir,
        "label": str(record.get("label") or Path(openclaw_dir).name or openclaw_dir).strip(),
        "role": str(record.get("role") or "primary").strip().lower(),
        "created_at": created_at,
        "updated_at": updated_at,
        "meta_json": json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
    }


def _tenant_installation_row_to_dict(row):
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except Exception:
        meta = {}
    return {
        "tenantId": row["tenant_id"],
        "openclawDir": row["openclaw_dir"],
        "label": row["label"],
        "role": row["role"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "meta": meta,
    }


def _normalize_tenant_api_key(record):
    if not isinstance(record, dict):
        return None
    tenant_id = str(record.get("tenantId") or record.get("tenant_id") or "").strip()
    name = str(record.get("name") or "").strip()
    raw_key = str(record.get("rawKey") or record.get("raw_key") or "").strip()
    if not tenant_id or not name or not raw_key:
        return None
    status = str(record.get("status") or "active").strip().lower()
    if status not in {"active", "disabled"}:
        status = "active"
    scopes = record.get("scopes") if isinstance(record.get("scopes"), list) else []
    meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
    created_at = str(record.get("createdAt") or record.get("created_at") or now_iso()).strip()
    return {
        "key_id": str(record.get("id") or record.get("key_id") or secrets.token_hex(8)).strip(),
        "tenant_id": tenant_id,
        "name": name,
        "key_hash": hash_api_key(raw_key),
        "prefix": raw_key[:10],
        "status": status,
        "scopes_json": json.dumps([str(item).strip() for item in scopes if str(item).strip()], ensure_ascii=False, separators=(",", ":")),
        "created_at": created_at,
        "last_used_at": str(record.get("lastUsedAt") or record.get("last_used_at") or "").strip(),
        "meta_json": json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
    }


def _tenant_api_key_row_to_dict(row):
    try:
        scopes = json.loads(row["scopes_json"] or "[]")
    except Exception:
        scopes = []
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except Exception:
        meta = {}
    return {
        "id": row["key_id"],
        "tenantId": row["tenant_id"],
        "name": row["name"],
        "prefix": row["prefix"],
        "status": row["status"],
        "scopes": scopes if isinstance(scopes, list) else [],
        "createdAt": row["created_at"],
        "lastUsedAt": row["last_used_at"],
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


def list_automation_rules(openclaw_dir):
    with _connect(openclaw_dir) as conn:
        rows = conn.execute(
            """
            SELECT
                rule_id, name, description, status, trigger_type, threshold_minutes, cooldown_minutes,
                severity, match_text, channel_ids_json, created_at, updated_at, meta_json
            FROM automation_rules
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    return [_automation_rule_row_to_dict(row) for row in rows]


def save_automation_rule(openclaw_dir, payload):
    normalized = _normalize_automation_rule(payload)
    if not normalized:
        raise RuntimeError("automation rule name is required")
    with _connect(openclaw_dir) as conn:
        conn.execute(
            """
            INSERT INTO automation_rules(
                rule_id, name, description, status, trigger_type, threshold_minutes, cooldown_minutes,
                severity, match_text, channel_ids_json, created_at, updated_at, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                status = excluded.status,
                trigger_type = excluded.trigger_type,
                threshold_minutes = excluded.threshold_minutes,
                cooldown_minutes = excluded.cooldown_minutes,
                severity = excluded.severity,
                match_text = excluded.match_text,
                channel_ids_json = excluded.channel_ids_json,
                updated_at = excluded.updated_at,
                meta_json = excluded.meta_json
            """,
            (
                normalized["rule_id"],
                normalized["name"],
                normalized["description"],
                normalized["status"],
                normalized["trigger_type"],
                normalized["threshold_minutes"],
                normalized["cooldown_minutes"],
                normalized["severity"],
                normalized["match_text"],
                normalized["channel_ids_json"],
                normalized["created_at"],
                normalized["updated_at"],
                normalized["meta_json"],
            ),
        )
        conn.commit()
    return next((item for item in list_automation_rules(openclaw_dir) if item["id"] == normalized["rule_id"]), None)


def list_notification_channels(openclaw_dir):
    with _connect(openclaw_dir) as conn:
        rows = conn.execute(
            """
            SELECT
                channel_id, name, channel_type, status, target, secret, created_at, updated_at, meta_json
            FROM notification_channels
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    return [_notification_channel_row_to_dict(row) for row in rows]


def save_notification_channel(openclaw_dir, payload):
    normalized = _normalize_notification_channel(payload)
    if not normalized:
        raise RuntimeError("notification channel name and type are required")
    with _connect(openclaw_dir) as conn:
        conn.execute(
            """
            INSERT INTO notification_channels(
                channel_id, name, channel_type, status, target, secret, created_at, updated_at, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                name = excluded.name,
                channel_type = excluded.channel_type,
                status = excluded.status,
                target = excluded.target,
                secret = excluded.secret,
                updated_at = excluded.updated_at,
                meta_json = excluded.meta_json
            """,
            (
                normalized["channel_id"],
                normalized["name"],
                normalized["channel_type"],
                normalized["status"],
                normalized["target"],
                normalized["secret"],
                normalized["created_at"],
                normalized["updated_at"],
                normalized["meta_json"],
            ),
        )
        conn.commit()
    return next((item for item in list_notification_channels(openclaw_dir) if item["id"] == normalized["channel_id"]), None)


def list_automation_alerts(openclaw_dir, limit=60):
    with _connect(openclaw_dir) as conn:
        rows = conn.execute(
            """
            SELECT
                alert_id, rule_id, event_key, title, detail, severity, status, source_type, source_id,
                triggered_at, updated_at, resolved_at, meta_json
            FROM automation_alerts
            ORDER BY updated_at DESC, triggered_at DESC
            LIMIT ?
            """,
            (max(int(limit or 0), 1),),
        ).fetchall()
    return [_automation_alert_row_to_dict(row) for row in rows]


def upsert_automation_alert(openclaw_dir, payload):
    normalized = _normalize_automation_alert(payload)
    if not normalized:
        raise RuntimeError("automation alert ruleId, eventKey, and title are required")
    existing = next(
        (
            item
            for item in list_automation_alerts(openclaw_dir, limit=256)
            if item["ruleId"] == normalized["rule_id"] and item["eventKey"] == normalized["event_key"]
        ),
        None,
    )
    if existing:
        normalized["alert_id"] = existing["id"]
    with _connect(openclaw_dir) as conn:
        conn.execute(
            """
            INSERT INTO automation_alerts(
                alert_id, rule_id, event_key, title, detail, severity, status, source_type, source_id,
                triggered_at, updated_at, resolved_at, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_id, event_key) DO UPDATE SET
                title = excluded.title,
                detail = excluded.detail,
                severity = excluded.severity,
                status = excluded.status,
                source_type = excluded.source_type,
                source_id = excluded.source_id,
                updated_at = excluded.updated_at,
                resolved_at = excluded.resolved_at,
                meta_json = excluded.meta_json
            """,
            (
                normalized["alert_id"],
                normalized["rule_id"],
                normalized["event_key"],
                normalized["title"],
                normalized["detail"],
                normalized["severity"],
                normalized["status"],
                normalized["source_type"],
                normalized["source_id"],
                normalized["triggered_at"],
                normalized["updated_at"],
                normalized["resolved_at"],
                normalized["meta_json"],
            ),
        )
        conn.commit()
    return next(
        (
            item
            for item in list_automation_alerts(openclaw_dir, limit=256)
            if item["ruleId"] == normalized["rule_id"] and item["eventKey"] == normalized["event_key"]
        ),
        None,
    )


def resolve_automation_alerts(openclaw_dir, rule_id, active_event_keys):
    rule_id = str(rule_id or "").strip()
    if not rule_id:
        return 0
    keys = {str(item).strip() for item in (active_event_keys or []) if str(item).strip()}
    resolved = 0
    with _connect(openclaw_dir) as conn:
        rows = conn.execute(
            """
            SELECT alert_id, event_key
            FROM automation_alerts
            WHERE rule_id = ? AND status IN ('open', 'notified', 'error')
            """,
            (rule_id,),
        ).fetchall()
        for row in rows:
            if row["event_key"] in keys:
                continue
            conn.execute(
                """
                UPDATE automation_alerts
                SET status = 'resolved', updated_at = ?, resolved_at = ?
                WHERE alert_id = ?
                """,
                (now_iso(), now_iso(), row["alert_id"]),
            )
            resolved += 1
        conn.commit()
    return resolved


def list_notification_deliveries(openclaw_dir, limit=120):
    with _connect(openclaw_dir) as conn:
        rows = conn.execute(
            """
            SELECT delivery_id, alert_id, channel_id, outcome, detail, delivered_at, meta_json
            FROM notification_deliveries
            ORDER BY delivered_at DESC
            LIMIT ?
            """,
            (max(int(limit or 0), 1),),
        ).fetchall()
    deliveries = []
    for row in rows:
        try:
            meta = json.loads(row["meta_json"] or "{}")
        except Exception:
            meta = {}
        deliveries.append(
            {
                "id": row["delivery_id"],
                "alertId": row["alert_id"],
                "channelId": row["channel_id"],
                "outcome": row["outcome"],
                "detail": row["detail"],
                "deliveredAt": row["delivered_at"],
                "meta": meta,
            }
        )
    return deliveries


def save_notification_delivery(openclaw_dir, alert_id, channel_id, outcome, detail="", meta=None):
    alert_id = str(alert_id or "").strip()
    channel_id = str(channel_id or "").strip()
    if not alert_id or not channel_id:
        raise RuntimeError("notification delivery requires alert_id and channel_id")
    meta_payload = json.dumps(meta or {}, ensure_ascii=False, separators=(",", ":"))
    delivered_at = now_iso()
    with _connect(openclaw_dir) as conn:
        existing = conn.execute(
            """
            SELECT delivery_id FROM notification_deliveries WHERE alert_id = ? AND channel_id = ?
            """,
            (alert_id, channel_id),
        ).fetchone()
        delivery_id = existing["delivery_id"] if existing else secrets.token_hex(8)
        conn.execute(
            """
            INSERT INTO notification_deliveries(
                delivery_id, alert_id, channel_id, outcome, detail, delivered_at, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(alert_id, channel_id) DO UPDATE SET
                outcome = excluded.outcome,
                detail = excluded.detail,
                delivered_at = excluded.delivered_at,
                meta_json = excluded.meta_json
            """,
            (delivery_id, alert_id, channel_id, str(outcome or "success"), str(detail or ""), delivered_at, meta_payload),
        )
        conn.commit()
    return next(
        (
            item
            for item in list_notification_deliveries(openclaw_dir, limit=256)
            if item["alertId"] == alert_id and item["channelId"] == channel_id
        ),
        None,
    )


def list_orchestration_workflows(openclaw_dir):
    with _connect(openclaw_dir) as conn:
        rows = conn.execute(
            """
            SELECT workflow_id, name, description, status, lanes_json, nodes_json, created_at, updated_at, meta_json
            FROM orchestration_workflows
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    return [_orchestration_workflow_row_to_dict(row) for row in rows]


def save_orchestration_workflow(openclaw_dir, payload):
    normalized = _normalize_orchestration_workflow(payload)
    if not normalized:
        raise RuntimeError("orchestration workflow name is required")
    with _connect(openclaw_dir) as conn:
        conn.execute(
            """
            INSERT INTO orchestration_workflows(
                workflow_id, name, description, status, lanes_json, nodes_json, created_at, updated_at, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                status = excluded.status,
                lanes_json = excluded.lanes_json,
                nodes_json = excluded.nodes_json,
                updated_at = excluded.updated_at,
                meta_json = excluded.meta_json
            """,
            (
                normalized["workflow_id"],
                normalized["name"],
                normalized["description"],
                normalized["status"],
                normalized["lanes_json"],
                normalized["nodes_json"],
                normalized["created_at"],
                normalized["updated_at"],
                normalized["meta_json"],
            ),
        )
        conn.commit()
    return next((item for item in list_orchestration_workflows(openclaw_dir) if item["id"] == normalized["workflow_id"]), None)


def list_routing_policies(openclaw_dir):
    with _connect(openclaw_dir) as conn:
        rows = conn.execute(
            """
            SELECT
                policy_id, name, status, strategy_type, keyword, target_agent_id, priority_level, queue_name,
                created_at, updated_at, meta_json
            FROM routing_policies
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    return [_routing_policy_row_to_dict(row) for row in rows]


def save_routing_policy(openclaw_dir, payload):
    normalized = _normalize_routing_policy(payload)
    if not normalized:
        raise RuntimeError("routing policy name is required")
    with _connect(openclaw_dir) as conn:
        conn.execute(
            """
            INSERT INTO routing_policies(
                policy_id, name, status, strategy_type, keyword, target_agent_id, priority_level, queue_name,
                created_at, updated_at, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(policy_id) DO UPDATE SET
                name = excluded.name,
                status = excluded.status,
                strategy_type = excluded.strategy_type,
                keyword = excluded.keyword,
                target_agent_id = excluded.target_agent_id,
                priority_level = excluded.priority_level,
                queue_name = excluded.queue_name,
                updated_at = excluded.updated_at,
                meta_json = excluded.meta_json
            """,
            (
                normalized["policy_id"],
                normalized["name"],
                normalized["status"],
                normalized["strategy_type"],
                normalized["keyword"],
                normalized["target_agent_id"],
                normalized["priority_level"],
                normalized["queue_name"],
                normalized["created_at"],
                normalized["updated_at"],
                normalized["meta_json"],
            ),
        )
        conn.commit()
    return next((item for item in list_routing_policies(openclaw_dir) if item["id"] == normalized["policy_id"]), None)


def list_tenants(openclaw_dir):
    with _connect(openclaw_dir) as conn:
        rows = conn.execute(
            """
            SELECT tenant_id, name, slug, status, primary_openclaw_dir, created_at, updated_at, meta_json
            FROM tenants
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    return [_tenant_row_to_dict(row) for row in rows]


def save_tenant(openclaw_dir, payload):
    normalized = _normalize_tenant(payload)
    if not normalized:
        raise RuntimeError("tenant name is required")
    with _connect(openclaw_dir) as conn:
        conn.execute(
            """
            INSERT INTO tenants(
                tenant_id, name, slug, status, primary_openclaw_dir, created_at, updated_at, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id) DO UPDATE SET
                name = excluded.name,
                slug = excluded.slug,
                status = excluded.status,
                primary_openclaw_dir = excluded.primary_openclaw_dir,
                updated_at = excluded.updated_at,
                meta_json = excluded.meta_json
            """,
            (
                normalized["tenant_id"],
                normalized["name"],
                normalized["slug"],
                normalized["status"],
                normalized["primary_openclaw_dir"],
                normalized["created_at"],
                normalized["updated_at"],
                normalized["meta_json"],
            ),
        )
        conn.commit()
    return next((item for item in list_tenants(openclaw_dir) if item["id"] == normalized["tenant_id"]), None)


def list_tenant_installations(openclaw_dir, tenant_id=""):
    with _connect(openclaw_dir) as conn:
        if tenant_id:
            rows = conn.execute(
                """
                SELECT tenant_id, openclaw_dir, label, role, created_at, updated_at, meta_json
                FROM tenant_installations
                WHERE tenant_id = ?
                ORDER BY updated_at DESC, created_at DESC
                """,
                (str(tenant_id).strip(),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT tenant_id, openclaw_dir, label, role, created_at, updated_at, meta_json
                FROM tenant_installations
                ORDER BY updated_at DESC, created_at DESC
                """
            ).fetchall()
    return [_tenant_installation_row_to_dict(row) for row in rows]


def save_tenant_installation(openclaw_dir, payload):
    normalized = _normalize_tenant_installation(payload)
    if not normalized:
        raise RuntimeError("tenant installation requires tenantId and openclawDir")
    with _connect(openclaw_dir) as conn:
        conn.execute(
            """
            INSERT INTO tenant_installations(
                tenant_id, openclaw_dir, label, role, created_at, updated_at, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, openclaw_dir) DO UPDATE SET
                label = excluded.label,
                role = excluded.role,
                updated_at = excluded.updated_at,
                meta_json = excluded.meta_json
            """,
            (
                normalized["tenant_id"],
                normalized["openclaw_dir"],
                normalized["label"],
                normalized["role"],
                normalized["created_at"],
                normalized["updated_at"],
                normalized["meta_json"],
            ),
        )
        conn.commit()
    return next(
        (
            item
            for item in list_tenant_installations(openclaw_dir, tenant_id=normalized["tenant_id"])
            if item["openclawDir"] == normalized["openclaw_dir"]
        ),
        None,
    )


def list_tenant_api_keys(openclaw_dir, tenant_id=""):
    with _connect(openclaw_dir) as conn:
        if tenant_id:
            rows = conn.execute(
                """
                SELECT key_id, tenant_id, name, prefix, status, scopes_json, created_at, last_used_at, meta_json
                FROM tenant_api_keys
                WHERE tenant_id = ?
                ORDER BY created_at DESC
                """,
                (str(tenant_id).strip(),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT key_id, tenant_id, name, prefix, status, scopes_json, created_at, last_used_at, meta_json
                FROM tenant_api_keys
                ORDER BY created_at DESC
                """
            ).fetchall()
    return [_tenant_api_key_row_to_dict(row) for row in rows]


def create_tenant_api_key(openclaw_dir, tenant_id, name, scopes=None):
    raw_key = f"slb_{secrets.token_urlsafe(24)}"
    record = _normalize_tenant_api_key(
        {
            "tenantId": tenant_id,
            "name": name,
            "rawKey": raw_key,
            "scopes": scopes or ["tenant:read", "dashboard:read", "agents:read", "tasks:read", "tasks:write"],
        }
    )
    if not record:
        raise RuntimeError("tenant API key requires tenantId and name")
    with _connect(openclaw_dir) as conn:
        conn.execute(
            """
            INSERT INTO tenant_api_keys(
                key_id, tenant_id, name, key_hash, prefix, status, scopes_json, created_at, last_used_at, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["key_id"],
                record["tenant_id"],
                record["name"],
                record["key_hash"],
                record["prefix"],
                record["status"],
                record["scopes_json"],
                record["created_at"],
                record["last_used_at"],
                record["meta_json"],
            ),
        )
        conn.commit()
    saved = next((item for item in list_tenant_api_keys(openclaw_dir, tenant_id=tenant_id) if item["id"] == record["key_id"]), None)
    return {"rawKey": raw_key, "key": saved}


def touch_tenant_api_key(openclaw_dir, key_id):
    key_id = str(key_id or "").strip()
    if not key_id:
        return
    with _connect(openclaw_dir) as conn:
        conn.execute(
            "UPDATE tenant_api_keys SET last_used_at = ? WHERE key_id = ?",
            (now_iso(), key_id),
        )
        conn.commit()


def resolve_tenant_api_key(openclaw_dir, raw_key):
    digest = hash_api_key(raw_key)
    with _connect(openclaw_dir) as conn:
        row = conn.execute(
            """
            SELECT key_id, tenant_id, name, prefix, status, scopes_json, created_at, last_used_at, meta_json
            FROM tenant_api_keys
            WHERE key_hash = ? AND status = 'active'
            """,
            (digest,),
        ).fetchone()
    if not row:
        return None
    return _tenant_api_key_row_to_dict(row)
