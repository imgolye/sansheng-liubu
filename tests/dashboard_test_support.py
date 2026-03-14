import contextlib
import json
import os
import stat
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "templates" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import collaboration_dashboard  # noqa: E402


TEST_TOKEN = "test-token"


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_transcript(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "type": "model_change",
            "modelId": "gpt-5",
            "provider": "openai",
        },
        {
            "type": "message",
            "timestamp": "2026-03-14T08:00:00Z",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "今天还有哪些任务未收口？"}],
            },
        },
        {
            "type": "message",
            "timestamp": "2026-03-14T08:00:03Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "当前仍有 1 条任务在推进中。"}],
            },
        },
    ]
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in entries), encoding="utf-8")


def _fake_openclaw_cli():
    return """#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def now_ms():
    return int(datetime(2026, 3, 14, 8, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)


def transcript_path(state_dir, agent_id, session_id):
    return Path(state_dir) / "agents" / agent_id / "sessions" / f"{session_id}.jsonl"


def append_transcript(state_dir, agent_id, session_id, user_text):
    path = transcript_path(state_dir, agent_id, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    response = f"已收到：{user_text}"
    entries = [
        {
            "type": "message",
            "timestamp": "2026-03-14T08:15:00Z",
            "message": {"role": "user", "content": [{"type": "text", "text": user_text}]},
        },
        {
            "type": "message",
            "timestamp": "2026-03-14T08:15:01Z",
            "message": {"role": "assistant", "content": [{"type": "text", "text": response}]},
        },
    ]
    with path.open("a", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\\n")
    return response


def main():
    args = sys.argv[1:]
    state_dir = os.environ.get("OPENCLAW_STATE_DIR", "")

    if not args:
        print("OpenClaw test shim", file=sys.stderr)
        return 1

    if args == ["--version"]:
        print("OpenClaw 2026.3.12 (test-build)")
        return 0

    if args[:3] == ["config", "validate", "--json"]:
        print(json.dumps({"valid": True, "path": str(Path(state_dir) / "openclaw.json")}, ensure_ascii=False))
        return 0

    if args[:3] == ["gateway", "health", "--json"]:
        payload = {
            "ok": True,
            "defaultAgentId": "taizi",
            "agents": [{"id": "taizi"}],
            "channels": {
                "telegram": {
                    "configured": True,
                    "running": True,
                    "probe": {"ok": True, "bot": {"username": "demo_bot"}},
                }
            },
            "channelLabels": {"telegram": "Telegram"},
            "channelOrder": ["telegram"],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if args[:3] == ["skills", "list", "--json"]:
        payload = {
            "managedSkillsDir": str(Path(state_dir) / "skills"),
            "workspaceDir": str(Path(state_dir) / "workspace-taizi"),
            "skills": [
                {
                    "name": "demo-skill",
                    "eligible": True,
                    "bundled": False,
                    "source": "managed",
                    "description": "Fixture skill",
                }
            ],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if args[:3] == ["sessions", "--all-agents", "--json"]:
        payload = {
            "sessions": [
                {
                    "key": "main:taizi",
                    "agentId": "taizi",
                    "sessionId": "main",
                    "updatedAt": now_ms(),
                    "kind": "direct",
                    "model": "gpt-5",
                    "modelProvider": "openai",
                }
            ]
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if args[:2] == ["agent", "--agent"]:
        agent_id = args[2]
        session_id = "main"
        message = ""
        if "--session-id" in args:
            session_id = args[args.index("--session-id") + 1]
        if "--message" in args:
            message = args[args.index("--message") + 1]
        reply = append_transcript(state_dir, agent_id, session_id, message)
        payload = {
            "status": "ok",
            "result": {
                "meta": {"agentMeta": {"agentId": agent_id, "sessionId": session_id}},
                "payloads": [{"text": reply}],
            },
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    print(json.dumps({"error": "unsupported", "args": args}, ensure_ascii=False), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
"""


