#!/usr/bin/env python3
"""刷新看板数据 — 被 kanban_update.py 异步调用"""
import json, pathlib, subprocess
_BASE = pathlib.Path(__file__).resolve().parent.parent
TASKS_FILE = _BASE / 'data' / 'tasks_source.json'
DASHBOARD_SCRIPT = _BASE / 'scripts' / 'collaboration_dashboard.py'
# Placeholder: extend with webhook/UI push as needed
if TASKS_FILE.exists():
    data = json.loads(TASKS_FILE.read_text())
    # Can add websocket push, file sync, etc. here
    if DASHBOARD_SCRIPT.exists():
        try:
            subprocess.run(
                ['python3', str(DASHBOARD_SCRIPT), '--quiet'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
        except Exception:
            pass
