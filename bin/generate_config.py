#!/usr/bin/env python3
"""生成 openclaw.json 配置文件"""

import argparse
import json
import secrets
from pathlib import Path


def load_theme(path):
    with open(path) as f:
        return json.load(f)


def generate_config(theme, args):
    r = theme["roles"]
    router = r["router"]
    planner = r["planner"]
    reviewer = r["reviewer"]
    dispatcher = r["dispatcher"]
    briefing = r["briefing"]
    deps = r["departments"]
    oc_dir = args.openclaw_dir

    # Collect all agent IDs
    all_ids = [
        router["agent_id"], planner["agent_id"], reviewer["agent_id"],
        dispatcher["agent_id"], briefing["agent_id"],
    ] + [d["agent_id"] for d in deps.values()]

    dep_ids = [d["agent_id"] for d in deps.values()]

    def model_for(role_info):
        return args.primary_model if role_info.get("model_tier") == "primary" else args.light_model

    # Build agents list
    agents_list = []

    # Router
    agents_list.append({
        "id": router["agent_id"],
        "default": True,
        "workspace": f"{oc_dir}/workspace-{router['agent_id']}",
        "agentDir": f"{oc_dir}/agents/{router['agent_id']}/agent",
        "model": model_for(router),
        "identity": {"name": router["identity_name"]},
        "heartbeat": {"every": "30m", "target": "none", "lightContext": True,
                       "prompt": "Check for active tasks. If none, reply HEARTBEAT_OK."},
        "subagents": {"allowAgents": [planner["agent_id"], dispatcher["agent_id"],
                                       reviewer["agent_id"], briefing["agent_id"]]},
        "groupChat": {"mentionPatterns": []},
        "tools": {"elevated": {"enabled": True, "allowFrom": {"feishu": ["*"], "telegram": ["*"], "qqbot": ["*"]}}},
    })

    # Planner
    agents_list.append({
        "id": planner["agent_id"],
        "workspace": f"{oc_dir}/workspace-{planner['agent_id']}",
        "agentDir": f"{oc_dir}/agents/{planner['agent_id']}/agent",
        "model": model_for(planner),
        "identity": {"name": planner["identity_name"]},
        "heartbeat": {"every": "30m", "target": "none", "lightContext": True,
                       "prompt": "Check for active tasks (Doing/Assigned/Blocked). If none, reply HEARTBEAT_OK."},
        "subagents": {"allowAgents": [reviewer["agent_id"], dispatcher["agent_id"]]},
    })

    # Reviewer
    agents_list.append({
        "id": reviewer["agent_id"],
        "workspace": f"{oc_dir}/workspace-{reviewer['agent_id']}",
        "agentDir": f"{oc_dir}/agents/{reviewer['agent_id']}/agent",
        "model": model_for(reviewer),
        "identity": {"name": reviewer["identity_name"]},
        "subagents": {"allowAgents": []},
        "tools": {
            "allow": ["Read", "Glob", "Grep", "sessions_history", "sessions_list"],
            "deny": ["Write", "Edit", "NotebookEdit", "Bash"],
            "fs": {"workspaceOnly": True},
        },
        "sandbox": {"mode": "all", "scope": "agent"},
    })

    # Dispatcher
    agents_list.append({
        "id": dispatcher["agent_id"],
        "workspace": f"{oc_dir}/workspace-{dispatcher['agent_id']}",
        "agentDir": f"{oc_dir}/agents/{dispatcher['agent_id']}/agent",
        "model": model_for(dispatcher),
        "identity": {"name": dispatcher["identity_name"]},
        "subagents": {"allowAgents": [planner["agent_id"], reviewer["agent_id"]] + dep_ids},
        "tools": {"elevated": {"enabled": True, "allowFrom": {"feishu": ["*"], "telegram": ["*"], "qqbot": ["*"]}}},
    })

    # Departments
    for dep_key, dep_info in deps.items():
        agent_cfg = {
            "id": dep_info["agent_id"],
            "workspace": f"{oc_dir}/workspace-{dep_info['agent_id']}",
            "agentDir": f"{oc_dir}/agents/{dep_info['agent_id']}/agent",
            "model": model_for(dep_info),
            "identity": {"name": dep_info["identity_name"]},
            "subagents": {"allowAgents": [dispatcher["agent_id"]]},
        }
        if dep_info.get("sandbox", "off") != "off":
            agent_cfg["sandbox"] = {"mode": dep_info["sandbox"], "scope": "agent"}
        if dep_info.get("elevated"):
            agent_cfg["tools"] = {"elevated": {"enabled": True,
                                                "allowFrom": {"feishu": ["*"], "telegram": ["*"], "qqbot": ["*"]}}}
        agents_list.append(agent_cfg)

    # Briefing
    agents_list.append({
        "id": briefing["agent_id"],
        "workspace": f"{oc_dir}/workspace-{briefing['agent_id']}",
        "agentDir": f"{oc_dir}/agents/{briefing['agent_id']}/agent",
        "model": model_for(briefing),
        "identity": {"name": briefing["identity_name"]},
        "subagents": {"allowAgents": [router["agent_id"]]},
        "tools": {
            "deny": ["Write", "Edit", "NotebookEdit"],
            "fs": {"workspaceOnly": True},
        },
        "sandbox": {"mode": "all", "scope": "agent"},
    })

    # Build channels
    channels = {}
    if args.feishu_app_id:
        channels["feishu"] = {
            "enabled": True,
            "appId": args.feishu_app_id,
            "appSecret": "${FEISHU_APP_SECRET}",
            "domain": "feishu",
            "groupPolicy": "allowlist",
            "groupAllowFrom": ["*"],
            "dmPolicy": "pairing",
            "allowFrom": ["*"],
        }
    if args.tg_bot_token:
        tg = {
            "enabled": True,
            "botToken": "${TELEGRAM_BOT_TOKEN}",
            "commands": {"native": True, "nativeSkills": False},
            "dmPolicy": "pairing",
            "allowFrom": ["*"],
            "groupPolicy": "allowlist",
            "streaming": "off",
        }
        if args.tg_proxy:
            tg["proxy"] = args.tg_proxy
        channels["telegram"] = tg
    if args.qq_app_id:
        channels["qqbot"] = {
            "enabled": True,
            "appId": args.qq_app_id,
            "clientSecret": "${QQBOT_CLIENT_SECRET}",
            "allowFrom": ["*"],
        }

    # Full config
    gateway_token = secrets.token_hex(24)
    config = {
        "agents": {
            "defaults": {
                "model": {
                    "primary": args.primary_model,
                    "fallbacks": [args.light_model],
                },
                "workspace": f"{oc_dir}/workspace",
                "memorySearch": {"enabled": True, "provider": "local"},
                "compaction": {"mode": "safeguard"},
                "elevatedDefault": "full",
                "timeoutSeconds": 300,
                "heartbeat": {"every": "30m"},
                "maxConcurrent": 4,
                "subagents": {"maxConcurrent": 8},
            },
            "list": agents_list,
        },
        "tools": {
            "profile": "full",
            "sessions": {"visibility": "tree"},
            "agentToAgent": {"enabled": True, "allow": all_ids},
            "elevated": {"enabled": True, "allowFrom": {"feishu": ["*"], "telegram": ["*"], "qqbot": ["*"]}},
        },
        "session": {
            "dmScope": "per-channel-peer",
            "agentToAgent": {"maxPingPongTurns": 3},
        },
        "channels": channels,
        "gateway": {
            "port": 18789,
            "mode": "local",
            "bind": "loopback",
            "auth": {"mode": "token", "token": "${GATEWAY_AUTH_TOKEN}"},
            "trustedProxies": ["127.0.0.1"],
        },
        "logging": {"redactSensitive": "tools"},
        "plugins": {
            "allow": list(channels.keys()) + ["acpx"],
            "entries": {ch: {"enabled": True} for ch in channels},
        },
    }

    # Write config
    config_path = Path(oc_dir) / "openclaw.json"
    with open(config_path, "w") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"Generated {config_path} with {len(agents_list)} agents")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", required=True)
    parser.add_argument("--openclaw-dir", required=True)
    parser.add_argument("--primary-model", default="openai-codex/gpt-5.4")
    parser.add_argument("--light-model", default="zai/glm-5")
    parser.add_argument("--feishu-app-id", default="")
    parser.add_argument("--feishu-app-secret", default="")
    parser.add_argument("--tg-bot-token", default="")
    parser.add_argument("--tg-proxy", default="")
    parser.add_argument("--qq-app-id", default="")
    parser.add_argument("--qq-client-secret", default="")
    parser.add_argument("--task-prefix", default="JJC")
    args = parser.parse_args()

    theme = load_theme(args.theme)
    generate_config(theme, args)


if __name__ == "__main__":
    main()
