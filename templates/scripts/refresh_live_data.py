#!/usr/bin/env python3
"""刷新看板数据 — 被 kanban_update.py 异步调用"""
import json, pathlib
_BASE = pathlib.Path(__file__).resolve().parent.parent
TASKS_FILE = _BASE / 'data' / 'tasks_source.json'
# Placeholder: extend with webhook/UI push as needed
if TASKS_FILE.exists():
    data = json.loads(TASKS_FILE.read_text())
    # Can add websocket push, file sync, etc. here
