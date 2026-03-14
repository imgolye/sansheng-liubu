#!/usr/bin/env python3
"""Switch sansheng-liubu theme for an existing OpenClaw install."""

from __future__ import annotations

import argparse
import json
import subprocess
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from generate_config import load_existing_config, write_config
from render_templates import render_theme
from theme_utils import (
    DEPARTMENT_KEYS,
    ROLE_KEYS,
    get_agent_id_map_by_semantic,
    infer_theme_name_from_config,
    load_theme,
    translate_text_references,
    translate_theme_value,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
THEMES_DIR = PROJECT_DIR / "themes"
TEMPLATES_DIR = PROJECT_DIR / "templates"
RUNTIME_SCRIPTS = (
    "kanban_update.py",
    "file_lock.py",
    "refresh_live_data.py",
    "health_dashboard.py",
    "collaboration_dashboard.py",
)
GENERATED_ROOT_FILES = {"SOUL.md", "HEARTBEAT.md"}
GENERATED_DIRS = {"scripts", "shared-context"}


def semantic_keys():
    return list(ROLE_KEYS) + list(DEPARTMENT_KEYS)


def build_semantic_pairs(old_theme, new_theme):
    old_map = get_agent_id_map_by_semantic(old_theme)
    new_map = get_agent_id_map_by_semantic(new_theme)
    return [(key, old_map[key], new_map[key]) for key in semantic_keys()]


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_installation(openclaw_dir, current_theme_name, target_theme_name):
    backup_dir = openclaw_dir / "backups" / f"theme-switch-{timestamp()}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for filename in ("openclaw.json", ".env"):
        source = openclaw_dir / filename
        if source.exists():
            shutil.copy2(source, backup_dir / filename)

    manifest = {
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "fromTheme": current_theme_name,
        "toTheme": target_theme_name,
    }
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return backup_dir


def ensure_agent_layout(openclaw_dir, theme):
    for agent_id in get_agent_id_map_by_semantic(theme).values():
        workspace = openclaw_dir / f"workspace-{agent_id}"
        for dirname in ("scripts", "data", "shared-context", "skills"):
            (workspace / dirname).mkdir(parents=True, exist_ok=True)
        (openclaw_dir / "agents" / agent_id / "agent").mkdir(parents=True, exist_ok=True)


def deploy_runtime_scripts(openclaw_dir, theme):
    for agent_id in get_agent_id_map_by_semantic(theme).values():
        scripts_dir = openclaw_dir / f"workspace-{agent_id}" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        for script_name in RUNTIME_SCRIPTS:
            shutil.copy2(TEMPLATES_DIR / "scripts" / script_name, scripts_dir / script_name)


def merge_tree(source, target):
    if not source.exists():
        return
    if source.resolve() == target.resolve():
        return
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def translate_path_references(value, old_to_new_agent_ids):
    if not isinstance(value, str) or not value:
        return value
    translated = value
    for old_id, new_id in old_to_new_agent_ids.items():
        translated = translated.replace(f"workspace-{old_id}", f"workspace-{new_id}")
        translated = translated.replace(f"/agents/{old_id}/", f"/agents/{new_id}/")
    return translated


def translate_task(task, old_theme, new_theme, old_to_new_agent_ids):
    translated = deepcopy(task)
    for field in ("official", "org"):
        translated[field] = translate_theme_value(translated.get(field), old_theme, new_theme)
    for field in ("now", "currentUpdate", "block", "blockers", "output"):
        translated[field] = translate_text_references(translated.get(field), old_theme, new_theme)
        translated[field] = translate_path_references(translated.get(field), old_to_new_agent_ids)

    flow_log = []
    for entry in translated.get("flow_log", []):
        new_entry = deepcopy(entry)
        new_entry["from"] = translate_theme_value(new_entry.get("from"), old_theme, new_theme)
        new_entry["to"] = translate_theme_value(new_entry.get("to"), old_theme, new_theme)
        new_entry["remark"] = translate_text_references(new_entry.get("remark"), old_theme, new_theme)
        flow_log.append(new_entry)
    if flow_log:
        translated["flow_log"] = flow_log

    progress_log = []
    for entry in translated.get("progress_log", []):
        new_entry = deepcopy(entry)
        agent_id = new_entry.get("agent")
        if isinstance(agent_id, str) and agent_id in old_to_new_agent_ids:
            new_entry["agent"] = old_to_new_agent_ids[agent_id]
        new_entry["agentLabel"] = translate_theme_value(
            new_entry.get("agentLabel"),
            old_theme,
            new_theme,
        )
        new_entry["org"] = translate_theme_value(new_entry.get("org"), old_theme, new_theme)
        new_entry["text"] = translate_text_references(new_entry.get("text"), old_theme, new_theme)
        progress_log.append(new_entry)
    if progress_log:
        translated["progress_log"] = progress_log

    return translated


def load_tasks(path):
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    return data if isinstance(data, list) else data.get("tasks", [])


def merge_tasks(existing_tasks, incoming_tasks):
    merged = {task.get("id"): deepcopy(task) for task in existing_tasks if isinstance(task, dict)}
    for task in incoming_tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        if not task_id:
            continue
        existing = merged.get(task_id)
        if not existing or str(task.get("updatedAt", "")) >= str(existing.get("updatedAt", "")):
            merged[task_id] = deepcopy(task)
    return sorted(
        merged.values(),
        key=lambda item: str(item.get("updatedAt", "")),
        reverse=True,
    )


def migrate_workspace(old_workspace, new_workspace, old_theme, new_theme, old_to_new_agent_ids):
    if not old_workspace.exists():
        return

    for entry in old_workspace.iterdir():
        if entry.name in GENERATED_ROOT_FILES or entry.name in GENERATED_DIRS:
            continue
        if entry.name == "data":
            continue
        merge_tree(entry, new_workspace / entry.name)

    old_data_dir = old_workspace / "data"
    new_data_dir = new_workspace / "data"
    new_data_dir.mkdir(parents=True, exist_ok=True)

    if old_data_dir.exists():
        for entry in old_data_dir.iterdir():
            if entry.name in {"tasks_source.json", "kanban_config.json"}:
                continue
            merge_tree(entry, new_data_dir / entry.name)

    translated_tasks = [
        translate_task(task, old_theme, new_theme, old_to_new_agent_ids)
        for task in load_tasks(old_data_dir / "tasks_source.json")
    ]
    merged_tasks = merge_tasks(load_tasks(new_data_dir / "tasks_source.json"), translated_tasks)
    (new_data_dir / "tasks_source.json").write_text(
        json.dumps(merged_tasks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def migrate_agent_state(openclaw_dir, old_theme, new_theme):
    pairs = build_semantic_pairs(old_theme, new_theme)
    old_to_new_agent_ids = {old_id: new_id for _, old_id, new_id in pairs}

    for _semantic_key, old_id, new_id in pairs:
        old_agent_root = openclaw_dir / "agents" / old_id
        new_agent_root = openclaw_dir / "agents" / new_id
        if old_agent_root.exists():
            merge_tree(old_agent_root, new_agent_root)

        old_workspace = openclaw_dir / f"workspace-{old_id}"
        new_workspace = openclaw_dir / f"workspace-{new_id}"
        new_workspace.mkdir(parents=True, exist_ok=True)
        migrate_workspace(old_workspace, new_workspace, old_theme, new_theme, old_to_new_agent_ids)


def build_generate_args(openclaw_dir, theme_file, existing_config, task_prefix_override):
    metadata = existing_config.get("sanshengLiubu", {})
    return SimpleNamespace(
        theme=str(theme_file),
        openclaw_dir=str(openclaw_dir),
        primary_model=None,
        light_model=None,
        feishu_app_id=existing_config.get("channels", {}).get("feishu", {}).get("appId", ""),
        feishu_app_secret="",
        tg_bot_token="",
        tg_proxy=existing_config.get("channels", {}).get("telegram", {}).get("proxy"),
        qq_app_id=existing_config.get("channels", {}).get("qqbot", {}).get("appId", ""),
        qq_client_secret="",
        task_prefix=task_prefix_override or metadata.get("taskPrefix"),
        project_dir=metadata.get("projectDir") or str(PROJECT_DIR),
        base_config="",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", required=True, help="Theme directory name, e.g. corporate")
    parser.add_argument("--dir", default=str(Path.home() / ".openclaw"))
    parser.add_argument("--task-prefix", default="")
    args = parser.parse_args()

    openclaw_dir = Path(args.dir).expanduser().resolve()
    config_path = openclaw_dir / "openclaw.json"
    if not config_path.exists():
        raise SystemExit(f"Missing OpenClaw config: {config_path}. Run setup.sh first.")

    theme_file = THEMES_DIR / args.theme / "theme.json"
    if not theme_file.exists():
        raise SystemExit(f"Unknown theme: {args.theme}")

    existing_config = load_existing_config(config_path)
    current_theme_name = infer_theme_name_from_config(existing_config, THEMES_DIR)
    new_theme = load_theme(theme_file)
    old_theme = load_theme(THEMES_DIR / current_theme_name / "theme.json") if current_theme_name else None

    backup_dir = backup_installation(openclaw_dir, current_theme_name, new_theme["name"])
    ensure_agent_layout(openclaw_dir, new_theme)

    if old_theme:
        migrate_agent_state(openclaw_dir, old_theme, new_theme)

    deploy_runtime_scripts(openclaw_dir, new_theme)
    render_theme(
        new_theme,
        openclaw_dir,
        args.task_prefix or existing_config.get("sanshengLiubu", {}).get("taskPrefix") or new_theme.get("task_prefix", "JJC"),
    )

    generate_args = build_generate_args(openclaw_dir, theme_file, existing_config, args.task_prefix)
    write_config(new_theme, generate_args, existing_config=existing_config)

    dashboard_script = openclaw_dir / f"workspace-{get_agent_id_map_by_semantic(new_theme)['router']}" / "scripts" / "collaboration_dashboard.py"
    if dashboard_script.exists():
        subprocess.run(["python3", str(dashboard_script), "--quiet"], check=False)

    print(
        f"Switched theme: {current_theme_name or 'unknown'} -> {new_theme['name']} "
        f"(backup: {backup_dir})"
    )


if __name__ == "__main__":
    main()