def create_fixture_openclaw_dir(base_dir):
    openclaw_dir = Path(base_dir)
    openclaw_dir.mkdir(parents=True, exist_ok=True)
    (openclaw_dir / ".env").write_text(f"GATEWAY_AUTH_TOKEN={TEST_TOKEN}\n", encoding="utf-8")
    os.chmod(openclaw_dir / ".env", 0o600)
    _write_json(
        openclaw_dir / "openclaw.json",
        {
            "agents": {
                "list": [
                    {"id": "taizi", "default": True, "workspace": str(openclaw_dir / "workspace-taizi")},
                    {"id": "zhongshu", "workspace": str(openclaw_dir / "workspace-zhongshu")},
                ]
            }
        },
    )
    _write_json(
        openclaw_dir / "sansheng-liubu.json",
        {
            "theme": "imperial",
            "displayName": "皇帝朝廷",
            "projectDir": str(ROOT),
            "taskPrefix": "JJC",
        },
    )
    kanban_config = {
        "owner_title": "皇上",
        "task_prefix": "JJC",
        "state_agent_map": {"Doing": "zhongshu", "Done": "taizi"},
        "org_agent_map": {"中书省": "zhongshu"},
        "agent_labels": {"taizi": "太子", "zhongshu": "中书令"},
    }
    _write_json(openclaw_dir / "workspace-taizi" / "data" / "kanban_config.json", kanban_config)
    _write_json(openclaw_dir / "workspace-zhongshu" / "data" / "kanban_config.json", kanban_config)
    tasks = [
        {
            "id": "JJC-TEST-001",
            "title": "验证商业产品交付链",
            "state": "Doing",
            "org": "中书省",
            "owner": "中书令",
            "updatedAt": "2026-03-14T08:05:00Z",
            "flow_log": [
                {
                    "from": "太子",
                    "to": "中书令",
                    "at": "2026-03-14T08:00:00Z",
                    "remark": "转交执行",
                }
            ],
            "progress_log": [
                {
                    "agent": "zhongshu",
                    "agentLabel": "中书令",
                    "at": "2026-03-14T08:05:00Z",
                    "text": "正在梳理可视化与测试能力。",
                }
            ],
            "todos": [
                {"title": "完成 Overview 图表", "status": "completed"},
                {"title": "补 E2E 测试", "status": "pending"},
            ],
        },
        {
            "id": "JJC-TEST-002",
            "title": "归档已完成交付",
            "state": "Done",
            "owner": "中书令",
            "output": "deliverables/release-note.md",
            "updatedAt": "2026-03-14T07:40:00Z",
            "flow_log": [],
            "progress_log": [],
            "todos": [],
        },
    ]
    _write_json(openclaw_dir / "workspace-taizi" / "data" / "tasks_source.json", tasks)
    _write_json(openclaw_dir / "workspace-zhongshu" / "data" / "tasks_source.json", tasks)
    _write_transcript(openclaw_dir / "agents" / "taizi" / "sessions" / "main.jsonl")

    bin_dir = openclaw_dir / "test-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    cli_path = bin_dir / "openclaw"
    cli_path.write_text(_fake_openclaw_cli(), encoding="utf-8")
    cli_path.chmod(cli_path.stat().st_mode | stat.S_IEXEC)
    return openclaw_dir


@contextlib.contextmanager
def patched_openclaw_path(openclaw_dir):
    bin_dir = str(Path(openclaw_dir) / "test-bin")
    original = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{original}"
    try:
        yield
    finally:
        os.environ["PATH"] = original


@contextlib.contextmanager
def running_dashboard_server(openclaw_dir, frontend_dist=""):
    openclaw_dir = Path(openclaw_dir).resolve()
    output_dir = openclaw_dir / "dashboard"
    server = ThreadingHTTPServer(("127.0.0.1", 0), collaboration_dashboard.CollaborationDashboardHandler)
    server.openclaw_dir = openclaw_dir
    server.output_dir = output_dir
    server.live_interval = 0.2
    server.dashboard_auth_token = collaboration_dashboard.resolve_dashboard_auth_token(openclaw_dir)
    server.frontend_dist = collaboration_dashboard.resolve_frontend_dist(openclaw_dir, explicit_path=frontend_dist)
    server.cors_origins = collaboration_dashboard.parse_cors_origins(",".join(sorted(collaboration_dashboard.DEFAULT_FRONTEND_ORIGINS)))
    collaboration_dashboard.build_dashboard_bundle(openclaw_dir, output_dir)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextlib.contextmanager
def fixture_dashboard(frontend_dist=""):
    with tempfile.TemporaryDirectory() as tmpdir:
        openclaw_dir = create_fixture_openclaw_dir(tmpdir)
        with patched_openclaw_path(openclaw_dir):
            with running_dashboard_server(openclaw_dir, frontend_dist=frontend_dist) as base_url:
                yield openclaw_dir, base_url
