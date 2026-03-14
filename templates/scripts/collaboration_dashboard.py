#!/usr/bin/env python3
"""Generate a visual collaboration dashboard for all agents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


TERMINAL_STATES = {"done", "cancelled", "canceled"}
THEME_STYLES = {
    "imperial": {
        "bg": "#efe4d6",
        "bg2": "#f8f1e7",
        "ink": "#2c1f1a",
        "muted": "#6b564d",
        "accent": "#a34128",
        "accentStrong": "#7e2713",
        "accentSoft": "#f0c48e",
        "panel": "rgba(251, 244, 236, 0.82)",
        "line": "rgba(98, 63, 49, 0.16)",
        "ok": "#2f6b48",
        "warn": "#b16b1d",
        "danger": "#922d20",
    },
    "corporate": {
        "bg": "#e7ece8",
        "bg2": "#f4f7f4",
        "ink": "#1f2e27",
        "muted": "#587064",
        "accent": "#1f7a63",
        "accentStrong": "#12503f",
        "accentSoft": "#a8d5bf",
        "panel": "rgba(246, 249, 246, 0.86)",
        "line": "rgba(43, 77, 61, 0.14)",
        "ok": "#2d7a4e",
        "warn": "#a66b1d",
        "danger": "#8c3232",
    },
    "startup": {
        "bg": "#f4e6d8",
        "bg2": "#fbf4ea",
        "ink": "#2b241c",
        "muted": "#6b5b4b",
        "accent": "#cb5a1e",
        "accentStrong": "#92380f",
        "accentSoft": "#f5b774",
        "panel": "rgba(252, 246, 239, 0.86)",
        "line": "rgba(108, 72, 42, 0.14)",
        "ok": "#2e7652",
        "warn": "#b06a20",
        "danger": "#99392a",
    },
}


def infer_openclaw_dir(explicit_dir=None):
    if explicit_dir:
        return Path(explicit_dir).expanduser().resolve()

    env_dir = os.environ.get("OPENCLAW_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        if parent.name.startswith("workspace-"):
            return parent.parent

    return Path.home() / ".openclaw"


def parse_iso(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def now_utc():
    return datetime.now(timezone.utc)


def format_age(dt, now):
    if dt is None:
        return "无信号"
    delta = now - dt.astimezone(timezone.utc)
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return "刚刚"
    if total_seconds < 3600:
        return f"{total_seconds // 60} 分钟前"
    if total_seconds < 86400:
        return f"{total_seconds // 3600} 小时前"
    return f"{delta.days} 天前"


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_config(openclaw_dir):
    return load_json(Path(openclaw_dir) / "openclaw.json", {})


def load_agents(config):
    return config.get("agents", {}).get("list", [])


def get_router_agent_id(config):
    for agent in load_agents(config):
        if agent.get("default"):
            return agent["id"]
    agents = load_agents(config)
    return agents[0]["id"] if agents else "taizi"


def load_kanban_config(openclaw_dir, router_agent_id):
    router_cfg = Path(openclaw_dir) / f"workspace-{router_agent_id}" / "data" / "kanban_config.json"
    cfg = load_json(router_cfg, None)
    if cfg:
        return cfg

    for path in sorted(Path(openclaw_dir).glob("workspace-*/data/kanban_config.json")):
        cfg = load_json(path, None)
        if cfg:
            return cfg
    return {
        "state_agent_map": {},
        "org_agent_map": {},
        "agent_labels": {},
        "owner_title": "用户",
        "task_prefix": "TASK",
    }


def load_tasks_from_workspace(workspace):
    path = workspace / "data" / "tasks_source.json"
    data = load_json(path, [])
    return data if isinstance(data, list) else data.get("tasks", [])


def merge_tasks(openclaw_dir, config):
    merged = {}
    for agent in load_agents(config):
        workspace = Path(agent.get("workspace", ""))
        if not workspace.exists():
            workspace = Path(openclaw_dir) / f"workspace-{agent['id']}"
        for task in load_tasks_from_workspace(workspace):
            if not isinstance(task, dict):
                continue
            task_id = task.get("id")
            if not task_id:
                continue
            previous = merged.get(task_id)
            previous_dt = parse_iso((previous or {}).get("updatedAt"))
            current_dt = parse_iso(task.get("updatedAt"))
            if previous is None or (current_dt and (previous_dt is None or current_dt >= previous_dt)):
                merged[task_id] = task
    return sorted(
        merged.values(),
        key=lambda item: parse_iso(item.get("updatedAt")) or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )


def workspace_last_activity(workspace):
    latest = None
    if not workspace.exists():
        return None
    for path in workspace.rglob("*"):
        if path.is_file() and ".git" not in str(path):
            dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if latest is None or dt > latest:
                latest = dt
    return latest


def session_last_activity(openclaw_dir, agent_id):
    sessions_dir = Path(openclaw_dir) / "agents" / agent_id / "sessions"
    latest = None
    if not sessions_dir.exists():
        return None
    for path in sessions_dir.rglob("*"):
        if path.is_file():
            dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if latest is None or dt > latest:
                latest = dt
    return latest


def latest_progress_event(task):
    progress_log = task.get("progress_log", [])
    if not progress_log:
        return None
    return max(
        progress_log,
        key=lambda entry: parse_iso(entry.get("at")) or datetime.fromtimestamp(0, tz=timezone.utc),
    )


def latest_flow_event(task):
    flow_log = task.get("flow_log", [])
    if not flow_log:
        return None
    return max(
        flow_log,
        key=lambda entry: parse_iso(entry.get("at")) or datetime.fromtimestamp(0, tz=timezone.utc),
    )


def current_agent_for_task(task, kanban_cfg, router_agent_id):
    progress = latest_progress_event(task)
    if progress and progress.get("agent"):
        return progress["agent"]

    state = str(task.get("state", task.get("status", "")))
    org = task.get("org", "")
    if state in ("Doing", "Next") and kanban_cfg.get("org_agent_map", {}).get(org):
        return kanban_cfg["org_agent_map"][org]

    agent_id = kanban_cfg.get("state_agent_map", {}).get(state)
    if agent_id == "main":
        return router_agent_id
    return agent_id


def task_route(task):
    labels = []
    for entry in task.get("flow_log", []):
        if entry.get("from"):
            labels.append(str(entry["from"]))
        if entry.get("to"):
            labels.append(str(entry["to"]))
    deduped = []
    for label in labels:
        if not deduped or deduped[-1] != label:
            deduped.append(label)
    return deduped[-6:]


def todo_summary(task):
    todos = task.get("todos", [])
    if not todos:
        return {"total": 0, "completed": 0, "ratio": 0}
    completed = sum(1 for item in todos if item.get("status") == "completed")
    return {
        "total": len(todos),
        "completed": completed,
        "ratio": int((completed / len(todos)) * 100),
    }


def collect_events(tasks):
    events = []
    for task in tasks:
        title = task.get("title", task.get("id", "任务"))
        for entry in task.get("flow_log", []):
            events.append(
                {
                    "type": "handoff",
                    "at": entry.get("at"),
                    "taskId": task.get("id"),
                    "title": title,
                    "headline": f"{entry.get('from', '?')} -> {entry.get('to', '?')}",
                    "detail": entry.get("remark", ""),
                }
            )
        for entry in task.get("progress_log", []):
            agent = entry.get("agentLabel") or entry.get("agent") or "Agent"
            events.append(
                {
                    "type": "progress",
                    "at": entry.get("at"),
                    "taskId": task.get("id"),
                    "title": title,
                    "headline": f"{agent} 正在推进",
                    "detail": entry.get("text", ""),
                }
            )
    return sorted(
        events,
        key=lambda item: parse_iso(item.get("at")) or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )


def build_dashboard_data(openclaw_dir):
    openclaw_dir = Path(openclaw_dir)
    config = load_config(openclaw_dir)
    agents = load_agents(config)
    router_agent_id = get_router_agent_id(config)
    kanban_cfg = load_kanban_config(openclaw_dir, router_agent_id)
    now = now_utc()
    tasks = merge_tasks(openclaw_dir, config)
    events = collect_events(tasks)

    theme_name = config.get("sanshengLiubu", {}).get("theme", "imperial")
    theme_style = THEME_STYLES.get(theme_name, THEME_STYLES["imperial"])
    agent_labels = dict(kanban_cfg.get("agent_labels", {}))
    if router_agent_id not in agent_labels:
        agent_labels[router_agent_id] = next(
            (agent.get("identity", {}).get("name", router_agent_id) for agent in agents if agent.get("id") == router_agent_id),
            router_agent_id,
        )

    task_counts_by_agent = Counter()
    blocked_counts_by_agent = Counter()
    latest_focus_by_agent = {}
    latest_focus_dt_by_agent = {}

    active_tasks = []
    for task in tasks:
        state = str(task.get("state", task.get("status", ""))).lower()
        if state in TERMINAL_STATES:
            continue
        current_agent = current_agent_for_task(task, kanban_cfg, router_agent_id)
        if current_agent:
            task_counts_by_agent[current_agent] += 1
            if state == "blocked":
                blocked_counts_by_agent[current_agent] += 1
            progress = latest_progress_event(task)
            progress_dt = parse_iso((progress or {}).get("at")) or parse_iso(task.get("updatedAt"))
            if current_agent not in latest_focus_dt_by_agent or (
                progress_dt and progress_dt >= latest_focus_dt_by_agent[current_agent]
            ):
                latest_focus_dt_by_agent[current_agent] = progress_dt
                latest_focus_by_agent[current_agent] = task.get("now") or task.get("currentUpdate") or task.get("title")

        summary = todo_summary(task)
        active_tasks.append(
            {
                "id": task.get("id"),
                "title": task.get("title", task.get("id", "Untitled Task")),
                "state": task.get("state", task.get("status", "Unknown")),
                "owner": task.get("official", ""),
                "org": task.get("org", ""),
                "currentAgent": current_agent,
                "currentAgentLabel": agent_labels.get(current_agent, current_agent or task.get("org", "?")),
                "currentUpdate": task.get("now") or task.get("currentUpdate") or "",
                "updatedAt": task.get("updatedAt"),
                "updatedAgo": format_age(parse_iso(task.get("updatedAt")), now),
                "todo": summary,
                "route": task_route(task),
                "blocked": state == "blocked",
            }
        )

    agent_cards = []
    active_agent_count = 0
    for agent in agents:
        agent_id = agent["id"]
        workspace = Path(agent.get("workspace", "")) if agent.get("workspace") else openclaw_dir / f"workspace-{agent_id}"
        workspace_dt = workspace_last_activity(workspace)
        session_dt = session_last_activity(openclaw_dir, agent_id)
        signal_dt = latest_focus_dt_by_agent.get(agent_id)
        last_seen = max([dt for dt in (workspace_dt, session_dt, signal_dt) if dt is not None], default=None)

        focus = latest_focus_by_agent.get(agent_id, "")
        active_count = task_counts_by_agent[agent_id]
        blocked_count = blocked_counts_by_agent[agent_id]
        if blocked_count:
            status = "blocked"
        elif active_count and signal_dt and now - signal_dt <= timedelta(minutes=20):
            status = "active"
        elif active_count:
            status = "waiting"
        elif last_seen and now - last_seen <= timedelta(minutes=20):
            status = "standby"
        else:
            status = "idle"

        if status in {"active", "waiting", "blocked"}:
            active_agent_count += 1

        assigned_titles = [
            task["title"] for task in active_tasks if task.get("currentAgent") == agent_id
        ][:3]

        agent_cards.append(
            {
                "id": agent_id,
                "name": agent.get("identity", {}).get("name", agent_id),
                "title": agent_labels.get(agent_id, agent_id),
                "model": agent.get("model", "default"),
                "status": status,
                "activeTasks": active_count,
                "blockedTasks": blocked_count,
                "focus": focus,
                "assignedTitles": assigned_titles,
                "lastSeenAgo": format_age(last_seen, now),
                "lastSeenAt": last_seen.isoformat().replace("+00:00", "Z") if last_seen else "",
            }
        )

    recent_threshold = now - timedelta(hours=24)
    relay_counter = Counter()
    relay_last_at = {}
    for event in events:
        if event["type"] != "handoff":
            continue
        at = parse_iso(event.get("at"))
        if at is None or at < recent_threshold:
            continue
        edge = tuple(event.get("headline", "? -> ?").split(" -> ", 1))
        relay_counter[edge] += 1
        relay_last_at[edge] = max(at, relay_last_at.get(edge, at))

    relays = []
    for edge, count in relay_counter.most_common(10):
        relays.append(
            {
                "from": edge[0],
                "to": edge[1] if len(edge) > 1 else "?",
                "count": count,
                "lastAt": relay_last_at[edge].isoformat().replace("+00:00", "Z"),
                "lastAgo": format_age(relay_last_at[edge], now),
            }
        )

    completed_today = sum(
        1
        for task in tasks
        if str(task.get("state", task.get("status", ""))).lower() == "done"
        and (parse_iso(task.get("updatedAt")) or now) >= now - timedelta(days=1)
    )
    blocked_total = sum(1 for task in active_tasks if task.get("blocked"))
    signal_count = sum(
        1
        for event in events
        if parse_iso(event.get("at")) and parse_iso(event.get("at")) >= now - timedelta(hours=1)
    )

    return {
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "generatedAgo": "刚刚",
        "openclawDir": str(openclaw_dir),
        "theme": {
            "name": theme_name,
            "displayName": config.get("sanshengLiubu", {}).get("displayName", theme_name),
            "styles": theme_style,
        },
        "ownerTitle": kanban_cfg.get("owner_title", "用户"),
        "agents": agent_cards,
        "tasks": active_tasks[:24],
        "events": events[:36],
        "relays": relays,
        "metrics": {
            "activeTasks": len(active_tasks),
            "activeAgents": active_agent_count,
            "blockedTasks": blocked_total,
            "completedToday": completed_today,
            "handoffs24h": sum(item["count"] for item in relays),
            "signals1h": signal_count,
        },
    }


def dashboard_signature(data):
    def normalize(value):
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                if key in {"signature", "generatedAt", "generatedAgo"} or key.endswith("Ago"):
                    continue
                cleaned[key] = normalize(item)
            return cleaned
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    raw = json.dumps(normalize(data), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def render_html(data):
    styles = data["theme"]["styles"]
    json_blob = json.dumps(data, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Mission Control</title>
  <style>
    :root {{
      --bg: {styles['bg']};
      --bg-2: {styles['bg2']};
      --ink: {styles['ink']};
      --muted: {styles['muted']};
      --accent: {styles['accent']};
      --accent-strong: {styles['accentStrong']};
      --accent-soft: {styles['accentSoft']};
      --panel: {styles['panel']};
      --line: {styles['line']};
      --ok: {styles['ok']};
      --warn: {styles['warn']};
      --danger: {styles['danger']};
      --shadow: 0 24px 60px rgba(63, 42, 30, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; min-height: 100%; }}
    body {{
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 0% 0%, rgba(255,255,255,0.65), transparent 30%),
        radial-gradient(circle at 100% 10%, rgba(255,255,255,0.45), transparent 28%),
        linear-gradient(155deg, var(--bg), var(--bg-2));
    }}
    .shell {{
      width: min(1440px, calc(100vw - 32px));
      margin: 20px auto 40px;
      display: grid;
      gap: 18px;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      background: linear-gradient(135deg, color-mix(in srgb, var(--panel) 82%, white 18%), rgba(255,255,255,0.55));
      border: 1px solid var(--line);
      border-radius: 28px;
      padding: 28px 28px 24px;
      box-shadow: var(--shadow);
    }}
    .hero::after {{
      content: "";
      position: absolute;
      right: -80px;
      top: -40px;
      width: 240px;
      height: 240px;
      border-radius: 999px;
      background: radial-gradient(circle, color-mix(in srgb, var(--accent-soft) 70%, white 30%), transparent 66%);
      opacity: 0.7;
      pointer-events: none;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      color: var(--accent-strong);
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .eyebrow::before {{
      content: "";
      width: 38px;
      height: 1px;
      background: currentColor;
      opacity: 0.7;
    }}
    h1 {{
      font-family: "Fraunces", "Times New Roman", serif;
      font-size: clamp(2.4rem, 4vw, 4.8rem);
      line-height: 0.96;
      margin: 14px 0 10px;
      max-width: 12ch;
    }}
    .lede {{
      color: var(--muted);
      font-size: clamp(1rem, 1.8vw, 1.2rem);
      line-height: 1.7;
      max-width: 72ch;
      margin: 0 0 18px;
    }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 16px;
      color: var(--muted);
      font-size: 0.94rem;
    }}
    .metric-grid, .relay-grid, .agent-grid, .task-list, .event-feed {{
      display: grid;
      gap: 14px;
    }}
    .metric-grid {{
      grid-template-columns: repeat(6, minmax(0, 1fr));
      margin-top: 24px;
    }}
    .metric {{
      padding: 16px 16px 18px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.56);
      min-height: 110px;
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 0.82rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .metric-value {{
      font-family: "Fraunces", "Times New Roman", serif;
      font-size: clamp(1.8rem, 2.4vw, 3rem);
      margin-top: 10px;
    }}
    .metric-note {{
      color: var(--muted);
      margin-top: 6px;
      font-size: 0.9rem;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .panel-head {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 12px;
      padding: 22px 24px 12px;
      border-bottom: 1px solid var(--line);
    }}
    .panel-title {{
      font-family: "Fraunces", "Times New Roman", serif;
      font-size: 1.35rem;
      margin: 0;
    }}
    .panel-subtitle {{
      color: var(--muted);
      font-size: 0.94rem;
      margin: 4px 0 0;
    }}
    .relay-grid {{
      grid-template-columns: repeat(4, minmax(0, 1fr));
      padding: 18px 20px 22px;
    }}
    .relay {{
      border-radius: 18px;
      padding: 16px;
      background: rgba(255,255,255,0.52);
      border: 1px solid var(--line);
    }}
    .relay-path {{
      font-weight: 700;
      line-height: 1.4;
    }}
    .relay-count {{
      font-family: "Fraunces", "Times New Roman", serif;
      font-size: 2rem;
      margin-top: 8px;
    }}
    .relay-meta {{
      color: var(--muted);
      margin-top: 8px;
      font-size: 0.92rem;
    }}
    .main-grid {{
      display: grid;
      grid-template-columns: 1.3fr 1.6fr 1.05fr;
      gap: 18px;
      align-items: start;
    }}
    .agent-grid {{
      padding: 18px;
    }}
    .agent-card {{
      border-radius: 20px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.56);
      padding: 16px;
      display: grid;
      gap: 12px;
    }}
    .agent-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
    }}
    .agent-title {{
      font-weight: 700;
      font-size: 1.05rem;
      line-height: 1.3;
    }}
    .agent-meta {{
      color: var(--muted);
      font-size: 0.92rem;
      margin-top: 4px;
      line-height: 1.5;
    }}
    .status {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 7px 12px;
      font-size: 0.82rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      white-space: nowrap;
    }}
    .status::before {{
      content: "";
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: currentColor;
    }}
    .status-active {{ color: var(--ok); background: rgba(47, 107, 72, 0.08); }}
    .status-waiting {{ color: var(--warn); background: rgba(177, 107, 29, 0.09); }}
    .status-blocked {{ color: var(--danger); background: rgba(146, 45, 32, 0.09); }}
    .status-standby {{ color: var(--accent-strong); background: rgba(163, 65, 40, 0.08); }}
    .status-idle {{ color: var(--muted); background: rgba(103, 96, 89, 0.09); }}
    .agent-facts {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .fact {{
      padding: 12px;
      border-radius: 14px;
      background: rgba(255,255,255,0.6);
      border: 1px solid var(--line);
    }}
    .fact strong {{
      display: block;
      font-size: 1.15rem;
      margin-top: 4px;
    }}
    .fact span {{
      color: var(--muted);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .focus {{
      padding-top: 2px;
      color: var(--ink);
      line-height: 1.6;
    }}
    .pill-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255,255,255,0.72);
      border: 1px solid var(--line);
      color: var(--ink);
      font-size: 0.86rem;
    }}
    .task-list {{
      padding: 18px;
    }}
    .task-card {{
      border-radius: 22px;
      padding: 18px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.58);
      display: grid;
      gap: 14px;
      position: relative;
      overflow: hidden;
    }}
    .task-card.blocked::before {{
      content: "";
      position: absolute;
      inset: 0 auto 0 0;
      width: 6px;
      background: linear-gradient(180deg, var(--danger), color-mix(in srgb, var(--danger) 52%, transparent));
    }}
    .task-head {{
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 16px;
    }}
    .task-title {{
      font-weight: 700;
      font-size: 1.08rem;
      line-height: 1.45;
    }}
    .task-sub {{
      color: var(--muted);
      margin-top: 4px;
      font-size: 0.92rem;
    }}
    .task-state {{
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      font-size: 0.84rem;
      font-weight: 700;
    }}
    .progress-track {{
      width: 100%;
      height: 10px;
      border-radius: 999px;
      background: rgba(64, 52, 44, 0.08);
      overflow: hidden;
    }}
    .progress-fill {{
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), var(--accent-soft));
      transition: width 220ms ease-out;
    }}
    .task-copy {{
      line-height: 1.6;
    }}
    .task-copy strong {{
      display: block;
      font-size: 0.85rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .route {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .route-step {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 0.84rem;
      color: var(--muted);
    }}
    .route-step:not(:last-child)::after {{
      content: "→";
      color: var(--accent);
      margin-left: 2px;
    }}
    .todo-row {{
      display: flex;
      gap: 12px;
      align-items: center;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .event-feed {{
      padding: 18px 18px 20px 26px;
      position: relative;
    }}
    .event-feed::before {{
      content: "";
      position: absolute;
      left: 26px;
      top: 18px;
      bottom: 18px;
      width: 1px;
      background: var(--line);
    }}
    .event {{
      position: relative;
      padding-left: 24px;
      margin-left: 0;
    }}
    .event::before {{
      content: "";
      position: absolute;
      left: -5px;
      top: 7px;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 0 5px rgba(255,255,255,0.68);
    }}
    .event-progress::before {{ background: var(--ok); }}
    .event-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
    }}
    .event-title {{
      font-weight: 700;
      line-height: 1.4;
    }}
    .event-meta {{
      color: var(--muted);
      font-size: 0.86rem;
      white-space: nowrap;
    }}
    .event-detail {{
      color: var(--muted);
      line-height: 1.6;
      margin-top: 5px;
    }}
    .empty {{
      color: var(--muted);
      padding: 12px 0 4px;
      line-height: 1.7;
    }}
    .hero-tools {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
      margin-top: 18px;
    }}
    .button {{
      appearance: none;
      border: 0;
      border-radius: 999px;
      background: var(--accent);
      color: #fffaf4;
      padding: 11px 16px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 10px 24px rgba(125, 58, 21, 0.16);
    }}
    .ghost {{
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      box-shadow: none;
      border: 1px solid var(--line);
      text-decoration: none;
    }}
    .live-indicator {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 0.94rem;
      transition: color 180ms ease-out;
    }}
    .live-indicator::before {{
      content: "";
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: currentColor;
      box-shadow: 0 0 0 0 currentColor;
      animation: pulse 2.2s infinite;
    }}
    .live-indicator[data-tone="live"] {{ color: var(--ok); }}
    .live-indicator[data-tone="warn"] {{ color: var(--warn); }}
    .live-indicator[data-tone="idle"] {{ color: var(--muted); }}
    .live-indicator[data-tone="paused"] {{ color: var(--accent-strong); }}
    @keyframes pulse {{
      0% {{ box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 28%, transparent); }}
      70% {{ box-shadow: 0 0 0 12px color-mix(in srgb, currentColor 0%, transparent); }}
      100% {{ box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 0%, transparent); }}
    }}
    @media (max-width: 1220px) {{
      .metric-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .relay-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .main-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 760px) {{
      .shell {{ width: min(100vw - 20px, 1440px); margin: 12px auto 26px; }}
      .hero {{ padding: 22px 18px 20px; border-radius: 24px; }}
      .metric-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .relay-grid {{ grid-template-columns: 1fr; }}
      .agent-facts {{ grid-template-columns: 1fr 1fr; }}
      .panel-head {{ padding: 18px 18px 10px; }}
      .agent-grid, .task-list, .event-feed {{ padding: 16px; }}
      .event-feed::before {{ left: 16px; }}
      .event {{ padding-left: 20px; }}
      .event::before {{ left: -15px; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      * {{ scroll-behavior: auto !important; animation: none !important; transition: none !important; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="eyebrow">Multi-Agent Mission Control</div>
      <h1>用户终于能看到协同正在发生。</h1>
      <p class="lede">这不是任务清单，而是运行中的协作现场。你能看到每个 Agent 当前的焦点、接力路径、最近信号和阻塞点，判断系统是真的在并行推进，还是只是在串行等待。</p>
      <div class="hero-meta">
        <span>主题：<strong id="theme-name"></strong></span>
        <span>主理人：<strong id="owner-title"></strong></span>
        <span>生成时间：<strong id="generated-at"></strong></span>
        <span>安装目录：<strong id="install-dir"></strong></span>
      </div>
      <div class="hero-tools">
        <button class="button" id="refresh-now">立即刷新</button>
        <button class="button ghost" id="toggle-refresh">暂停实时刷新</button>
        <a class="button ghost" href="./collaboration-dashboard.json">查看 JSON 快照</a>
        <span class="live-indicator" data-tone="idle" id="live-indicator"></span>
      </div>
      <div class="metric-grid" id="metric-grid"></div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2 class="panel-title">接力网</h2>
          <p class="panel-subtitle">过去 24 小时最频繁的 handoff，能看出系统是不是在真正协同。</p>
        </div>
      </div>
      <div class="relay-grid" id="relay-grid"></div>
    </section>

    <div class="main-grid">
      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">Agent 现场</h2>
            <p class="panel-subtitle">每个 Agent 当前的状态、最近信号和在手任务。</p>
          </div>
        </div>
        <div class="agent-grid" id="agent-grid"></div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">任务河道</h2>
            <p class="panel-subtitle">当前活跃任务的负责人、进展和流转路径。</p>
          </div>
        </div>
        <div class="task-list" id="task-list"></div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">信号时间线</h2>
            <p class="panel-subtitle">最近发生的 handoff 与 progress，帮助你判断系统是否持续推进。</p>
          </div>
        </div>
        <div class="event-feed" id="event-feed"></div>
      </section>
    </div>
  </div>

  <script id="dashboard-data" type="application/json">{json_blob}</script>
  <script>
    let state = JSON.parse(document.getElementById("dashboard-data").textContent);
    const metricGrid = document.getElementById("metric-grid");
    const relayGrid = document.getElementById("relay-grid");
    const agentGrid = document.getElementById("agent-grid");
    const taskList = document.getElementById("task-list");
    const eventFeed = document.getElementById("event-feed");
    const generatedAt = document.getElementById("generated-at");
    const themeName = document.getElementById("theme-name");
    const ownerTitle = document.getElementById("owner-title");
    const installDir = document.getElementById("install-dir");
    const refreshNow = document.getElementById("refresh-now");
    const toggleRefresh = document.getElementById("toggle-refresh");
    const liveIndicator = document.getElementById("live-indicator");

    const supportsHttp = location.protocol.startsWith("http");
    let paused = false;
    let eventSource = null;
    let reconnectTimer = null;
    let lastSyncAt = Date.now();
    let connectionMode = supportsHttp ? "connecting" : "snapshot";
    let fetchInFlight = false;

    function el(tag, className, text) {{
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    }}

    function clearNode(node) {{
      node.textContent = "";
    }}

    function setLiveStatus(text, tone) {{
      liveIndicator.dataset.tone = tone;
      liveIndicator.textContent = text;
    }}

    function renderMetrics() {{
      clearNode(metricGrid);
      const metrics = [
        ["活跃任务", state.metrics.activeTasks, "还在推进中的任务数量"],
        ["活跃 Agent", state.metrics.activeAgents, "当前正在处理或等待结果的 Agent"],
        ["阻塞任务", state.metrics.blockedTasks, "需要用户介入或额外资源的任务"],
        ["今日完成", state.metrics.completedToday, "过去 24 小时完成的任务"],
        ["24h 接力", state.metrics.handoffs24h, "最近 24 小时 handoff 总次数"],
        ["1h 信号", state.metrics.signals1h, "最近一小时 progress 与 handoff 信号"],
      ];
      metrics.forEach(([label, value, note]) => {{
        const card = el("div", "metric");
        card.append(el("div", "metric-label", label));
        card.append(el("div", "metric-value", String(value)));
        card.append(el("div", "metric-note", note));
        metricGrid.append(card);
      }});
    }}

    function renderRelays() {{
      clearNode(relayGrid);
      if (!state.relays.length) {{
        relayGrid.append(el("div", "empty", "最近 24 小时还没有足够的接力记录。先运行几轮任务，协同图就会出现。"));
        return;
      }}
      state.relays.forEach((relay) => {{
        const card = el("div", "relay");
        card.append(el("div", "relay-path", `${{relay.from}} → ${{relay.to}}`));
        card.append(el("div", "relay-count", `${{relay.count}} 次`));
        card.append(el("div", "relay-meta", `最近一次：${{relay.lastAgo}}`));
        relayGrid.append(card);
      }});
    }}

    function renderAgents() {{
      clearNode(agentGrid);
      state.agents.forEach((agent) => {{
        const card = el("article", "agent-card");
        const head = el("div", "agent-head");
        const identity = el("div");
        identity.append(el("div", "agent-title", agent.title));
        identity.append(el("div", "agent-meta", `${{agent.name}} · ${{agent.id}} · ${{agent.model}}`));
        head.append(identity, el("div", `status status-${{agent.status}}`, agent.status));
        card.append(head);

        const facts = el("div", "agent-facts");
        [["在手任务", agent.activeTasks], ["阻塞", agent.blockedTasks], ["最后信号", agent.lastSeenAgo]].forEach(([label, value]) => {{
          const fact = el("div", "fact");
          fact.append(el("span", "", label));
          fact.append(el("strong", "", String(value)));
          facts.append(fact);
        }});
        card.append(facts);

        const focus = el("div", "focus");
        focus.textContent = agent.focus || "当前没有明确的 progress signal，可以继续观察下一次任务推进。";
        card.append(focus);

        const pills = el("div", "pill-row");
        if (agent.assignedTitles.length) {{
          agent.assignedTitles.forEach((title) => pills.append(el("span", "pill", title)));
        }} else {{
          pills.append(el("span", "pill", "当前无在手任务"));
        }}
        card.append(pills);
        agentGrid.append(card);
      }});
    }}

    function renderTasks() {{
      clearNode(taskList);
      if (!state.tasks.length) {{
        taskList.append(el("div", "empty", "当前没有活跃任务。可以先发起一个明确任务，系统会在这里展示协同过程。"));
        return;
      }}
      state.tasks.forEach((task) => {{
        const card = el("article", `task-card${{task.blocked ? ' blocked' : ''}}`);
        const head = el("div", "task-head");
        const titleWrap = el("div");
        titleWrap.append(el("div", "task-title", task.title));
        titleWrap.append(el("div", "task-sub", `${{task.id}} · 当前负责人：${{task.currentAgentLabel || task.org || '未知'}} · ${{task.updatedAgo}}`));
        head.append(titleWrap);
        head.append(el("div", "task-state", task.state));
        card.append(head);

        const progressTrack = el("div", "progress-track");
        const progressFill = el("div", "progress-fill");
        progressFill.style.width = `${{task.todo.ratio || 0}}%`;
        progressTrack.append(progressFill);
        card.append(progressTrack);

        const todoRow = el("div", "todo-row");
        todoRow.textContent = task.todo.total
          ? `Todo 完成 ${{task.todo.completed}} / ${{task.todo.total}}`
          : "当前还没有拆出 todos，可以继续观察下一次 progress 更新。";
        card.append(todoRow);

        const update = el("div", "task-copy");
        update.append(el("strong", "", "当前焦点"));
        update.append(el("div", "", task.currentUpdate || "暂时没有进展描述"));
        card.append(update);

        const route = el("div", "route");
        if (task.route.length) {{
          task.route.forEach((step) => route.append(el("span", "route-step", step)));
        }} else {{
          route.append(el("span", "route-step", "还没有形成流转路径"));
        }}
        card.append(route);
        taskList.append(card);
      }});
    }}

    function renderEvents() {{
      clearNode(eventFeed);
      if (!state.events.length) {{
        eventFeed.append(el("div", "empty", "还没有 progress 或 handoff 事件。"));
        return;
      }}
      state.events.forEach((event) => {{
        const item = el("article", `event event-${{event.type}}`);
        const head = el("div", "event-head");
        const title = el("div");
        title.append(el("div", "event-title", event.headline));
        title.append(el("div", "event-detail", `${{event.taskId}} · ${{event.title}}`));
        head.append(title);
        head.append(el("div", "event-meta", event.at ? new Date(event.at).toLocaleString() : "未知时间"));
        item.append(head);
        if (event.detail) {{
          item.append(el("div", "event-detail", event.detail));
        }}
        eventFeed.append(item);
      }});
    }}

    function renderMeta() {{
      generatedAt.textContent = new Date(state.generatedAt).toLocaleString();
      themeName.textContent = state.theme.displayName;
      ownerTitle.textContent = state.ownerTitle;
      installDir.textContent = state.openclawDir;
    }}

    function renderAll() {{
      renderMeta();
      renderMetrics();
      renderRelays();
      renderAgents();
      renderTasks();
      renderEvents();
    }}

    async function fetchLatestDashboard(reason = "manual") {{
      if (!supportsHttp || paused || fetchInFlight) {{
        return;
      }}
      fetchInFlight = true;
      try {{
        const response = await fetch(`./api/dashboard?_=${{Date.now()}}`, {{ cache: "no-store" }});
        if (!response.ok) {{
          throw new Error(`HTTP ${{response.status}}`);
        }}
        state = await response.json();
        lastSyncAt = Date.now();
        renderAll();
        connectionMode = reason === "stream" ? "live" : connectionMode;
      }} catch (_error) {{
        connectionMode = "degraded";
      }} finally {{
        fetchInFlight = false;
      }}
    }}

    function disconnectLive() {{
      if (eventSource) {{
        eventSource.close();
        eventSource = null;
      }}
      if (reconnectTimer) {{
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }}
    }}

    function connectLive() {{
      if (!supportsHttp || paused) {{
        return;
      }}
      if (!window.EventSource) {{
        connectionMode = "snapshot";
        return;
      }}
      disconnectLive();
      connectionMode = "connecting";
      setLiveStatus("正在建立实时连接...", "warn");
      eventSource = new EventSource("./events");
      eventSource.addEventListener("dashboard", async () => {{
        await fetchLatestDashboard("stream");
      }});
      eventSource.onopen = () => {{
        connectionMode = "live";
        lastSyncAt = Date.now();
      }};
      eventSource.onerror = () => {{
        if (paused) {{
          return;
        }}
        connectionMode = "degraded";
        disconnectLive();
        reconnectTimer = setTimeout(() => connectLive(), 4000);
      }};
    }}

    refreshNow.addEventListener("click", async () => {{
      if (supportsHttp) {{
        await fetchLatestDashboard("manual");
      }} else {{
        location.reload();
      }}
    }});

    toggleRefresh.addEventListener("click", async () => {{
      paused = !paused;
      toggleRefresh.textContent = paused ? "恢复实时刷新" : "暂停实时刷新";
      if (paused) {{
        disconnectLive();
        setLiveStatus("实时刷新已暂停", "paused");
      }} else {{
        await fetchLatestDashboard("manual");
        connectLive();
      }}
    }});

    setInterval(() => {{
      if (paused) {{
        return;
      }}
      if (!supportsHttp) {{
        setLiveStatus("当前是本地快照模式", "idle");
        return;
      }}
      const ageSeconds = Math.max(0, Math.floor((Date.now() - lastSyncAt) / 1000));
      if (connectionMode === "live") {{
        setLiveStatus(`实时连接中 · 最近同步 ${{ageSeconds}} 秒前`, "live");
      }} else if (connectionMode === "connecting") {{
        setLiveStatus("正在建立实时连接...", "warn");
      }} else if (connectionMode === "degraded") {{
        setLiveStatus(`连接中断，正在重连 · 最近同步 ${{ageSeconds}} 秒前`, "warn");
      }} else {{
        setLiveStatus(`快照模式 · 最近同步 ${{ageSeconds}} 秒前`, "idle");
      }}
    }}, 1000);

    renderAll();
    if (supportsHttp) {{
      connectLive();
      fetchLatestDashboard("manual");
    }} else {{
      setLiveStatus("当前是本地快照模式", "idle");
    }}
  </script>
</body>
</html>
"""


