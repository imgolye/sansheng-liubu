#!/usr/bin/env python3
"""三省六部健康看板 - 一键查看所有 agent 状态和最近活动"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

OPENCLAW_DIR = Path.home() / ".openclaw"

# Default agents (imperial theme fallback)
_DEFAULT_AGENTS = [
    ("taizi", "太子", "消息路由"),
    ("zhongshu", "中书省", "规划决策"),
    ("menxia", "门下省", "审议把关"),
    ("shangshu", "尚书省", "执行调度"),
    ("gongbu", "工部", "开发/架构"),
    ("bingbu", "兵部", "运维/部署"),
    ("hubu", "户部", "数据/分析"),
    ("libu", "礼部", "文档/对外"),
    ("xingbu", "刑部", "测试/审查"),
    ("libu_hr", "吏部", "人事/培训"),
    ("zaochao", "早朝简报官", "情报简报"),
]


def load_agents_from_config():
    """Load agent list from openclaw.json or theme config."""
    config_file = OPENCLAW_DIR / "openclaw.json"
    try:
        with open(config_file) as f:
            config = json.load(f)
        agents = []
        for agent in config.get("agents", {}).get("list", []):
            aid = agent["id"]
            name = agent.get("identity", {}).get("name", aid)
            desc = agent.get("description", "")
            agents.append((aid, name, desc))
        if agents:
            return agents
    except Exception:
        pass
    return _DEFAULT_AGENTS


AGENTS = load_agents_from_config()


def get_gateway_health():
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "health"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def get_workspace_activity(agent_id):
    """获取 workspace 最近修改时间"""
    ws = OPENCLAW_DIR / f"workspace-{agent_id}"
    if not ws.exists():
        return None
    latest = None
    for f in ws.rglob("*"):
        if f.is_file() and ".git" not in str(f):
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if latest is None or mtime > latest:
                latest = mtime
    return latest


def get_session_activity(agent_id):
    """获取 session 最近活动时间"""
    sessions_dir = OPENCLAW_DIR / "agents" / agent_id / "sessions"
    if not sessions_dir.exists():
        return None
    latest = None
    for f in sessions_dir.rglob("*"):
        if f.is_file():
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if latest is None or mtime > latest:
                latest = mtime
    return latest


def format_age(dt):
    if dt is None:
        return "无记录"
    delta = datetime.now() - dt
    if delta < timedelta(minutes=5):
        return "刚刚"
    elif delta < timedelta(hours=1):
        return f"{int(delta.total_seconds() / 60)}分钟前"
    elif delta < timedelta(days=1):
        return f"{int(delta.total_seconds() / 3600)}小时前"
    else:
        return f"{delta.days}天前"


def get_active_tasks():
    """从 tasks_source.json 获取活跃任务"""
    tasks_file = OPENCLAW_DIR / "workspace-taizi" / "data" / "tasks_source.json"
    if not tasks_file.exists():
        return []
    try:
        with open(tasks_file) as f:
            data = json.load(f)
        active = []
        tasks = data if isinstance(data, list) else data.get("tasks", [])
        for t in tasks:
            state = t.get("state", t.get("status", ""))
            if state.lower() in ("doing", "assigned", "blocked", "zhongshu", "menxia"):
                active.append(t)
        return active
    except Exception:
        return []


def get_model_info():
    """获取 agent 模型配置"""
    config_file = OPENCLAW_DIR / "openclaw.json"
    try:
        with open(config_file) as f:
            config = json.load(f)
        models = {}
        for agent in config.get("agents", {}).get("list", []):
            models[agent["id"]] = agent.get("model", "default")
        return models
    except Exception:
        return {}


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    models = get_model_info()

    print(f"{'='*70}")
    print(f"  Health Dashboard  |  {now}")
    print(f"{'='*70}")

    # Gateway
    print(f"\n--- 网关状态 ---")
    health = get_gateway_health()
    for line in health.split("\n"):
        if line.strip():
            print(f"  {line.strip()}")

    # Agents
    print(f"\n--- Agent 状态 ---")
    print(f"  {'Agent':<12} {'名称':<10} {'模型':<24} {'工作区活动':<12} {'会话活动':<12}")
    print(f"  {'-'*12} {'-'*10} {'-'*24} {'-'*12} {'-'*12}")

    for agent_id, name, role in AGENTS:
        ws_time = get_workspace_activity(agent_id)
        sess_time = get_session_activity(agent_id)
        model = models.get(agent_id, "?")
        # 截短模型名
        if len(model) > 22:
            model = model[-22:]
        print(f"  {agent_id:<12} {name:<10} {model:<24} {format_age(ws_time):<12} {format_age(sess_time):<12}")

    # Active tasks
    active = get_active_tasks()
    print(f"\n--- 活跃任务 ({len(active)}) ---")
    if active:
        for t in active[:10]:
            tid = t.get("id", "?")
            title = t.get("title", "?")[:30]
            state = t.get("state", t.get("status", "?"))
            now_field = t.get("now", t.get("currentUpdate", ""))[:40]
            print(f"  {tid}  [{state}]  {title}")
            if now_field:
                print(f"    -> {now_field}")
    else:
        print("  无活跃任务")

    # Logs
    print(f"\n--- 日志状态 ---")
    log_dir = OPENCLAW_DIR / "logs"
    if log_dir.exists():
        for log in sorted(log_dir.glob("*.log")):
            size = log.stat().st_size
            mtime = format_age(datetime.fromtimestamp(log.stat().st_mtime))
            size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size}B"
            print(f"  {log.name:<30} {size_str:<10} {mtime}")
    else:
        print("  日志目录不存在")

    print(f"\n{'='*70}")


if __name__ == "__main__":
    main()