def build_dashboard_bundle(openclaw_dir, output_dir=None):
    data = build_dashboard_data(openclaw_dir)
    data["signature"] = dashboard_signature(data)
    paths = write_dashboard_files(openclaw_dir, data, output_dir=output_dir)
    return data, paths


def write_dashboard_files(openclaw_dir, data, output_dir=None):
    openclaw_dir = Path(openclaw_dir)
    output_dir = Path(output_dir) if output_dir else openclaw_dir / "dashboard"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "collaboration-dashboard.json"
    html_path = output_dir / "collaboration-dashboard.html"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    return {"json": json_path, "html": html_path}


class CollaborationDashboardHandler(BaseHTTPRequestHandler):
    server_version = "SanshengDashboard/1.4"

    def log_message(self, format, *args):
        return

    def _send_bytes(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _bundle(self):
        return build_dashboard_bundle(self.server.openclaw_dir, self.server.output_dir)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/collaboration-dashboard.html"):
            data, _paths = self._bundle()
            body = render_html(data).encode("utf-8")
            self._send_bytes(body, "text/html; charset=utf-8")
            return
        if path in ("/api/dashboard", "/collaboration-dashboard.json"):
            data, _paths = self._bundle()
            body = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/events":
            self._serve_events()
            return

        body = b"Not found"
        self._send_bytes(body, "text/plain; charset=utf-8", status=404)

    def _serve_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_signature = None
        try:
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            while True:
                data, _paths = self._bundle()
                if data["signature"] != last_signature:
                    payload = json.dumps(
                        {
                            "signature": data["signature"],
                            "generatedAt": data["generatedAt"],
                        },
                        ensure_ascii=False,
                    )
                    self.wfile.write(f"event: dashboard\ndata: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    last_signature = data["signature"]
                else:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                time.sleep(self.server.live_interval)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return


def serve_dashboard(openclaw_dir, output_dir, port, live_interval):
    server = ThreadingHTTPServer(("127.0.0.1", port), CollaborationDashboardHandler)
    server.openclaw_dir = Path(openclaw_dir)
    server.output_dir = Path(output_dir) if output_dir else Path(openclaw_dir) / "dashboard"
    server.live_interval = live_interval
    build_dashboard_bundle(server.openclaw_dir, server.output_dir)
    print(f"Serving collaboration dashboard at http://127.0.0.1:{port}/collaboration-dashboard.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=18890)
    parser.add_argument("--live-interval", type=float, default=2.0)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    openclaw_dir = infer_openclaw_dir(args.dir)
    data, paths = build_dashboard_bundle(openclaw_dir, args.output_dir or None)
    if not args.quiet:
        print(f"Generated dashboard HTML: {paths['html']}")
        print(f"Generated dashboard JSON: {paths['json']}")
    if args.serve:
        serve_dashboard(openclaw_dir, args.output_dir or None, args.port, args.live_interval)


if __name__ == "__main__":
    main()
