#!/usr/bin/env python3
"""Generate and serve a visual collaboration dashboard for all agents."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import shutil
import subprocess
import time
from collections import Counter, defaultdict, deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import Request, urlopen

from dashboard_store import (
    append_audit_event as store_append_audit_event,
    create_management_run as store_create_management_run,
    create_tenant_api_key as store_create_tenant_api_key,
    delete_product_installation as store_delete_product_installation,
    list_automation_alerts as store_list_automation_alerts,
    list_automation_rules as store_list_automation_rules,
    list_management_runs as store_list_management_runs,
    list_orchestration_workflows as store_list_orchestration_workflows,
    list_notification_channels as store_list_notification_channels,
    list_notification_deliveries as store_list_notification_deliveries,
    list_routing_policies as store_list_routing_policies,
    list_tenant_api_keys as store_list_tenant_api_keys,
    list_tenant_installations as store_list_tenant_installations,
    list_tenants as store_list_tenants,
    load_audit_events as store_load_audit_events,
    load_product_installations as store_load_product_installations,
    load_product_users as store_load_product_users,
    resolve_automation_alerts as store_resolve_automation_alerts,
    resolve_tenant_api_key as store_resolve_tenant_api_key,
    save_product_users as store_save_product_users,
    save_automation_rule as store_save_automation_rule,
    save_notification_channel as store_save_notification_channel,
    save_notification_delivery as store_save_notification_delivery,
    save_orchestration_workflow as store_save_orchestration_workflow,
    save_routing_policy as store_save_routing_policy,
    save_tenant as store_save_tenant,
    save_tenant_installation as store_save_tenant_installation,
    store_path as dashboard_store_path,
    touch_tenant_api_key as store_touch_tenant_api_key,
    upsert_automation_alert as store_upsert_automation_alert,
    update_management_run as store_update_management_run,
    upsert_product_installation as store_upsert_product_installation,
)


TERMINAL_STATES = {"done", "cancelled", "canceled"}
PRODUCT_VERSION = "1.18.0"
OPENCLAW_BASELINE_RELEASE = "2026.3.12"
PASSWORD_HASH_ITERATIONS = 260000
USER_ROLES = {
    "owner": {
        "label": "Owner",
        "description": "管理产品、成员、主题和高风险动作。",
        "permissions": {"read", "task_write", "conversation_write", "theme_write", "admin_write", "audit_view"},
    },
    "operator": {
        "label": "Operator",
        "description": "负责推进任务、维护交付和处理运营现场。",
        "permissions": {"read", "task_write", "conversation_write", "audit_view"},
    },
    "viewer": {
        "label": "Viewer",
        "description": "只读查看现场、交付和协同动态。",
        "permissions": {"read"},
    },
}
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

THEME_CATALOG = {
    "imperial": {
        "displayName": "三省六部",
        "language": "zh-CN",
        "tagline": "层级清晰，适合复杂任务编排",
        "bestFor": "个人玩家、极客、强流程任务",
        "summary": "强调审议、调度和六部协作，适合希望把复杂任务拆成正式流转的人。",
    },
    "corporate": {
        "displayName": "企业组织",
        "language": "en",
        "tagline": "更像 CEO / VP / Team 的现代协同方式",
        "bestFor": "企业团队、正式场景、跨职能配合",
        "summary": "用更贴近公司组织的命名和职责，让多 Agent 协同更容易被业务团队理解。",
    },
    "startup": {
        "displayName": "创业团队",
        "language": "zh-CN",
        "tagline": "扁平直接，适合小团队高速迭代",
        "bestFor": "创业公司、产品开发、小规模团队",
        "summary": "减少流程负担，让 PM、全栈、测试、运营等角色快速接力推进。",
    },
}

SESSION_COOKIE_NAME = "sansheng_dashboard_session"
SESSION_COOKIE_MAX_AGE = 60 * 60 * 12
DEFAULT_FRONTEND_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
}

LOGIN_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mission Control Login</title>
  <link rel="icon" href="data:,">
  <style>
    :root {{
      --bg: {bg};
      --bg2: {bg2};
      --ink: {ink};
      --muted: {muted};
      --accent: {accent};
      --accentStrong: {accentStrong};
      --accentSoft: {accentSoft};
      --line: {line};
      --ok: {ok};
      --danger: {danger};
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; min-height: 100%; }}
    body {{
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 0% 0%, rgba(255,255,255,0.72), transparent 30%),
        radial-gradient(circle at 100% 0%, rgba(255,255,255,0.38), transparent 26%),
        linear-gradient(150deg, var(--bg), var(--bg2));
      padding: 18px;
    }}
    .login-shell {{
      width: min(1180px, 100%);
      min-height: calc(100vh - 36px);
      margin: 0 auto;
      display: grid;
      grid-template-columns: 1.08fr 0.92fr;
      gap: 18px;
      align-items: stretch;
    }}
    .story,
    .auth-card {{
      border-radius: 30px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      box-shadow: 0 24px 60px rgba(57, 40, 28, 0.10);
      overflow: hidden;
    }}
    .story {{
      position: relative;
      padding: 34px;
      background:
        linear-gradient(140deg, rgba(255,255,255,0.78), rgba(255,255,255,0.58)),
        radial-gradient(circle at 100% 0%, color-mix(in srgb, var(--accentSoft) 70%, white 30%), transparent 42%);
    }}
    .story::after {{
      content: "";
      position: absolute;
      right: -80px;
      bottom: -110px;
      width: 280px;
      height: 280px;
      border-radius: 50%;
      background: radial-gradient(circle, color-mix(in srgb, var(--accentSoft) 76%, white 24%), transparent 64%);
      opacity: 0.85;
      pointer-events: none;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      color: var(--accentStrong);
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
      margin: 18px 0 14px;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: clamp(2.1rem, 4vw, 3.2rem);
      line-height: 1.12;
      letter-spacing: -0.02em;
      max-width: none;
    }}
    .lede {{
      max-width: 56ch;
      color: var(--muted);
      line-height: 1.78;
      font-size: 1.04rem;
      margin: 0;
    }}
    .story-grid {{
      margin-top: 24px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .story-card {{
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.96);
      padding: 16px;
    }}
    .story-card span {{
      display: block;
      color: var(--muted);
      font-size: 0.82rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .story-card strong {{
      display: block;
      margin-top: 8px;
      font-size: 1.18rem;
      line-height: 1.4;
    }}
    .story-card p {{
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.65;
      font-size: 0.94rem;
    }}
    .auth-card {{
      padding: 24px;
      display: grid;
      align-content: center;
      gap: 18px;
    }}
    .auth-top {{
      display: grid;
      gap: 8px;
    }}
    .auth-top h2 {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: 1.9rem;
      font-weight: 700;
      line-height: 1.2;
    }}
    .auth-top p,
    .auth-help,
    .auth-meta {{
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }}
    .auth-pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .auth-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.96);
      padding: 8px 12px;
      font-size: 0.84rem;
      font-weight: 700;
      color: var(--accentStrong);
    }}
    form {{
      display: grid;
      gap: 14px;
    }}
    label {{
      display: grid;
      gap: 8px;
      font-size: 0.96rem;
      font-weight: 700;
    }}
    input[type="password"],
    input[type="text"] {{
      width: 100%;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
      color: var(--ink);
      padding: 14px 16px;
      outline: none;
      font: inherit;
    }}
    input[type="password"]:focus,
    input[type="text"]:focus {{
      border-color: color-mix(in srgb, var(--accent) 38%, var(--line));
      box-shadow: 0 0 0 4px rgba(203, 90, 30, 0.10);
    }}
    .button {{
      appearance: none;
      border: 0;
      border-radius: 10px;
      padding: 11px 16px;
      background: var(--accent);
      color: #fffaf3;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      box-shadow: none;
    }}
    .button.secondary {{
      background: rgba(255,255,255,0.96);
      color: var(--ink);
      box-shadow: none;
      border: 1px solid var(--line);
    }}
    .auth-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }}
    .auth-divider {{
      display: flex;
      align-items: center;
      gap: 12px;
      color: var(--muted);
      font-size: 0.82rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .auth-divider::before,
    .auth-divider::after {{
      content: "";
      height: 1px;
      flex: 1;
      background: var(--line);
    }}
    .error {{
      border-radius: 16px;
      border: 1px solid color-mix(in srgb, var(--danger) 28%, var(--line));
      background: rgba(255,255,255,0.78);
      color: var(--danger);
      padding: 12px 14px;
      line-height: 1.6;
      font-size: 0.95rem;
    }}
    .hidden {{ display: none; }}
    @media (max-width: 980px) {{
      .login-shell {{ grid-template-columns: 1fr; }}
      .story-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="login-shell">
    <section class="story">
      <div class="eyebrow">Mission Control</div>
      <h1>先登录，再进入你的多 Agent 产品控制台。</h1>
      <p class="lede">这不是公开页面，而是本地协同中枢。登录后你会进入完整的 Mission Control 应用，查看 Agent 运营、任务交付、活动时间线、主题中心和交付资产。</p>
      <div class="story-grid">
        <article class="story-card">
          <span>Product Surface</span>
          <strong>总览、运营、交付、审计、后台管理</strong>
          <p>它开始具备商业后台应有的账号、权限、审计和操作闭环。</p>
        </article>
        <article class="story-card">
          <span>Secure Local Access</span>
          <strong>团队账号优先，Owner Token 兜底</strong>
          <p>日常使用团队席位登录；Owner Token 只保留给初始化和紧急接管。</p>
        </article>
        <article class="story-card">
          <span>Commercial Readiness</span>
          <strong>角色权限、审计日志、后台治理</strong>
          <p>所有高风险动作都会留下审计线索，成员权限也开始按角色收口。</p>
        </article>
        <article class="story-card">
          <span>Current Context</span>
          <strong>{theme_name} · {owner_title}</strong>
          <p>{theme_summary}</p>
        </article>
      </div>
    </section>

    <section class="auth-card">
      <div class="auth-top">
        <div class="eyebrow">Local Sign-In</div>
        <h2>进入 Mission Control</h2>
        <p>优先使用团队账号登录。Owner Token 仍保留作初始化和紧急接管入口。</p>
      </div>

      <div class="auth-pills">
        <span class="auth-pill">{team_status}</span>
        <span class="auth-pill">{auth_mode}</span>
      </div>

      <div class="error {error_hidden}">{error_message}</div>

      <form method="post" action="/login">
        <input type="hidden" name="next" value="{next_path}">
        <input type="hidden" name="mode" value="password">
        <label>
          用户名
          <input type="text" name="username" autocomplete="username" placeholder="例如 owner / alice@company">
        </label>
        <label>
          密码
          <input type="password" name="password" autocomplete="current-password" placeholder="输入团队账号密码">
        </label>
        <div class="auth-actions">
          <button class="button" type="submit">团队登录</button>
          <a class="button secondary" href="https://github.com/imgolye/sansheng-liubu/releases/latest">查看版本说明</a>
        </div>
      </form>

      <div class="auth-divider">Owner Fallback</div>

      <form method="post" action="/login">
        <input type="hidden" name="next" value="{next_path}">
        <input type="hidden" name="mode" value="token">
        <label>
          Owner Token
          <input type="password" name="token" autocomplete="current-password" placeholder="输入本地 dashboard token">
        </label>
        <div class="auth-actions">
          <button class="button secondary" type="submit">使用 Token 进入</button>
        </div>
      </form>

      <p class="auth-help">{bootstrap_help}</p>
      <p class="auth-meta">登录后会创建本地会话 cookie，仅用于当前 Mission Control 页面与 API 访问。</p>
      <p class="auth-meta">如需单独管理兜底令牌，可在 `{openclaw_dir}/.env` 中设置 `DASHBOARD_AUTH_TOKEN`；未设置时默认回落到 `GATEWAY_AUTH_TOKEN`。</p>
    </section>
  </div>
</body>
</html>
"""


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Mission Control</title>
  <link rel="icon" href="data:,">
  <style>
    :root {
__STYLE_VARS__
      --shadow: 0 14px 32px rgba(15, 23, 42, 0.08);
      --shadow-soft: 0 6px 18px rgba(15, 23, 42, 0.06);
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; }
    body {
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        linear-gradient(180deg, color-mix(in srgb, var(--bg2) 88%, white 12%), color-mix(in srgb, var(--bg) 92%, white 8%));
    }
    button, input, textarea, select { font: inherit; }
    .shell {
      width: min(1480px, calc(100vw - 28px));
      margin: 18px auto 40px;
      display: grid;
      gap: 18px;
    }
    .hero {
      position: relative;
      overflow: hidden;
      padding: 24px;
      border-radius: 20px;
      border: 1px solid var(--line);
      background:
        linear-gradient(180deg, color-mix(in srgb, var(--panel) 94%, white 6%), rgba(255,255,255,0.96));
      box-shadow: var(--shadow);
    }
    .hero::after {
      content: "";
      position: absolute;
      right: -72px;
      top: -96px;
      width: 220px;
      height: 220px;
      border-radius: 50%;
      background: radial-gradient(circle, color-mix(in srgb, var(--accentSoft) 42%, white 58%), transparent 68%);
      opacity: 0.55;
      pointer-events: none;
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      color: var(--accentStrong);
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      font-weight: 700;
    }
    .eyebrow::before {
      content: "";
      width: 40px;
      height: 1px;
      background: currentColor;
      opacity: 0.75;
    }
    h1 {
      margin: 10px 0 10px;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: clamp(1.9rem, 3.2vw, 2.8rem);
      line-height: 1.15;
      letter-spacing: -0.02em;
      max-width: none;
    }
    .lede {
      max-width: 76ch;
      margin: 0 0 20px;
      line-height: 1.72;
      color: var(--muted);
      font-size: clamp(1rem, 1.5vw, 1.16rem);
    }
    .hero-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 10px 18px;
      color: var(--muted);
      font-size: 0.95rem;
    }
    .hero-tools {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      margin-top: 20px;
    }
    .button {
      appearance: none;
      border: 0;
      border-radius: 10px;
      padding: 10px 14px;
      background: var(--accent);
      color: #fffaf3;
      font-weight: 600;
      cursor: pointer;
      box-shadow: none;
      transition: transform 140ms ease-out, border-color 140ms ease-out, background 140ms ease-out;
      text-decoration: none;
    }
    .button:hover { transform: translateY(-1px); }
    .button.secondary {
      background: rgba(255,255,255,0.94);
      color: var(--ink);
      box-shadow: none;
      border: 1px solid var(--line);
    }
    .button:disabled {
      opacity: 0.58;
      cursor: wait;
      transform: none;
    }
    .toast-stack {
      position: fixed;
      right: 16px;
      bottom: 16px;
      z-index: 120;
      display: grid;
      gap: 10px;
      width: min(360px, calc(100vw - 24px));
      pointer-events: none;
    }
    .toast {
      border-radius: 20px;
      border: 1px solid var(--line);
      background: color-mix(in srgb, var(--panel) 86%, white 14%);
      box-shadow: 0 18px 38px rgba(70, 44, 28, 0.12);
      padding: 14px 16px;
      display: grid;
      gap: 6px;
      transform: translateY(0);
      transition: opacity 180ms ease-out, transform 180ms ease-out;
      pointer-events: auto;
    }
    .toast[data-hiding="true"] {
      opacity: 0;
      transform: translateY(8px);
    }
    .toast strong {
      font-size: 0.95rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .toast p {
      margin: 0;
      line-height: 1.6;
      color: var(--muted);
    }
    .toast[data-tone="success"] strong { color: var(--ok); }
    .toast[data-tone="warn"] strong { color: var(--warn); }
    .toast[data-tone="error"] strong { color: var(--danger); }
    .studio-grid,
    .drawer-action-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .studio-card {
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.96);
      padding: 16px;
      display: grid;
      gap: 12px;
      align-content: start;
    }
    .studio-eyebrow {
      color: var(--accentStrong);
      font-size: 0.78rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      font-weight: 700;
    }
    .studio-copy,
    .field-hint,
    .status-inline,
    .selection-meta {
      color: var(--muted);
      line-height: 1.6;
    }
    .studio-copy {
      font-size: 0.94rem;
    }
    .studio-form {
      display: grid;
      gap: 12px;
    }
    .form-field {
      display: grid;
      gap: 8px;
    }
    .field-label {
      font-size: 0.92rem;
      font-weight: 700;
    }
    .field-hint {
      font-size: 0.84rem;
    }
    .text-input,
    .text-area {
      width: 100%;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
      color: var(--ink);
      padding: 12px 14px;
      outline: none;
      box-shadow: none;
      transition: border-color 140ms ease-out, box-shadow 140ms ease-out, background 140ms ease-out;
    }
    .text-area {
      resize: vertical;
      min-height: 110px;
    }
    .text-input:focus,
    .text-area:focus {
      border-color: color-mix(in srgb, var(--accent) 30%, var(--line));
      box-shadow: 0 0 0 4px rgba(203, 90, 30, 0.08);
    }
    .check-row {
      display: flex;
      gap: 10px;
      align-items: flex-start;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.55;
    }
    .check-row input {
      margin-top: 3px;
      accent-color: var(--accent);
    }
    .action-footer {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }
    .status-inline {
      min-height: 1.6em;
      font-size: 0.9rem;
    }
    .selection-card {
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
      padding: 18px;
      display: grid;
      gap: 12px;
    }
    .selection-title {
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: 1.22rem;
      line-height: 1.3;
      font-weight: 700;
    }
    .selection-stats {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .selection-stat {
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      padding: 12px;
    }
    .selection-stat span {
      display: block;
      color: var(--muted);
      font-size: 0.76rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-weight: 700;
    }
    .selection-stat strong {
      display: block;
      margin-top: 5px;
      font-size: 1.02rem;
    }
    .theme-card-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .operations-view {
      display: grid;
      gap: 18px;
    }
    .workspace-hero {
      position: relative;
      overflow: hidden;
      border-radius: 18px;
      border: 1px solid var(--line);
      background:
        linear-gradient(180deg, rgba(255,255,255,0.98), rgba(255,255,255,0.94));
      box-shadow: var(--shadow-soft);
      padding: 22px;
      display: grid;
      gap: 20px;
    }
    .workspace-hero::after {
      content: "";
      position: absolute;
      right: -72px;
      bottom: -110px;
      width: 180px;
      height: 180px;
      border-radius: 50%;
      background: radial-gradient(circle, color-mix(in srgb, var(--accentSoft) 28%, white 72%), transparent 68%);
      opacity: 0.38;
      pointer-events: none;
    }
    .workspace-hero-head {
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(290px, 0.85fr);
      gap: 18px;
      align-items: end;
    }
    .workspace-hero-title {
      margin: 8px 0 6px;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: clamp(1.7rem, 2.8vw, 2.3rem);
      font-weight: 700;
      line-height: 1.22;
      letter-spacing: -0.02em;
      max-width: none;
    }
    .workspace-hero-copy {
      max-width: 60ch;
      color: var(--muted);
      line-height: 1.74;
      font-size: 0.98rem;
      margin: 0;
    }
    .workspace-note-card {
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
      padding: 18px;
      display: grid;
      gap: 8px;
      box-shadow: none;
      justify-self: end;
      width: min(100%, 340px);
    }
    .workspace-note-card span,
    .workspace-kpi-card span {
      color: var(--muted);
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-weight: 700;
    }
    .workspace-note-card strong {
      font-size: 1.14rem;
      line-height: 1.42;
    }
    .workspace-note-card p,
    .workspace-kpi-card p {
      margin: 0;
      color: var(--muted);
      line-height: 1.62;
      font-size: 0.93rem;
    }
    .workspace-kpi-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }
    .workspace-kpi-card {
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
      padding: 18px;
      display: grid;
      gap: 10px;
      min-height: 148px;
    }
    .workspace-kpi-card strong {
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: clamp(1.2rem, 1.8vw, 1.6rem);
      font-weight: 700;
      line-height: 1.28;
    }
    .workspace-kpi-meta {
      color: var(--ink);
      font-size: 0.9rem;
      line-height: 1.58;
      padding-top: 3px;
      border-top: 1px solid rgba(98, 63, 49, 0.08);
      white-space: pre-wrap;
      word-break: break-word;
    }
    .workspace-split {
      display: grid;
      grid-template-columns: minmax(0, 1.16fr) minmax(320px, 0.84fr);
      gap: 18px;
      align-items: start;
    }
    .workspace-panel .panel-head {
      padding: 20px 22px 14px;
    }
    .workspace-panel .panel-title {
      font-size: 1.34rem;
    }
    .panel-body {
      padding: 18px 20px 20px;
    }
    .admin-view {
      display: grid;
      gap: 18px;
    }
    .admin-hero {
      position: relative;
      overflow: hidden;
      border-radius: 18px;
      border: 1px solid var(--line);
      background:
        linear-gradient(180deg, rgba(255,255,255,0.98), rgba(255,255,255,0.94));
      box-shadow: var(--shadow-soft);
      padding: 22px;
      display: grid;
      gap: 22px;
    }
    .admin-hero::after {
      content: "";
      position: absolute;
      right: -86px;
      bottom: -110px;
      width: 180px;
      height: 180px;
      border-radius: 50%;
      background: radial-gradient(circle, color-mix(in srgb, var(--accentSoft) 26%, white 74%), transparent 68%);
      opacity: 0.36;
      pointer-events: none;
    }
    .admin-hero-head {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(300px, 0.8fr);
      gap: 20px;
      align-items: end;
    }
    .admin-hero-title {
      margin: 8px 0 6px;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: clamp(1.8rem, 3vw, 2.5rem);
      font-weight: 700;
      line-height: 1.2;
      letter-spacing: -0.02em;
      max-width: none;
    }
    .admin-hero-copy {
      max-width: 60ch;
      color: var(--muted);
      line-height: 1.76;
      font-size: 1rem;
    }
    .admin-hero-side {
      display: grid;
      gap: 12px;
      justify-items: end;
      align-content: end;
    }
    .admin-chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: flex-end;
    }
    .admin-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.76);
      color: var(--accentStrong);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-weight: 700;
    }
    .admin-note-card {
      width: min(100%, 340px);
      border-radius: 24px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.76);
      padding: 18px;
      display: grid;
      gap: 8px;
      box-shadow: 0 18px 38px rgba(67, 47, 31, 0.08);
    }
    .admin-note-card span,
    .admin-kpi-card span,
    .admin-mini-stat span {
      color: var(--muted);
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-weight: 700;
    }
    .admin-note-card strong {
      font-size: 1.12rem;
      line-height: 1.42;
    }
    .admin-note-card p {
      margin: 0;
      color: var(--muted);
      line-height: 1.65;
      font-size: 0.92rem;
    }
    .admin-kpi-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }
    .admin-kpi-card {
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
      padding: 18px;
      display: grid;
      gap: 10px;
      min-height: 154px;
    }
    .admin-kpi-card strong {
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: 1.4rem;
      font-weight: 700;
      line-height: 1.28;
    }
    .admin-kpi-card p,
    .admin-kpi-meta,
    .admin-role-card p,
    .admin-instance-card p,
    .admin-user-card p {
      margin: 0;
      color: var(--muted);
      line-height: 1.62;
      font-size: 0.94rem;
    }
    .admin-kpi-meta {
      padding-top: 2px;
      border-top: 1px solid rgba(98, 63, 49, 0.08);
      white-space: pre-wrap;
      word-break: break-word;
    }
    .admin-operations-grid,
    .admin-team-grid {
      display: grid;
      gap: 18px;
      align-items: start;
    }
    .admin-operations-grid {
      grid-template-columns: minmax(0, 1.32fr) minmax(320px, 0.92fr);
    }
    .admin-team-grid {
      grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
    }
    .admin-side-stack,
    .admin-studio-stack {
      display: grid;
      gap: 18px;
    }
    .admin-panel .panel-head {
      padding: 20px 22px 14px;
    }
    .admin-panel .panel-title {
      font-size: 1.34rem;
    }
    .admin-panel .admin-role-grid,
    .admin-panel .admin-fleet-grid,
    .admin-panel .admin-seat-list,
    .admin-panel .admin-studio-grid {
      padding: 18px 20px 20px;
    }
    .admin-role-grid,
    .admin-seat-list,
    .admin-fleet-grid {
      display: grid;
      gap: 14px;
    }
    .admin-fleet-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .admin-role-card,
    .admin-instance-card,
    .admin-user-card {
      border-radius: 22px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      padding: 18px;
      display: grid;
      gap: 12px;
    }
    .admin-role-card {
      background:
        linear-gradient(180deg, rgba(255,255,255,0.78), rgba(255,255,255,0.64)),
        radial-gradient(circle at 100% 0%, rgba(255,255,255,0.56), transparent 48%);
    }
    .admin-instance-card {
      background:
        linear-gradient(180deg, rgba(255,255,255,0.82), rgba(255,255,255,0.64)),
        radial-gradient(circle at 100% 0%, color-mix(in srgb, var(--accentSoft) 50%, white 50%), transparent 48%);
    }
    .admin-instance-path {
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.78);
      font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
      font-size: 0.83rem;
      line-height: 1.58;
      white-space: pre-wrap;
      word-break: break-all;
    }
    .admin-instance-facts {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .admin-mini-stat {
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.82);
      padding: 12px;
      display: grid;
      gap: 5px;
    }
    .admin-mini-stat strong {
      font-size: 1.02rem;
      line-height: 1.24;
    }
    .admin-section-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .admin-user-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(220px, 0.9fr);
      gap: 12px;
      align-items: start;
    }
    .admin-user-grid .admin-section-meta {
      align-content: start;
      justify-content: flex-start;
    }
    .admin-user-card .theme-badge {
      justify-self: start;
    }
    .admin-audit-panel .event-feed {
      padding: 20px 24px 24px 34px;
    }
    .admin-audit-panel .event-feed::before {
      left: 34px;
      top: 20px;
      bottom: 20px;
    }
    .admin-audit-event {
      background: rgba(255,255,255,0.66);
      border-radius: 18px;
      border: 1px solid var(--line);
      padding: 16px 16px 16px 22px;
    }
    .live-indicator {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      color: var(--muted);
      font-size: 0.94rem;
      min-height: 24px;
    }
    .live-indicator::before {
      content: "";
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: currentColor;
      box-shadow: 0 0 0 0 currentColor;
      animation: pulse 2.2s infinite;
    }
    .live-indicator[data-tone="live"] { color: var(--ok); }
    .live-indicator[data-tone="warn"] { color: var(--warn); }
    .live-indicator[data-tone="idle"] { color: var(--muted); }
    .live-indicator[data-tone="paused"] { color: var(--accentStrong); }
    .metric-grid,
    .relay-grid,
    .agent-grid,
    .task-list,
    .event-feed,
    .drawer-list,
    .drawer-flow {
      display: grid;
      gap: 14px;
    }
    .metric-grid {
      grid-template-columns: repeat(6, minmax(0, 1fr));
      margin-top: 24px;
    }
    .metric {
      min-height: 116px;
      padding: 16px 16px 18px;
      border-radius: 14px;
      background: rgba(255,255,255,0.98);
      border: 1px solid var(--line);
    }
    .metric-label {
      color: var(--muted);
      font-size: 0.82rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-weight: 700;
    }
    .metric-value {
      margin-top: 8px;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: clamp(1.55rem, 2vw, 2.15rem);
      font-weight: 700;
      line-height: 1.24;
    }
    .metric-note {
      margin-top: 6px;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.55;
    }
    .panel {
      overflow: hidden;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.96);
      box-shadow: var(--shadow-soft);
    }
    .panel-head {
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 12px;
      padding: 22px 24px 12px;
      border-bottom: 1px solid var(--line);
    }
    .panel-title {
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: 1.18rem;
      font-weight: 700;
      line-height: 1.3;
    }
    .panel-subtitle {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 0.94rem;
      line-height: 1.55;
    }
    .relay-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
      padding: 18px 20px 22px;
    }
    .relay {
      padding: 16px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
    }
    .relay-path {
      font-weight: 700;
      line-height: 1.45;
    }
    .relay-count {
      margin-top: 8px;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: 1.5rem;
      font-weight: 700;
      line-height: 1.2;
    }
    .relay-meta {
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.92rem;
    }
    .main-grid {
      display: grid;
      grid-template-columns: 1.18fr 1.32fr 1fr;
      gap: 18px;
      align-items: start;
    }
    .agent-grid,
    .task-list {
      padding: 18px;
    }
    .event-feed {
      padding: 18px 18px 20px 26px;
      position: relative;
    }
    .event-feed::before {
      content: "";
      position: absolute;
      left: 26px;
      top: 18px;
      bottom: 18px;
      width: 1px;
      background: var(--line);
    }
    .click-card {
      cursor: pointer;
      transition: transform 150ms ease-out, border-color 150ms ease-out, box-shadow 150ms ease-out;
    }
    .click-card:hover {
      transform: translateY(-2px);
      border-color: color-mix(in srgb, var(--accent) 25%, var(--line));
      box-shadow: 0 12px 28px rgba(48, 36, 28, 0.08);
    }
    .agent-card,
    .task-card {
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
      padding: 16px;
      display: grid;
      gap: 12px;
    }
    .agent-head,
    .task-head,
    .event-head {
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 12px;
    }
    .agent-title,
    .task-title,
    .event-title {
      font-weight: 700;
      line-height: 1.42;
    }
    .agent-title { font-size: 1.06rem; }
    .task-title { font-size: 1.08rem; }
    .agent-meta,
    .task-sub,
    .event-meta,
    .event-detail,
    .drawer-muted,
    .drawer-subtle {
      color: var(--muted);
    }
    .agent-meta,
    .task-sub,
    .event-meta {
      font-size: 0.92rem;
      line-height: 1.55;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 12px;
      border-radius: 10px;
      font-size: 0.82rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      white-space: nowrap;
    }
    .status-pill::before {
      content: "";
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: currentColor;
    }
    .status-active { color: var(--ok); background: rgba(47, 107, 72, 0.08); }
    .status-waiting { color: var(--warn); background: rgba(177, 107, 29, 0.09); }
    .status-blocked { color: var(--danger); background: rgba(146, 45, 32, 0.09); }
    .status-standby { color: var(--accentStrong); background: rgba(163, 65, 40, 0.08); }
    .status-idle { color: var(--muted); background: rgba(103, 96, 89, 0.09); }
    .agent-facts {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .fact {
      padding: 12px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
    }
    .fact span {
      display: block;
      color: var(--muted);
      font-size: 0.8rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .fact strong {
      display: block;
      margin-top: 4px;
      font-size: 1.16rem;
    }
    .focus {
      color: var(--ink);
      line-height: 1.65;
    }
    .pill-row,
    .route,
    .drawer-chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .pill,
    .route-step,
    .drawer-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.96);
      color: var(--ink);
      font-size: 0.86rem;
      line-height: 1.4;
    }
    .route-step:not(:last-child)::after {
      content: "→";
      color: var(--accent);
      margin-left: 2px;
    }
    .progress-track {
      width: 100%;
      height: 10px;
      border-radius: 999px;
      background: rgba(64, 52, 44, 0.08);
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), var(--accentSoft));
      transition: width 220ms ease-out;
    }
    .conversation-shell {
      display: grid;
      grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.4fr);
      gap: 18px;
      align-items: start;
    }
    .conversation-list,
    .transcript-stream {
      padding: 18px;
      display: grid;
      gap: 12px;
    }
    .conversation-card {
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
      padding: 16px;
      display: grid;
      gap: 10px;
      cursor: pointer;
      transition: transform 150ms ease-out, border-color 150ms ease-out, box-shadow 150ms ease-out;
    }
    .conversation-card:hover,
    .conversation-card[data-active="true"] {
      transform: translateY(-2px);
      border-color: color-mix(in srgb, var(--accent) 28%, var(--line));
      box-shadow: 0 16px 34px rgba(48, 36, 28, 0.09);
    }
    .conversation-card[data-active="true"] {
      background: color-mix(in srgb, var(--accentSoft) 16%, rgba(255,255,255,0.98));
    }
    .agent-card-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }
    .agent-launch-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 12px;
    }
    .agent-launch-card {
      appearance: none;
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px 15px;
      background: rgba(255,255,255,0.98);
      display: grid;
      gap: 8px;
      text-align: left;
      color: var(--ink);
      cursor: pointer;
      transition: transform 150ms ease-out, border-color 150ms ease-out, box-shadow 150ms ease-out;
    }
    .agent-launch-card:hover,
    .agent-launch-card[data-active="true"] {
      transform: translateY(-2px);
      border-color: color-mix(in srgb, var(--accent) 28%, var(--line));
      box-shadow: 0 16px 34px rgba(48, 36, 28, 0.09);
    }
    .agent-launch-card[data-active="true"] {
      background: color-mix(in srgb, var(--accentSoft) 18%, rgba(255,255,255,0.98));
    }
    .agent-launch-card strong {
      font-size: 1rem;
      line-height: 1.3;
    }
    .agent-launch-card span {
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.55;
    }
    .agent-launch-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      color: var(--muted);
      font-size: 0.82rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .conversation-preview {
      color: var(--ink);
      line-height: 1.62;
      display: -webkit-box;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 3;
      overflow: hidden;
    }
    .transcript-stream {
      min-height: 420px;
      max-height: min(72vh, 920px);
      overflow: auto;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.6), rgba(255,255,255,0.42)),
        radial-gradient(circle at top right, color-mix(in srgb, var(--accentSoft) 38%, transparent), transparent 44%);
    }
    .transcript-message {
      display: grid;
      gap: 8px;
      justify-items: start;
    }
    .transcript-message[data-kind="assistant"] {
      justify-items: end;
    }
    .transcript-meta {
      font-size: 0.82rem;
      color: var(--muted);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .transcript-bubble {
      max-width: min(86%, 760px);
      border-radius: 22px;
      padding: 14px 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.76);
      line-height: 1.68;
      white-space: pre-wrap;
      word-break: break-word;
      box-shadow: 0 12px 24px rgba(32, 22, 16, 0.04);
    }
    .transcript-message[data-kind="assistant"] .transcript-bubble {
      background: color-mix(in srgb, var(--accentSoft) 34%, rgba(255,255,255,0.78));
      border-color: color-mix(in srgb, var(--accent) 18%, var(--line));
    }
    .transcript-message[data-kind="tool_call"] .transcript-bubble,
    .transcript-message[data-kind="tool_result"] .transcript-bubble {
      background: rgba(255,255,255,0.58);
      border-style: dashed;
    }
    .transcript-message[data-kind="tool_result"][data-error="true"] .transcript-bubble {
      border-color: color-mix(in srgb, var(--danger) 38%, var(--line));
      background: color-mix(in srgb, var(--danger) 8%, rgba(255,255,255,0.68));
    }
    .transcript-summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .transcript-stat {
      padding: 12px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.6);
    }
    .transcript-stat span {
      display: block;
      color: var(--muted);
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .transcript-stat strong {
      display: block;
      margin-top: 4px;
      font-size: 1rem;
    }
    .task-copy {
      line-height: 1.65;
    }
    .task-copy strong,
    .drawer-section h3 {
      display: block;
      margin: 0 0 8px;
      font-size: 0.86rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .todo-row {
      display: flex;
      gap: 12px;
      align-items: center;
      color: var(--muted);
      font-size: 0.92rem;
    }
    .event {
      position: relative;
      padding-left: 24px;
      cursor: pointer;
      transition: transform 150ms ease-out;
    }
    .event:hover { transform: translateX(2px); }
    .event::before {
      content: "";
      position: absolute;
      left: -5px;
      top: 7px;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 0 5px rgba(255,255,255,0.7);
    }
    .event-progress::before { background: var(--ok); }
    .event-detail {
      margin-top: 5px;
      line-height: 1.6;
    }
    .empty {
      color: var(--muted);
      line-height: 1.7;
      padding: 10px 0 4px;
    }
    .scrim {
      position: fixed;
      inset: 0;
      background: rgba(37, 27, 21, 0.28);
      backdrop-filter: blur(6px);
      z-index: 40;
      pointer-events: none;
    }
    .drawer {
      position: fixed;
      top: 14px;
      right: 14px;
      bottom: 14px;
      width: min(520px, calc(100vw - 28px));
      z-index: 50;
      pointer-events: none;
      transform: translateX(24px);
      opacity: 0;
      transition: transform 180ms ease-out, opacity 180ms ease-out;
    }
    .drawer[data-open="true"] {
      transform: translateX(0);
      opacity: 1;
      pointer-events: auto;
    }
    .drawer-shell {
      height: 100%;
      display: grid;
      grid-template-rows: auto 1fr;
      border-radius: 28px;
      border: 1px solid var(--line);
      background: color-mix(in srgb, var(--panel) 92%, white 8%);
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .drawer-head {
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 16px;
      padding: 22px 22px 14px;
      border-bottom: 1px solid var(--line);
    }
    .drawer-kicker {
      color: var(--accentStrong);
      font-size: 0.82rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      font-weight: 700;
    }
    .drawer-title {
      margin: 10px 0 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: 1.5rem;
      font-weight: 700;
      line-height: 1.2;
    }
    .drawer-body {
      overflow: auto;
      padding: 18px 22px 26px;
      display: grid;
      gap: 18px;
    }
    .drawer-close {
      appearance: none;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      border-radius: 999px;
      padding: 9px 12px;
      cursor: pointer;
    }
    .drawer-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .drawer-chip.strong {
      background: color-mix(in srgb, var(--accentSoft) 52%, white 48%);
      border-color: color-mix(in srgb, var(--accent) 18%, var(--line));
    }
    .drawer-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .drawer-stat {
      padding: 12px;
      border-radius: 16px;
      background: rgba(255,255,255,0.64);
      border: 1px solid var(--line);
    }
    .drawer-stat span {
      display: block;
      color: var(--muted);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .drawer-stat strong {
      display: block;
      margin-top: 4px;
      font-size: 1.08rem;
    }
    .drawer-section {
      padding: 16px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.56);
      display: grid;
      gap: 10px;
    }
    .drawer-list-item,
    .drawer-flow-item {
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.66);
      padding: 12px;
      display: grid;
      gap: 6px;
    }
    .drawer-item-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
    }
    .drawer-item-title {
      font-weight: 700;
      line-height: 1.45;
    }
    .drawer-item-meta {
      font-size: 0.85rem;
      color: var(--muted);
      white-space: nowrap;
    }
    .drawer-item-detail {
      color: var(--muted);
      line-height: 1.6;
      font-size: 0.95rem;
    }
    .drawer-link {
      appearance: none;
      border: 0;
      background: none;
      padding: 0;
      color: inherit;
      text-align: left;
      cursor: pointer;
      font: inherit;
    }
    .todo-list {
      display: grid;
      gap: 8px;
    }
    .todo-item {
      display: flex;
      align-items: center;
      gap: 10px;
      border-radius: 14px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.64);
    }
    .todo-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--muted);
      flex: 0 0 auto;
    }
    .todo-completed .todo-dot { background: var(--ok); }
    .todo-in-progress .todo-dot { background: var(--warn); }
    .todo-label {
      flex: 1;
      line-height: 1.5;
    }
    .todo-status {
      font-size: 0.84rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .app-shell {
      width: min(1780px, calc(100vw - 32px));
      margin: 16px auto 32px;
      display: grid;
      grid-template-columns: 292px minmax(0, 1fr);
      gap: 20px;
      align-items: start;
    }
    .rail {
      position: sticky;
      top: 16px;
      display: grid;
      gap: 12px;
      align-self: start;
    }
    .brand-card,
    .rail-panel,
    .topbar {
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.96);
      box-shadow: var(--shadow-soft);
    }
    .brand-card,
    .rail-panel {
      padding: 18px;
    }
    .brand-card {
      background: rgba(255,255,255,0.98);
    }
    .brand-card h2 {
      margin: 10px 0 6px;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: 1.5rem;
      font-weight: 700;
      line-height: 1.22;
    }
    .rail-copy,
    .topbar-subtitle,
    .rail-muted,
    .status-note,
    .path-line,
    .command-desc {
      color: var(--muted);
      line-height: 1.65;
    }
    .rail-label,
    .topbar-kicker {
      color: var(--accentStrong);
      font-size: 0.78rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      font-weight: 700;
    }
    .nav-stack {
      display: grid;
      gap: 8px;
    }
    .nav-link {
      appearance: none;
      width: 100%;
      text-align: left;
      border: 1px solid transparent;
      border-radius: 10px;
      background: transparent;
      padding: 10px 12px;
      color: var(--ink);
      cursor: pointer;
      font-weight: 600;
      transition: transform 140ms ease-out, border-color 140ms ease-out, background 140ms ease-out;
    }
    .nav-link span {
      display: block;
      margin-top: 5px;
      color: var(--muted);
      font-size: 0.84rem;
      font-weight: 500;
      line-height: 1.48;
    }
    .nav-link:hover {
      transform: translateY(-1px);
      background: rgba(0,0,0,0.02);
      border-color: var(--line);
    }
    .nav-link[data-active="true"] {
      background:
        linear-gradient(180deg, color-mix(in srgb, var(--accentSoft) 18%, white 82%), rgba(255,255,255,0.98));
      border-color: color-mix(in srgb, var(--accent) 28%, var(--line));
      box-shadow: inset 2px 0 0 color-mix(in srgb, var(--accent) 72%, white 28%);
    }
    .rail-grid,
    .status-strip,
    .command-list,
    .deliverable-list,
    .theme-grid {
      display: grid;
      gap: 12px;
    }
    .rail-grid {
      grid-template-columns: 1fr;
    }
    .rail-kv {
      padding: 12px 13px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
    }
    .rail-kv strong,
    .status-card strong {
      display: block;
      margin-top: 6px;
      font-size: 1rem;
      font-weight: 700;
    }
    .workspace-shell {
      min-width: 0;
      display: grid;
      gap: 18px;
    }
    .topbar {
      padding: 18px 22px;
      display: grid;
      grid-template-columns: auto minmax(260px, 1fr) auto;
      gap: 16px;
      align-items: center;
    }
    .topbar-title {
      margin-top: 6px;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      font-size: 1.8rem;
      font-weight: 700;
      line-height: 1.16;
    }
    .search-shell {
      display: flex;
      align-items: center;
    }
    .search-input {
      width: 100%;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
      color: var(--ink);
      padding: 13px 18px;
      outline: none;
      box-shadow: none;
    }
    .search-input:focus {
      border-color: color-mix(in srgb, var(--accent) 34%, var(--line));
      box-shadow: 0 0 0 4px rgba(203, 90, 30, 0.08);
    }
    .view-stack,
    .overview-grid {
      display: grid;
      gap: 18px;
    }
    .overview-grid {
      grid-template-columns: 1.12fr 1.12fr 0.96fr;
      align-items: start;
    }
    .split-grid {
      display: grid;
      grid-template-columns: 1.25fr 0.95fr;
      gap: 18px;
      align-items: start;
    }
    .view[hidden] {
      display: none !important;
    }
    .status-strip {
      grid-template-columns: repeat(5, minmax(0, 1fr));
    }
    .status-card,
    .deliverable-card,
    .theme-card,
    .command-card {
      padding: 16px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
    }
    .status-card {
      min-height: 112px;
    }
    .status-card span {
      color: var(--muted);
      font-size: 0.8rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      font-weight: 700;
    }
    .status-note {
      margin-top: 8px;
      font-size: 0.9rem;
    }
    .filter-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .filter-chip {
      appearance: none;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: rgba(255,255,255,0.94);
      color: var(--ink);
      padding: 8px 12px;
      font-weight: 600;
      cursor: pointer;
    }
    .filter-chip[data-active="true"] {
      background: color-mix(in srgb, var(--accentSoft) 32%, white 68%);
      border-color: color-mix(in srgb, var(--accent) 28%, var(--line));
    }
    .deliverable-card,
    .theme-card,
    .command-card {
      display: grid;
      gap: 10px;
    }
    .deliverable-head,
    .theme-head {
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 12px;
    }
    .deliverable-title,
    .theme-title {
      font-weight: 700;
      font-size: 1.04rem;
      line-height: 1.42;
    }
    .list-meta {
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.55;
    }
    .path-line,
    .code-line {
      padding: 12px 14px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.98);
      font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
      font-size: 0.84rem;
      white-space: pre-wrap;
      word-break: break-all;
    }
    .theme-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 11px;
      border-radius: 10px;
      border: 1px solid var(--line);
      font-size: 0.8rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      background: rgba(255,255,255,0.96);
    }
    .theme-card[data-current="true"] {
      border-color: color-mix(in srgb, var(--accent) 28%, var(--line));
      box-shadow: 0 14px 30px rgba(70, 44, 28, 0.08);
    }
    .panel-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .topbar-tools {
      display: flex;
      flex-wrap: wrap;
      justify-content: end;
      gap: 10px;
      align-items: center;
    }
    .layout-row,
    .auth-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .auth-row form {
      display: inline-flex;
      gap: 0;
    }
    .button.small {
      padding: 10px 14px;
      font-size: 0.92rem;
    }
    .app-shell[data-rail="collapsed"] {
      grid-template-columns: 108px minmax(0, 1fr);
    }
    .app-shell[data-rail="collapsed"] .rail-copy,
    .app-shell[data-rail="collapsed"] .rail-label,
    .app-shell[data-rail="collapsed"] .rail-grid,
    .app-shell[data-rail="collapsed"] .command-list,
    .app-shell[data-rail="collapsed"] .nav-link span,
    .app-shell[data-rail="collapsed"] .brand-card h2 {
      display: none;
    }
    .app-shell[data-rail="collapsed"] .brand-card,
    .app-shell[data-rail="collapsed"] .rail-panel {
      padding: 14px 12px;
    }
    .app-shell[data-rail="collapsed"] .eyebrow::before {
      width: 16px;
    }
    .app-shell[data-rail="collapsed"] .nav-link {
      text-align: center;
      padding: 14px 10px;
    }
    .app-shell[data-layout="focus"] .overview-grid {
      grid-template-columns: 1fr;
    }
    .app-shell[data-layout="focus"] .split-grid {
      grid-template-columns: 1fr;
    }
    .app-shell[data-layout="focus"] .status-strip {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .app-shell[data-layout="compact"] .metric-grid,
    .app-shell[data-layout="compact"] .status-strip {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .app-shell[data-layout="compact"] .agent-grid,
    .app-shell[data-layout="compact"] .task-list,
    .app-shell[data-layout="compact"] .event-feed {
      gap: 10px;
    }
    .app-shell[data-layout="compact"] .agent-card,
    .app-shell[data-layout="compact"] .task-card,
    .app-shell[data-layout="compact"] .status-card,
    .app-shell[data-layout="compact"] .deliverable-card,
    .app-shell[data-layout="compact"] .command-card {
      padding: 14px;
      border-radius: 18px;
    }
    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 28%, transparent); }
      70% { box-shadow: 0 0 0 12px color-mix(in srgb, currentColor 0%, transparent); }
      100% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 0%, transparent); }
    }
    @media (max-width: 1360px) {
      .app-shell { grid-template-columns: 258px minmax(0, 1fr); }
      .topbar {
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: start;
      }
      .search-shell {
        grid-column: 1 / -1;
      }
      .overview-grid {
        grid-template-columns: 1fr 1fr;
      }
      .overview-grid > .panel:last-child {
        grid-column: 1 / -1;
      }
      .workspace-hero-head,
      .workspace-split {
        grid-template-columns: 1fr;
      }
      .workspace-note-card {
        justify-self: start;
      }
      .workspace-kpi-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .admin-hero-head,
      .admin-operations-grid,
      .admin-team-grid {
        grid-template-columns: 1fr;
      }
      .admin-hero-side {
        justify-items: start;
      }
      .admin-chip-row {
        justify-content: flex-start;
      }
      .admin-kpi-grid,
      .admin-fleet-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
    @media (max-width: 1040px) {
      .app-shell { grid-template-columns: 1fr; }
      .rail { position: static; }
      .topbar { grid-template-columns: 1fr; }
      .overview-grid, .split-grid { grid-template-columns: 1fr; }
      .conversation-shell { grid-template-columns: 1fr; }
      .studio-grid, .drawer-action-grid { grid-template-columns: 1fr; }
      .status-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .relay-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .main-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 760px) {
      .shell { width: min(100vw - 18px, 1480px); margin: 10px auto 26px; }
      .app-shell { width: min(100vw - 14px, 1720px); margin: 8px auto 22px; }
      .app-shell[data-rail="collapsed"] { grid-template-columns: 1fr; }
      .hero { padding: 22px 18px 20px; border-radius: 24px; }
      .workspace-hero { padding: 22px 18px; }
      .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .workspace-kpi-grid { grid-template-columns: 1fr; }
      .transcript-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .relay-grid { grid-template-columns: 1fr; }
      .status-strip { grid-template-columns: 1fr 1fr; }
      .agent-facts, .drawer-grid { grid-template-columns: 1fr 1fr; }
      .selection-stats { grid-template-columns: 1fr; }
      .panel-head { padding: 18px 18px 10px; }
      .agent-grid, .task-list, .event-feed { padding: 16px; }
      .event-feed::before { left: 16px; }
      .event { padding-left: 20px; }
      .event::before { left: -15px; }
      .admin-hero { padding: 22px 18px; }
      .admin-kpi-grid,
      .admin-fleet-grid,
      .admin-instance-facts,
      .admin-user-grid {
        grid-template-columns: 1fr;
      }
      .admin-panel .admin-role-grid,
      .admin-panel .admin-fleet-grid,
      .admin-panel .admin-seat-list,
      .admin-panel .admin-studio-grid {
        padding: 16px;
      }
      .admin-audit-panel .event-feed {
        padding: 16px 16px 18px 24px;
      }
      .admin-audit-panel .event-feed::before {
        left: 24px;
        top: 16px;
        bottom: 16px;
      }
      .drawer {
        top: 8px;
        right: 8px;
        left: 8px;
        bottom: 8px;
        width: auto;
      }
    }
    @media (prefers-reduced-motion: reduce) {
      * { animation: none !important; transition: none !important; }
    }
  </style>
</head>
<body>
  <div class="app-shell" id="app-shell" data-layout="operations" data-rail="expanded">
    <aside class="rail">
      <section class="brand-card">
        <div class="eyebrow">Sansheng Liubu</div>
        <h2>Mission Control</h2>
        <p class="rail-copy">它现在不只是一个实时看板，而是一套本地多 Agent 产品。你可以在不同模块里看现场、交付、活动、主题和操作命令。</p>
      </section>

      <section class="rail-panel">
        <div class="rail-label">产品导航</div>
        <div class="nav-stack">
          <button class="nav-link" data-view="overview">总览<span>关键指标、接力网和现场概览</span></button>
          <button class="nav-link" data-view="agents">Agent 运营<span>完整 roster、状态分布和负责人现场</span></button>
          <button class="nav-link" data-view="tasks">交付执行<span>任务河道、筛选、已完成交付物</span></button>
          <button class="nav-link" data-view="conversations">会话中心<span>真实 sessions、对话记录和直接发问</span></button>
          <button class="nav-link" data-view="activity">活动时间线<span>handoff 与 progress 的完整动态</span></button>
          <button class="nav-link" data-view="themes">主题中心<span>当前组织主题与产品运行命令</span></button>
          <button class="nav-link" data-view="skills">Skills Center<span>技能目录、校验、脚手架与打包</span></button>
          <button class="nav-link" data-view="openclaw">OpenClaw<span>官方运行态、skills、schema 与 gateway 适配</span></button>
          <button class="nav-link" data-view="admin">商业后台<span>账号席位、角色权限与审计留痕</span></button>
        </div>
      </section>

      <section class="rail-panel">
        <div class="rail-label">当前上下文</div>
        <div class="rail-grid">
          <div class="rail-kv">主题<strong id="rail-theme-name"></strong></div>
          <div class="rail-kv">主理人<strong id="rail-owner-title"></strong></div>
          <div class="rail-kv">路由 Agent<strong id="rail-router-agent"></strong></div>
          <div class="rail-kv">安装目录<strong id="rail-install-dir"></strong></div>
        </div>
      </section>

      <section class="rail-panel">
        <div class="rail-label">快速动作</div>
        <div class="command-list" id="rail-command-list"></div>
      </section>
    </aside>

    <div class="workspace-shell">
      <header class="topbar">
        <div>
          <div class="topbar-kicker">Local Product</div>
          <div class="topbar-title" id="view-title">Mission Control</div>
          <div class="topbar-subtitle" id="view-subtitle">本地多 Agent 应用，不再只是单页监控。</div>
        </div>
        <div class="search-shell">
          <input class="search-input" id="global-search" type="search" placeholder="搜索 Agent、任务、事件、交付物、skills">
        </div>
        <div class="topbar-tools">
          <button class="button secondary small" id="toggle-rail">菜单</button>
          <div class="layout-row" id="layout-row">
            <button class="filter-chip" data-layout="operations" type="button">运营</button>
            <button class="filter-chip" data-layout="focus" type="button">聚焦</button>
            <button class="filter-chip" data-layout="compact" type="button">紧凑</button>
          </div>
          <div class="auth-row" id="auth-row">
            <span class="theme-badge" id="auth-status">已登录</span>
            <form method="post" action="/logout" id="logout-form">
              <input type="hidden" name="next" value="/login">
              <button class="button secondary small" type="submit">退出</button>
            </form>
          </div>
          <button class="button" id="refresh-now">立即刷新</button>
          <button class="button secondary" id="toggle-refresh">暂停实时刷新</button>
          <a class="button secondary" id="json-link" href="./collaboration-dashboard.json">查看 JSON 快照</a>
          <span class="live-indicator" data-tone="idle" id="live-indicator"></span>
        </div>
      </header>

      <main class="view-stack">
        <section class="view" data-view="overview">
          <section class="hero">
            <div class="eyebrow">Multi-Agent Product</div>
            <h1>现在它更像一套控制台，而不是一张大屏。</h1>
            <p class="lede">总览看势能，Agent 运营看人手，交付执行看任务，活动时间线看接力，主题中心看组织模式。你可以像用一个真正的本地产品一样管理这套多 Agent 系统。</p>
            <div class="hero-meta">
              <span>主题：<strong id="theme-name"></strong></span>
              <span>主理人：<strong id="owner-title"></strong></span>
              <span>生成时间：<strong id="generated-at"></strong></span>
              <span>安装目录：<strong id="install-dir"></strong></span>
            </div>
            <div class="metric-grid" id="metric-grid"></div>
          </section>

          <section class="panel">
            <div class="panel-head">
              <div>
                <h2 class="panel-title">接力网</h2>
                <p class="panel-subtitle">总览当前 24 小时最频繁的 handoff 关系，快速判断系统是不是在真正协同推进。</p>
              </div>
            </div>
            <div class="relay-grid" id="overview-relay-grid"></div>
          </section>

          <div class="overview-grid">
            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">现场负责人</h2>
                  <p class="panel-subtitle">优先看最近有活跃任务或新信号的 Agent。</p>
                </div>
              </div>
              <div class="agent-grid" id="overview-agent-grid"></div>
            </section>

            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">任务河道</h2>
                  <p class="panel-subtitle">这里聚焦正在执行或刚有信号变化的任务。</p>
                </div>
              </div>
              <div class="task-list" id="overview-task-list"></div>
            </section>

            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">最新活动</h2>
                  <p class="panel-subtitle">最近发生的 handoff / progress，可直接跳进回放。</p>
                </div>
              </div>
              <div class="event-feed" id="overview-event-feed"></div>
            </section>
          </div>
        </section>

        <section class="view operations-view" data-view="agents" hidden>
          <section class="workspace-hero">
            <div class="workspace-hero-head">
              <div>
                <div class="eyebrow">Roster Control</div>
                <h1 class="workspace-hero-title">Agent 运营台</h1>
                <p class="workspace-hero-copy">参考 Ant Design 的企业后台方式，把 roster、负载、状态分布和协作入口收口成一张运营页。你应该先看到风险和负载，再决定点进谁。</p>
              </div>
              <div class="workspace-note-card">
                <span>运营原则</span>
                <strong>先看状态分布，再追高负载 Agent。</strong>
                <p>推进中、待反馈、阻塞和空闲必须同时看，避免只盯着最热闹的那一个。</p>
              </div>
            </div>
            <div class="workspace-kpi-grid" id="agents-summary-list"></div>
          </section>

          <section class="panel workspace-panel">
            <div class="panel-head">
              <div>
                <h2 class="panel-title">团队态势</h2>
                <p class="panel-subtitle">把推进、等待、阻塞、待命和空闲分层摆出来，先看清整支团队的温度分布。</p>
              </div>
            </div>
            <div class="panel-body">
              <div class="status-strip" id="agent-status-strip"></div>
            </div>
          </section>

          <section class="panel workspace-panel">
            <div class="panel-head">
              <div>
                <h2 class="panel-title">Agent 运营台</h2>
                <p class="panel-subtitle">完整查看每个 Agent 的状态、焦点、在手任务和最近协同信号，并一键直达它的对话入口。</p>
              </div>
            </div>
            <div class="agent-grid" id="agents-page-grid"></div>
          </section>
        </section>

        <section class="view operations-view" data-view="tasks" hidden>
          <section class="workspace-hero">
            <div class="workspace-hero-head">
              <div>
                <div class="eyebrow">Delivery River</div>
                <h1 class="workspace-hero-title">交付执行台</h1>
                <p class="workspace-hero-copy">参考 Ant Design Pro 的工作台思路，把任务创建、焦点上下文、执行河道、交付物和 runbook 放进同一页，让交付推进更像产品后台，而不是单纯列表。</p>
              </div>
              <div class="workspace-note-card">
                <span>交付原则</span>
                <strong>创建、推进、阻塞、归档要在同一工作流里完成。</strong>
                <p>先确认焦点任务，再决定是继续推进、补背景，还是转入阻塞处理和结果归档。</p>
              </div>
            </div>
            <div class="workspace-kpi-grid" id="tasks-summary-list"></div>
          </section>

          <div class="workspace-split">
            <section class="panel workspace-panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">操作工作台</h2>
                  <p class="panel-subtitle">现在可以直接在产品里建任务，不需要先回到终端。打开任意任务后，还能在抽屉里继续推进、阻塞或完成。</p>
                </div>
              </div>
              <div class="studio-grid" id="task-action-studio"></div>
            </section>

            <section class="panel workspace-panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">当前焦点任务</h2>
                  <p class="panel-subtitle">这里会跟着你最近打开的任务变化，方便你在操作前快速确认上下文。</p>
                </div>
              </div>
              <div id="task-focus-card"></div>
            </section>
          </div>

          <section class="panel workspace-panel">
            <div class="panel-head">
              <div>
                <h2 class="panel-title">交付执行台</h2>
                <p class="panel-subtitle">按阶段筛选任务，打开任务回放，直接追踪产出与阻塞。</p>
              </div>
              <div class="filter-row" id="task-filter-row"></div>
            </div>
            <div class="task-list" id="tasks-page-list"></div>
          </section>

          <div class="workspace-split">
            <section class="panel workspace-panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">交付物</h2>
                  <p class="panel-subtitle">展示已完成任务和其输出路径，方便把多 Agent 产出当成可管理资产。</p>
                </div>
              </div>
              <div class="deliverable-list" id="deliverables-list"></div>
            </section>

            <section class="panel workspace-panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">本地操作</h2>
                  <p class="panel-subtitle">产品常用命令，适合作为操作面板内置的 runbook。</p>
                </div>
              </div>
              <div class="command-list" id="task-command-list"></div>
            </section>
          </div>
        </section>

        <section class="view operations-view" data-view="conversations" hidden>
          <section class="workspace-hero">
            <div class="workspace-hero-head">
              <div>
                <div class="eyebrow">Dialogue Ops</div>
                <h1 class="workspace-hero-title">会话中心</h1>
                <p class="workspace-hero-copy">参考 Ant Design 的企业控制台交互，把会话列表、直达主会话、指令入口和 transcript 分区管理。这里既能看，也能继续对话和调度。</p>
              </div>
              <div class="workspace-note-card">
                <span>会话原则</span>
                <strong>先定目标 Agent，再决定是否接着原会话说。</strong>
                <p>把“找会话”和“继续协作”分开，可以让产品更像指挥台，而不是消息抽屉。</p>
              </div>
            </div>
            <div class="workspace-kpi-grid" id="conversation-summary-list"></div>
          </section>

          <div class="workspace-split">
            <section class="panel workspace-panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">对话命令</h2>
                  <p class="panel-subtitle">保留官方命令入口，既能在产品内操作，也能随时回到终端做排障和自动化。</p>
                </div>
              </div>
              <div class="command-list" id="conversation-command-list"></div>
            </section>

            <section class="panel workspace-panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">会话工作台</h2>
                  <p class="panel-subtitle">先点亮目标 Agent 或主会话，再在这里直接继续对话，把“查看”和“操作”放在一个工作区里。</p>
                </div>
              </div>
              <div class="studio-grid" id="conversation-studio"></div>
            </section>
          </div>

          <div class="conversation-shell">
            <section class="panel workspace-panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">真实会话列表</h2>
                  <p class="panel-subtitle">这里读的是 OpenClaw `sessions --all-agents` 的真实索引，不是产品自己生成的影子会话。</p>
                </div>
              </div>
              <div class="conversation-list" id="conversation-list"></div>
            </section>

            <section class="panel workspace-panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">对话现场</h2>
                  <p class="panel-subtitle">查看选中会话的真实 transcript，并直接继续发问。未选会话时，会默认发给所选 Agent 的主会话。</p>
                </div>
              </div>
              <div class="transcript-stream" id="conversation-transcript"></div>
            </section>
          </div>
        </section>

        <section class="view" data-view="activity" hidden>
          <div class="split-grid">
            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">接力关系</h2>
                  <p class="panel-subtitle">看过去 24 小时的 handoff 网络，从组织角度观察协同。</p>
                </div>
              </div>
              <div class="relay-grid" id="activity-relay-grid"></div>
            </section>

            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">完整时间线</h2>
                  <p class="panel-subtitle">按时间顺序查看所有 handoff 和 progress 事件。</p>
                </div>
              </div>
              <div class="event-feed" id="activity-event-feed"></div>
            </section>
          </div>
        </section>

        <section class="view" data-view="themes" hidden>
          <div class="split-grid">
            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">当前组织主题</h2>
                  <p class="panel-subtitle">把多 Agent 组织方式、主理人身份和常用命令放到一个主题中心里。</p>
                </div>
              </div>
              <div class="deliverable-list" id="current-theme-summary"></div>
            </section>

            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">主题目录</h2>
                  <p class="panel-subtitle">了解三套组织结构各自适合的协同风格和使用场景。</p>
                </div>
              </div>
              <div class="theme-grid" id="theme-grid"></div>
            </section>
          </div>

          <section class="panel">
            <div class="panel-head">
              <div>
                <h2 class="panel-title">运行命令</h2>
                <p class="panel-subtitle">产品内嵌的本地 runbook，用来打开看板、导出快照和做健康检查。</p>
              </div>
            </div>
            <div class="command-list" id="theme-command-list"></div>
          </section>
        </section>

        <section class="view" data-view="skills" hidden>
          <div class="split-grid">
            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">技能总览</h2>
                  <p class="panel-subtitle">把 Anthropic Skills 指南里的结构、触发、校验和打包能力落到本地产品里。</p>
                </div>
              </div>
              <div class="deliverable-list" id="skills-summary-list"></div>
            </section>

            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">指南映射</h2>
                  <p class="panel-subtitle">这些卡片对应的是你给我的 PDF 里最关键的能力：渐进披露、触发质量和分发准备度。</p>
                </div>
              </div>
              <div class="deliverable-list" id="skills-guidance-list"></div>
            </section>
          </div>

          <div class="split-grid">
            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">技能目录</h2>
                  <p class="panel-subtitle">扫描本仓库的 `skills/` 目录，检查 frontmatter、结构质量、示例和打包状态。</p>
                </div>
              </div>
              <div class="deliverable-list" id="skills-catalog-list"></div>
            </section>

            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">技能工作台</h2>
                  <p class="panel-subtitle">Owner 可以直接在产品里建 skill 脚手架并打包 zip，准备上传到 Claude.ai 或放进 Claude Code。</p>
                </div>
              </div>
              <div class="studio-grid" id="skills-studio"></div>
            </section>
          </div>

          <section class="panel">
            <div class="panel-head">
              <div>
                <h2 class="panel-title">技能命令</h2>
                <p class="panel-subtitle">直接复制底层命令，既能走产品，也能回到终端做自动化。</p>
              </div>
            </div>
            <div class="command-list" id="skills-command-list"></div>
          </section>
        </section>

        <section class="view" data-view="openclaw" hidden>
          <div class="split-grid">
            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">OpenClaw 运行态</h2>
                  <p class="panel-subtitle">把官方 CLI、Gateway、schema、skills 和 onboarding 适配面统一放到一个产品视图里。</p>
                </div>
              </div>
              <div class="deliverable-list" id="openclaw-summary-list"></div>
            </section>

            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">兼容性判断</h2>
                  <p class="panel-subtitle">快速判断当前仓库和 OpenClaw 运行面的耦合状态，避免只在 README 里说“兼容”。</p>
                </div>
              </div>
              <div class="deliverable-list" id="openclaw-compat-list"></div>
            </section>
          </div>

          <div class="split-grid">
            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">Channels 与 Gateway</h2>
                  <p class="panel-subtitle">直接看官方 Gateway health 返回的 channel 与 agent 运行信息。</p>
                </div>
              </div>
              <div class="deliverable-list" id="openclaw-channels-list"></div>
            </section>

            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">原生 Skills 生态</h2>
                  <p class="panel-subtitle">同时看 OpenClaw 当前识别到的原生 skills，以及哪些本仓库 skill 已经发布进运行时。</p>
                </div>
              </div>
              <div class="deliverable-list" id="openclaw-native-skills-list"></div>
            </section>
          </div>

          <section class="panel">
            <div class="panel-head">
              <div>
                <h2 class="panel-title">OpenClaw 命令</h2>
                <p class="panel-subtitle">直接复制官方命令，进入 dashboard、doctor、gateway health、skills list 和 onboard。</p>
              </div>
            </div>
            <div class="command-list" id="openclaw-command-list"></div>
          </section>
        </section>

        <section class="view admin-view" data-view="admin" hidden>
          <section class="admin-hero">
            <div class="admin-hero-head">
              <div>
                <div class="eyebrow">Control Plane</div>
                <h1 class="admin-hero-title">商业后台控制平面</h1>
                <p class="admin-hero-copy">参考 Ant Design 的后台产品结构，把实例舰队、席位治理、权限边界和审计留痕统一到一个管理者视角里，方便你按产品运营方式持续管理这套多 Agent 系统。</p>
              </div>
              <div class="admin-hero-side">
                <div class="admin-chip-row">
                  <span class="admin-chip">Fleet Registry</span>
                  <span class="admin-chip">Seat Governance</span>
                  <span class="admin-chip">Audit Trail</span>
                </div>
                <div class="admin-note-card">
                  <span>运营原则</span>
                  <strong>一屏内先看经营指标，再做实例与成员治理。</strong>
                  <p>这页只保留真正和产品运营相关的对象，不再把后台做成一组平铺的说明卡片。</p>
                </div>
              </div>
            </div>
            <div class="admin-kpi-grid" id="admin-summary-list"></div>
          </section>

          <div class="admin-operations-grid">
            <section class="panel admin-panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">安装舰队</h2>
                  <p class="panel-subtitle">先看清现在到底有几套系统在跑、哪一套可达、哪一套正在承载活跃任务。</p>
                </div>
              </div>
              <div class="deliverable-list admin-fleet-grid" id="admin-instance-list"></div>
            </section>

            <div class="admin-side-stack">
              <section class="panel admin-panel">
                <div class="panel-head">
                  <div>
                    <h2 class="panel-title">角色矩阵</h2>
                    <p class="panel-subtitle">把 Owner、Operator、Viewer 的权限边界讲清楚，避免后台继续靠共享 token 运转。</p>
                  </div>
                </div>
                <div class="deliverable-list admin-role-grid" id="admin-role-list"></div>
              </section>

              <section class="panel admin-panel">
                <div class="panel-head">
                  <div>
                    <h2 class="panel-title">登记实例</h2>
                    <p class="panel-subtitle">Owner 在这里把其他本地安装纳入控制平面，开始形成多实例运营能力。</p>
                  </div>
                </div>
                <div class="studio-grid admin-studio-grid" id="admin-instance-studio"></div>
              </section>
            </div>
          </div>

          <div class="admin-team-grid">
            <section class="panel admin-panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">团队席位</h2>
                  <p class="panel-subtitle">按人管理访问、角色和状态，让产品的使用方式从单人控制台升级到团队后台。</p>
                </div>
              </div>
              <div class="deliverable-list admin-seat-list" id="admin-user-list"></div>
            </section>

            <section class="panel admin-panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">席位工作台</h2>
                  <p class="panel-subtitle">Owner 可以在这里补齐新成员、调整权限和重置账号，不需要再切回终端做治理动作。</p>
                </div>
              </div>
              <div class="studio-grid admin-studio-grid" id="admin-user-studio"></div>
            </section>
          </div>

          <section class="panel admin-panel admin-audit-panel">
            <div class="panel-head">
              <div>
                <h2 class="panel-title">操作审计</h2>
                <p class="panel-subtitle">登录、任务推进、主题切换、成员治理和实例登记都会沉淀在这里，便于做事后追溯和责任界定。</p>
              </div>
            </div>
            <div class="event-feed" id="admin-audit-feed"></div>
          </section>
        </section>
      </main>
    </div>
  </div>

  <div class="scrim" id="scrim" hidden></div>
  <aside class="drawer" id="drawer" data-open="false" aria-hidden="true">
    <div class="drawer-shell">
      <div class="drawer-head">
        <div>
          <div class="drawer-kicker" id="drawer-kicker">Inspector</div>
          <div class="drawer-title" id="drawer-title">协同详情</div>
        </div>
        <button class="drawer-close" id="drawer-close">关闭</button>
      </div>
      <div class="drawer-body" id="drawer-body"></div>
    </div>
  </aside>
  <div class="toast-stack" id="toast-stack" aria-live="polite"></div>

  <script id="dashboard-data" type="application/json">__INITIAL_STATE__</script>
  <script>
    let state = JSON.parse(document.getElementById("dashboard-data").textContent);
    const supportsHttp = location.protocol.startsWith("http");
    const VIEW_META = {
      overview: {
        title: "Mission Control",
        subtitle: "用产品化视角总览多 Agent 系统当前的协同势能。",
      },
      agents: {
        title: "Agent 运营",
        subtitle: "看清谁在推进、谁在等待、谁需要介入支持。",
      },
      tasks: {
        title: "交付执行",
        subtitle: "把任务河道、交付物和 runbook 放在同一个工作台。",
      },
      conversations: {
        title: "会话中心",
        subtitle: "进入真实 OpenClaw sessions，看 transcript，也能直接继续和 Agent 对话。",
      },
      activity: {
        title: "活动时间线",
        subtitle: "按时间追踪 handoff 与 progress，快速还原协同路径。",
      },
      themes: {
        title: "主题中心",
        subtitle: "把组织主题、运行命令和当前上下文放进一个统一入口。",
      },
      skills: {
        title: "Skills Center",
        subtitle: "用产品方式管理 Claude 风格技能的目录、质量、脚手架与分发准备度。",
      },
      openclaw: {
        title: "OpenClaw Center",
        subtitle: "把官方运行态、schema、skills 和 gateway 适配收口到一个产品视图里。",
      },
      admin: {
        title: "商业后台",
        subtitle: "用控制平面视角经营这套多 Agent 产品：舰队、席位、权限与审计都在这里。",
      },
    };

    const refs = {
      appShell: document.getElementById("app-shell"),
      navLinks: Array.from(document.querySelectorAll(".nav-link")),
      views: Array.from(document.querySelectorAll(".view")),
      viewTitle: document.getElementById("view-title"),
      viewSubtitle: document.getElementById("view-subtitle"),
      globalSearch: document.getElementById("global-search"),
      toggleRail: document.getElementById("toggle-rail"),
      layoutButtons: Array.from(document.querySelectorAll("[data-layout]")).filter((node) => node.closest("#layout-row")),
      authRow: document.getElementById("auth-row"),
      authStatus: document.getElementById("auth-status"),
      logoutForm: document.getElementById("logout-form"),
      metricGrid: document.getElementById("metric-grid"),
      overviewRelayGrid: document.getElementById("overview-relay-grid"),
      overviewAgentGrid: document.getElementById("overview-agent-grid"),
      overviewTaskList: document.getElementById("overview-task-list"),
      overviewEventFeed: document.getElementById("overview-event-feed"),
      agentsSummaryList: document.getElementById("agents-summary-list"),
      agentStatusStrip: document.getElementById("agent-status-strip"),
      agentsPageGrid: document.getElementById("agents-page-grid"),
      tasksSummaryList: document.getElementById("tasks-summary-list"),
      taskFilterRow: document.getElementById("task-filter-row"),
      taskActionStudio: document.getElementById("task-action-studio"),
      taskFocusCard: document.getElementById("task-focus-card"),
      tasksPageList: document.getElementById("tasks-page-list"),
      deliverablesList: document.getElementById("deliverables-list"),
      taskCommandList: document.getElementById("task-command-list"),
      conversationSummaryList: document.getElementById("conversation-summary-list"),
      conversationCommandList: document.getElementById("conversation-command-list"),
      conversationList: document.getElementById("conversation-list"),
      conversationStudio: document.getElementById("conversation-studio"),
      conversationTranscript: document.getElementById("conversation-transcript"),
      activityRelayGrid: document.getElementById("activity-relay-grid"),
      activityEventFeed: document.getElementById("activity-event-feed"),
      currentThemeSummary: document.getElementById("current-theme-summary"),
      themeGrid: document.getElementById("theme-grid"),
      themeCommandList: document.getElementById("theme-command-list"),
      skillsSummaryList: document.getElementById("skills-summary-list"),
      skillsGuidanceList: document.getElementById("skills-guidance-list"),
      skillsCatalogList: document.getElementById("skills-catalog-list"),
      skillsStudio: document.getElementById("skills-studio"),
      skillsCommandList: document.getElementById("skills-command-list"),
      openclawSummaryList: document.getElementById("openclaw-summary-list"),
      openclawCompatList: document.getElementById("openclaw-compat-list"),
      openclawChannelsList: document.getElementById("openclaw-channels-list"),
      openclawNativeSkillsList: document.getElementById("openclaw-native-skills-list"),
      openclawCommandList: document.getElementById("openclaw-command-list"),
      adminSummaryList: document.getElementById("admin-summary-list"),
      adminRoleList: document.getElementById("admin-role-list"),
      adminInstanceList: document.getElementById("admin-instance-list"),
      adminInstanceStudio: document.getElementById("admin-instance-studio"),
      adminUserList: document.getElementById("admin-user-list"),
      adminUserStudio: document.getElementById("admin-user-studio"),
      adminAuditFeed: document.getElementById("admin-audit-feed"),
      railThemeName: document.getElementById("rail-theme-name"),
      railOwnerTitle: document.getElementById("rail-owner-title"),
      railRouterAgent: document.getElementById("rail-router-agent"),
      railInstallDir: document.getElementById("rail-install-dir"),
      railCommandList: document.getElementById("rail-command-list"),
      generatedAt: document.getElementById("generated-at"),
      themeName: document.getElementById("theme-name"),
      ownerTitle: document.getElementById("owner-title"),
      installDir: document.getElementById("install-dir"),
      refreshNow: document.getElementById("refresh-now"),
      toggleRefresh: document.getElementById("toggle-refresh"),
      jsonLink: document.getElementById("json-link"),
      liveIndicator: document.getElementById("live-indicator"),
      scrim: document.getElementById("scrim"),
      drawer: document.getElementById("drawer"),
      drawerKicker: document.getElementById("drawer-kicker"),
      drawerTitle: document.getElementById("drawer-title"),
      drawerBody: document.getElementById("drawer-body"),
      drawerClose: document.getElementById("drawer-close"),
      toastStack: document.getElementById("toast-stack"),
    };

    let paused = false;
    let eventSource = null;
    let reconnectTimer = null;
    let lastSyncAt = Date.now();
    let connectionMode = supportsHttp ? "connecting" : "snapshot";
    let fetchInFlight = false;
    let selection = { kind: null, id: null };
    let currentView = getViewFromLocation();
    let searchQuery = "";
    let taskFilter = "active";
    let conversationState = {
      key: "",
      agentId: "",
      sessionId: "",
      preferredAgentId: "",
      mode: "session",
      transcript: null,
      loading: false,
      error: "",
    };
    let layoutMode = localStorage.getItem("sansheng-layout-mode") || "operations";
    let railCollapsed = localStorage.getItem("sansheng-rail-collapsed") === "true";

    function el(tag, className, text) {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    }

    function clearNode(node) {
      node.textContent = "";
    }

    function formatClock(value) {
      if (!value) return "未知时间";
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? "未知时间" : date.toLocaleString();
    }

    function setLiveStatus(text, tone) {
      refs.liveIndicator.dataset.tone = tone;
      refs.liveIndicator.textContent = text;
    }

    function dashboardJsonHref() {
      return supportsHttp ? "/collaboration-dashboard.json" : "./collaboration-dashboard.json";
    }

    function dashboardApiHref() {
      return supportsHttp ? "/api/dashboard" : dashboardJsonHref();
    }

    function dashboardEventsHref() {
      return "/events";
    }

    function getViewFromLocation() {
      const fromHash = (location.hash || "").replace(/^#\/?/, "");
      if (VIEW_META[fromHash]) return fromHash;
      const mapping = {
        "/": "overview",
        "/overview": "overview",
        "/collaboration-dashboard.html": "overview",
        "/agents": "agents",
        "/tasks": "tasks",
        "/conversations": "conversations",
        "/activity": "activity",
        "/themes": "themes",
        "/skills": "skills",
        "/openclaw": "openclaw",
        "/admin": "admin",
      };
      return mapping[location.pathname.replace(/\/+$/, "") || "/"] || "overview";
    }

    function viewPath(view) {
      return view === "overview" ? "/" : `/${view}`;
    }

    function navigate(view) {
      currentView = view;
      if (supportsHttp) {
        const target = viewPath(view);
        if (location.pathname !== target) {
          history.pushState({}, "", target);
        }
      } else {
        const targetHash = view === "overview" ? "" : `#${view}`;
        if (location.hash !== targetHash) {
          location.hash = targetHash;
        }
      }
      renderAll();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function applyLayoutPrefs() {
      refs.appShell.dataset.layout = layoutMode;
      refs.appShell.dataset.rail = railCollapsed ? "collapsed" : "expanded";
      refs.layoutButtons.forEach((button) => {
        button.dataset.active = String(button.dataset.layout === layoutMode);
      });
      refs.toggleRail.textContent = railCollapsed ? "展开菜单" : "收起菜单";
      if (!supportsHttp) {
        refs.authRow.hidden = true;
      } else {
        refs.authRow.hidden = false;
      }
    }

    function setLayoutMode(mode) {
      layoutMode = mode;
      localStorage.setItem("sansheng-layout-mode", layoutMode);
      applyLayoutPrefs();
    }

    function toggleRail() {
      railCollapsed = !railCollapsed;
      localStorage.setItem("sansheng-rail-collapsed", String(railCollapsed));
      applyLayoutPrefs();
    }

    function normalizeText(value) {
      return String(value || "").toLowerCase();
    }

    function matchesQuery(value) {
      if (!searchQuery) return true;
      return normalizeText(value).includes(normalizeText(searchQuery));
    }

    function mapTasks() {
      const map = new Map();
      (state.taskIndex || []).forEach((task) => map.set(task.id, task));
      (state.tasks || []).forEach((task) => map.set(task.id, task));
      return map;
    }

    function getTask(taskId) {
      return mapTasks().get(taskId) || null;
    }

    function getAgent(agentId) {
      return (state.agents || []).find((agent) => agent.id === agentId) || null;
    }

    function agentSearchBlob(agent) {
      return [
        agent.title,
        agent.name,
        agent.id,
        agent.model,
        agent.focus,
        ...(agent.activeTaskCards || []).map((task) => task.title),
        ...(agent.recentSignals || []).map((signal) => `${signal.title} ${signal.detail}`),
      ].join(" ");
    }

    function taskSearchBlob(task) {
      return [
        task.id,
        task.title,
        task.state,
        task.owner,
        task.org,
        task.currentAgentLabel,
        task.currentUpdate,
        task.output,
        ...(task.route || []),
        ...(task.todoItems || []).map((item) => item.title),
      ].join(" ");
    }

    function eventSearchBlob(event) {
      return [event.headline, event.detail, event.title, event.taskId].join(" ");
    }

    function filteredAgents() {
      return (state.agents || []).filter((agent) => matchesQuery(agentSearchBlob(agent)));
    }

    function filteredTasks() {
      return (state.taskIndex || []).filter((task) => {
        if (taskFilter === "active" && !task.active) return false;
        if (taskFilter === "blocked" && !task.blocked) return false;
        if (taskFilter === "done" && normalizeText(task.state) !== "done") return false;
        return matchesQuery(taskSearchBlob(task));
      });
    }

    function filteredEvents() {
      return (state.events || []).filter((event) => matchesQuery(eventSearchBlob(event)));
    }

    function filteredDeliverables() {
      return (state.deliverables || []).filter((item) => matchesQuery(`${item.id} ${item.title} ${item.summary} ${item.output}`));
    }

    function filteredSkills() {
      return ((state.skills || {}).skills || []).filter((skill) =>
        matchesQuery(`${skill.displayName} ${skill.slug} ${skill.description} ${skill.categoryLabel} ${skill.relativePath}`),
      );
    }

    function conversationSearchBlob(session) {
      return [
        session.label,
        session.agentId,
        session.agentLabel,
        session.key,
        session.sourceLabel,
        session.model,
        session.provider,
        session.preview,
      ].join(" ");
    }

    function filteredConversations() {
      return (((state.conversations || {}).sessions) || []).filter((session) => matchesQuery(conversationSearchBlob(session)));
    }

    function copyText(text) {
      if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text);
      }
      const input = document.createElement("textarea");
      input.value = text;
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.appendChild(input);
      input.select();
      document.execCommand("copy");
      input.remove();
      return Promise.resolve();
    }

    function makeCopyButton(text, label = "复制命令") {
      const button = el("button", "button secondary", label);
      button.type = "button";
      button.addEventListener("click", async () => {
        await copyText(text);
        const original = button.textContent;
        button.textContent = "已复制";
        setTimeout(() => {
          button.textContent = original;
        }, 1200);
      });
      return button;
    }

    function runtimeCaps() {
      return state.runtime || {};
    }

    function supportsActions() {
      return supportsHttp && Boolean(runtimeCaps().actionsEnabled);
    }

    function supportsThemeSwitch() {
      return supportsActions() && Boolean(runtimeCaps().themeSwitchAvailable);
    }

    function supportsConversationWrite() {
      return supportsActions() && hasPermission("conversationWrite");
    }

    function currentUser() {
      return runtimeCaps().currentUser || { displayName: "Guest", roleLabel: "Viewer", role: "viewer" };
    }

    function hasPermission(permissionKey) {
      return Boolean((runtimeCaps().permissions || {})[permissionKey]);
    }

    function showToast(message, tone = "success", title = "") {
      if (!refs.toastStack) return;
      const toast = el("div", "toast");
      toast.dataset.tone = tone;
      toast.append(el("strong", "", title || (tone === "success" ? "已完成" : tone === "warn" ? "请注意" : "操作失败")));
      toast.append(el("p", "", message));
      refs.toastStack.append(toast);
      setTimeout(() => {
        toast.dataset.hiding = "true";
      }, 2400);
      setTimeout(() => {
        toast.remove();
      }, 2700);
    }

    function setButtonBusy(button, busy, busyLabel = "处理中...") {
      if (!button) return;
      if (!button.dataset.defaultLabel) {
        button.dataset.defaultLabel = button.textContent;
      }
      button.disabled = busy;
      button.textContent = busy ? busyLabel : button.dataset.defaultLabel;
    }

    async function postActionJson(path, payload) {
      if (!supportsActions()) {
        throw new Error("请通过本地登录后的产品页面执行操作。");
      }
      const response = await fetch(path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({
          ...payload,
          actionToken: runtimeCaps().actionToken || "",
        }),
      });
      let data = {};
      try {
        data = await response.json();
      } catch (_error) {
        data = {};
      }
      if (!response.ok || data.ok === false) {
        throw new Error(data.message || data.error || `HTTP ${response.status}`);
      }
      if (data.dashboard) {
        state = data.dashboard;
        lastSyncAt = Date.now();
        renderAll();
      } else if (supportsHttp) {
        await fetchLatestDashboard("manual");
      }
      return data;
    }

    async function getJson(path) {
      const response = await fetch(path, {
        credentials: "same-origin",
        cache: "no-store",
      });
      let data = {};
      try {
        data = await response.json();
      } catch (_error) {
        data = {};
      }
      if (!response.ok) {
        throw new Error(data.message || data.error || `HTTP ${response.status}`);
      }
      return data;
    }

    function makeField(labelText, control, hint = "") {
      const wrap = el("label", "form-field");
      wrap.append(el("span", "field-label", labelText));
      wrap.append(control);
      if (hint) {
        wrap.append(el("span", "field-hint", hint));
      }
      return wrap;
    }

    function makeInput(placeholder = "", value = "", type = "text") {
      const input = document.createElement("input");
      input.type = type;
      input.className = "text-input";
      input.placeholder = placeholder;
      input.value = value;
      return input;
    }

    function makeSelect(options = [], value = "") {
      const select = document.createElement("select");
      select.className = "text-input";
      options.forEach((option) => {
        const item = document.createElement("option");
        if (typeof option === "string") {
          item.value = option;
          item.textContent = option;
        } else {
          item.value = option.value;
          item.textContent = option.label;
        }
        select.append(item);
      });
      select.value = value;
      return select;
    }

    function makeTextarea(placeholder = "", value = "", rows = 4) {
      const area = document.createElement("textarea");
      area.className = "text-area";
      area.placeholder = placeholder;
      area.rows = rows;
      area.value = value;
      return area;
    }

    function makeCheckbox(labelText, checked = false) {
      const wrap = el("label", "check-row");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = checked;
      wrap.append(input);
      wrap.append(el("span", "", labelText));
      return { wrap, input };
    }

    function currentTaskForStudio() {
      if (selection.kind === "task" && selection.id) {
        const selected = getTask(selection.id);
        if (selected) return selected;
      }
      return filteredTasks().find((task) => task.active) || filteredTasks()[0] || null;
    }

    function taskTone(task) {
      if (task.blocked) return "blocked";
      if (!task.active) return "idle";
      if ((task.todo && task.todo.ratio >= 70) || normalizeText(task.state) === "doing") return "active";
      return "standby";
    }

    function attachOpenAgent(card, agentId) {
      card.classList.add("click-card");
      card.tabIndex = 0;
      card.addEventListener("click", () => openDrawer("agent", agentId));
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openDrawer("agent", agentId);
        }
      });
    }

    function attachOpenTask(card, taskId) {
      card.classList.add("click-card");
      card.tabIndex = 0;
      card.addEventListener("click", () => openDrawer("task", taskId));
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openDrawer("task", taskId);
        }
      });
    }

    function renderMetrics() {
      clearNode(refs.metricGrid);
      const metrics = [
        ["活跃任务", state.metrics.activeTasks, "仍在推进中的任务数量"],
        ["活跃 Agent", state.metrics.activeAgents, "当前正在处理或等待反馈的 Agent"],
        ["阻塞任务", state.metrics.blockedTasks, "需要用户介入或外部资源的任务"],
        ["今日完成", state.metrics.completedToday, "过去 24 小时完成的任务"],
        ["24h 接力", state.metrics.handoffs24h, "最近 24 小时 handoff 总次数"],
        ["1h 信号", state.metrics.signals1h, "最近一小时 progress 与 handoff 信号"],
      ];
      metrics.forEach(([label, value, note]) => {
        const card = el("div", "metric");
        card.append(el("div", "metric-label", label));
        card.append(el("div", "metric-value", String(value)));
        card.append(el("div", "metric-note", note));
        refs.metricGrid.append(card);
      });
    }

    function renderWorkspaceKpiCards(container, items) {
      clearNode(container);
      if (!items.length) {
        container.append(el("div", "empty", "当前还没有可展示的摘要。"));
        return;
      }
      items.forEach((item) => {
        const card = el("div", "workspace-kpi-card");
        card.append(el("span", "", item.label));
        card.append(el("strong", "", item.value));
        card.append(el("p", "", item.note));
        if (item.meta) {
          card.append(el("div", "workspace-kpi-meta", item.meta));
        }
        container.append(card);
      });
    }

    function currentTaskFilterLabel() {
      return {
        active: "活跃任务",
        blocked: "阻塞任务",
        done: "已完成",
        all: "全部任务",
      }[taskFilter] || "任务";
    }

    function renderRelaysInto(container, relays, emptyText) {
      clearNode(container);
      if (!relays.length) {
        container.append(el("div", "empty", emptyText));
        return;
      }
      relays.forEach((relay) => {
        const card = el("div", "relay");
        card.append(el("div", "relay-path", `${relay.from} → ${relay.to}`));
        card.append(el("div", "relay-count", `${relay.count} 次`));
        card.append(el("div", "relay-meta", `最近一次：${relay.lastAgo}`));
        container.append(card);
      });
    }

    function renderAgentsInto(container, agents, emptyText, limit = Infinity) {
      clearNode(container);
      const items = agents.slice(0, limit);
      if (!items.length) {
        container.append(el("div", "empty", emptyText));
        return;
      }
      items.forEach((agent) => {
        const card = el("article", "agent-card");
        attachOpenAgent(card, agent.id);

        const head = el("div", "agent-head");
        const identity = el("div");
        identity.append(el("div", "agent-title", agent.title));
        identity.append(el("div", "agent-meta", `${agent.name} · ${agent.id} · ${agent.model}`));
        head.append(identity);
        head.append(el("div", `status-pill status-${agent.status}`, agent.status));
        card.append(head);

        const facts = el("div", "agent-facts");
        [
          ["在手任务", agent.activeTasks],
          ["阻塞", agent.blockedTasks],
          ["最后信号", agent.lastSeenAgo],
        ].forEach(([label, value]) => {
          const fact = el("div", "fact");
          fact.append(el("span", "", label));
          fact.append(el("strong", "", String(value)));
          facts.append(fact);
        });
        card.append(facts);

        card.append(el("div", "focus", agent.focus || "当前没有明确的 progress signal，可以继续观察下一次推进。"));

        const actions = el("div", "agent-card-actions");
        const talkButton = el("button", supportsConversationWrite() ? "button small" : "button secondary small", supportsConversationWrite() ? "立即对话" : "查看会话");
        talkButton.type = "button";
        talkButton.addEventListener("click", (event) => {
          event.stopPropagation();
          openConversationForAgent(agent.id);
        });
        actions.append(talkButton);
        actions.append(el("span", "drawer-subtle", "默认直达该 Agent 的主会话"));
        card.append(actions);

        const pills = el("div", "pill-row");
        if ((agent.activeTaskCards || []).length) {
          agent.activeTaskCards.slice(0, 3).forEach((task) => {
            const pill = el("button", "pill drawer-link");
            pill.type = "button";
            pill.textContent = task.title;
            pill.addEventListener("click", (event) => {
              event.stopPropagation();
              openDrawer("task", task.id);
            });
            pills.append(pill);
          });
        } else {
          pills.append(el("span", "pill", "当前无在手任务"));
        }
        card.append(pills);
        container.append(card);
      });
    }

    function renderTasksInto(container, tasks, emptyText, limit = Infinity) {
      clearNode(container);
      const items = tasks.slice(0, limit);
      if (!items.length) {
        container.append(el("div", "empty", emptyText));
        return;
      }
      items.forEach((task) => {
        const card = el("article", `task-card${task.blocked ? " blocked" : ""}`);
        attachOpenTask(card, task.id);

        const head = el("div", "task-head");
        const titleWrap = el("div");
        titleWrap.append(el("div", "task-title", task.title));
        titleWrap.append(el("div", "task-sub", `${task.id} · 当前负责人：${task.currentAgentLabel || task.org || "未知"} · ${task.updatedAgo}`));
        head.append(titleWrap);
        head.append(el("div", `status-pill status-${taskTone(task)}`, task.state));
        card.append(head);

        const progressTrack = el("div", "progress-track");
        const progressFill = el("div", "progress-fill");
        progressFill.style.width = `${task.todo.ratio || 0}%`;
        progressTrack.append(progressFill);
        card.append(progressTrack);

        const todoRow = el("div", "todo-row");
        todoRow.textContent = task.todo.total
          ? `Todo 完成 ${task.todo.completed} / ${task.todo.total}`
          : "当前还没有拆出 todos，可以继续观察下一次 progress 更新。";
        card.append(todoRow);

        const update = el("div", "task-copy");
        update.append(el("strong", "", "当前焦点"));
        update.append(el("div", "", task.currentUpdate || "暂时没有进展描述"));
        card.append(update);

        const route = el("div", "route");
        if ((task.route || []).length) {
          task.route.forEach((step) => route.append(el("span", "route-step", step)));
        } else {
          route.append(el("span", "route-step", "还没有形成流转路径"));
        }
        card.append(route);
        container.append(card);
      });
    }

    function renderEventsInto(container, events, emptyText, limit = Infinity) {
      clearNode(container);
      const items = events.slice(0, limit);
      if (!items.length) {
        container.append(el("div", "empty", emptyText));
        return;
      }
      items.forEach((event) => {
        const item = el("article", `event event-${event.type}`);
        if (event.taskId) {
          item.classList.add("click-card");
          item.tabIndex = 0;
          item.addEventListener("click", () => openDrawer("task", event.taskId));
          item.addEventListener("keydown", (keyboardEvent) => {
            if (keyboardEvent.key === "Enter" || keyboardEvent.key === " ") {
              keyboardEvent.preventDefault();
              openDrawer("task", event.taskId);
            }
          });
        }
        const head = el("div", "event-head");
        const title = el("div");
        title.append(el("div", "event-title", event.headline));
        title.append(el("div", "event-detail", `${event.taskId} · ${event.title}`));
        head.append(title);
        head.append(el("div", "event-meta", event.at ? formatClock(event.at) : "未知时间"));
        item.append(head);
        if (event.detail) {
          item.append(el("div", "event-detail", event.detail));
        }
        container.append(item);
      });
    }

    function renderCommandCards(container, commands, emptyText) {
      clearNode(container);
      if (!commands.length) {
        container.append(el("div", "empty", emptyText));
        return;
      }
      commands.forEach((command) => {
        const card = el("div", "command-card");
        card.append(el("div", "deliverable-title", command.label));
        card.append(el("div", "command-desc", command.description));
        card.append(el("div", "code-line", command.command));
        const actions = el("div", "panel-actions");
        actions.append(makeCopyButton(command.command));
        card.append(actions);
        container.append(card);
      });
    }

    function renderDeliverables() {
      clearNode(refs.deliverablesList);
      const items = filteredDeliverables();
      if (!items.length) {
        refs.deliverablesList.append(el("div", "empty", "当前还没有可展示的交付物。任务完成后，产出路径会在这里聚合。"));
        return;
      }
      items.forEach((item) => {
        const card = el("div", "deliverable-card");
        const head = el("div", "deliverable-head");
        const left = el("div");
        left.append(el("div", "deliverable-title", item.title));
        left.append(el("div", "list-meta", `${item.id} · ${item.state} · ${item.updatedAgo}`));
        head.append(left);
        head.append(el("div", "theme-badge", item.state));
        card.append(head);
        card.append(el("div", "command-desc", item.summary || "暂无交付摘要"));
        if (item.output) {
          card.append(el("div", "path-line", item.output));
        }
        const actions = el("div", "panel-actions");
        const openTaskButton = el("button", "button secondary", "打开任务回放");
        openTaskButton.type = "button";
        openTaskButton.addEventListener("click", () => openDrawer("task", item.id));
        actions.append(openTaskButton);
        if (item.output) {
          actions.append(makeCopyButton(item.output, "复制路径"));
        }
        card.append(actions);
        refs.deliverablesList.append(card);
      });
    }

    function renderTaskActionStudio() {
      clearNode(refs.taskActionStudio);
      const createCard = el("section", "studio-card");
      createCard.append(el("div", "studio-eyebrow", "Quick Create"));
      createCard.append(el("div", "deliverable-title", "直接发起一条新任务"));
      createCard.append(el("div", "studio-copy", "适合你已经明确想推进的事项。创建后任务会直接进入规划链路，你可以立刻打开抽屉继续补进展。"));

      if (!supportsActions()) {
        createCard.append(el("div", "empty", "请通过 `--serve` 启动本地产品并登录后再执行操作。"));
        refs.taskActionStudio.append(createCard);
      } else {
        const form = el("form", "studio-form");
        const titleInput = makeTextarea("例如：整理 1.10.0 发布后的客户答疑 FAQ", "", 3);
        const briefInput = makeTextarea("给协同链路补充一句背景、目标或优先级说明", "", 4);
        const submit = el("button", "button", "创建并进入任务");
        submit.type = "submit";
        const inline = el("div", "status-inline", "系统会自动生成任务号并放入当前主题的规划入口。");

        form.append(makeField("任务标题", titleInput, "标题尽量写成可执行任务，不要只是关键词。"));
        form.append(makeField("背景说明", briefInput, "可选。它会成为任务的首条说明，帮助后续 Agent 更快接手。"));

        const footer = el("div", "action-footer");
        footer.append(submit);
        footer.append(inline);
        form.append(footer);

        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          const title = titleInput.value.trim();
          const remark = briefInput.value.trim();
          if (!title) {
            inline.textContent = "请先写一个明确的任务标题。";
            showToast("请先写一个明确的任务标题。", "warn");
            return;
          }
          setButtonBusy(submit, true, "创建中...");
          inline.textContent = "正在创建任务并刷新协同视图。";
          try {
            const data = await postActionJson("/api/actions/task/create", { title, remark });
            titleInput.value = "";
            briefInput.value = "";
            inline.textContent = data.message || "任务已创建。";
            showToast(data.message || "任务已创建。", "success");
            if (data.taskId) {
              openDrawer("task", data.taskId);
            }
          } catch (error) {
            inline.textContent = error.message;
            showToast(error.message, "error");
          } finally {
            setButtonBusy(submit, false);
          }
        });

        createCard.append(form);
        refs.taskActionStudio.append(createCard);
      }

      const currentTask = currentTaskForStudio();
      const guideCard = el("section", "studio-card");
      guideCard.append(el("div", "studio-eyebrow", "Live Context"));
      if (!currentTask) {
        guideCard.append(el("div", "deliverable-title", "还没有焦点任务"));
        guideCard.append(el("div", "studio-copy", "你可以先创建一条任务，或者从下面的任务河道中打开一条已有任务。任务抽屉里已经集成了推进、阻塞和完成操作。"));
      } else {
        guideCard.append(el("div", "deliverable-title", currentTask.title));
        guideCard.append(el("div", "selection-meta", `${currentTask.id} · ${currentTask.state} · 当前负责人 ${currentTask.currentAgentLabel || currentTask.org || "未知"}`));
        guideCard.append(el("div", "studio-copy", currentTask.currentUpdate || "这条任务还没有最近进展说明。"));
        const actions = el("div", "panel-actions");
        const open = el("button", "button secondary", "打开任务抽屉");
        open.type = "button";
        open.addEventListener("click", () => openDrawer("task", currentTask.id));
        actions.append(open);
        guideCard.append(actions);
      }
      refs.taskActionStudio.append(guideCard);
    }

    function renderTaskFocusCard() {
      clearNode(refs.taskFocusCard);
      const task = currentTaskForStudio();
      const card = el("div", "selection-card");
      if (!task) {
        card.append(el("div", "studio-eyebrow", "Focus"));
        card.append(el("div", "selection-title", "先选一条任务"));
        card.append(el("div", "selection-meta", "点开任务卡片后，这里会汇总它的状态、Todo 进度和路线。"));
        refs.taskFocusCard.append(card);
        return;
      }

      card.append(el("div", "studio-eyebrow", "Focus"));
      card.append(el("div", "selection-title", task.title));
      card.append(el("div", "selection-meta", `${task.id} · ${task.state} · 最近更新 ${task.updatedAgo}`));

      const stats = el("div", "selection-stats");
      [
        ["负责人", task.currentAgentLabel || task.org || "未知"],
        ["Todo", task.todo.total ? `${task.todo.completed}/${task.todo.total}` : "未拆分"],
        ["路由", (task.route || []).length ? `${task.route.length} 步` : "未形成"],
      ].forEach(([label, value]) => {
        const stat = el("div", "selection-stat");
        stat.append(el("span", "", label));
        stat.append(el("strong", "", String(value)));
        stats.append(stat);
      });
      card.append(stats);

      const focus = el("div", "studio-copy", task.currentUpdate || "这条任务还没有最近进展说明。");
      card.append(focus);

      const route = el("div", "drawer-chip-row");
      if ((task.route || []).length) {
        task.route.forEach((step) => route.append(el("span", "drawer-chip", step)));
      } else {
        route.append(el("span", "drawer-chip", "还没有形成流转路径"));
      }
      card.append(route);

      const actions = el("div", "panel-actions");
      const open = el("button", "button", "进入任务操作");
      open.type = "button";
      open.addEventListener("click", () => openDrawer("task", task.id));
      actions.append(open);
      if (task.output) {
        actions.append(makeCopyButton(task.output, "复制产出路径"));
      }
      card.append(actions);
      refs.taskFocusCard.append(card);
    }

    function renderThemes() {
      clearNode(refs.currentThemeSummary);
      clearNode(refs.themeGrid);
      const currentTheme = (state.themeCatalog || []).find((theme) => theme.current) || null;
      if (currentTheme) {
        const summary = el("div", "deliverable-card");
        summary.append(el("div", "deliverable-title", currentTheme.displayName));
        summary.append(el("div", "command-desc", currentTheme.summary));
        summary.append(el("div", "path-line", `适合：${currentTheme.bestFor}`));
        summary.append(el("div", "path-line", `组织气质：${currentTheme.tagline}`));
        summary.append(el("div", "path-line", `产品版本：${runtimeCaps().productVersion || PRODUCT_VERSION}`));
        summary.append(el("div", "path-line", supportsThemeSwitch() ? "可直接在这里切换主题" : "当前运行环境未暴露主题切换能力"));
        refs.currentThemeSummary.append(summary);
      }
      if (!(state.themeCatalog || []).length) {
        refs.themeGrid.append(el("div", "empty", "当前没有可用主题目录。"));
        return;
      }
      (state.themeCatalog || []).forEach((theme) => {
        const card = el("article", "theme-card");
        card.dataset.current = theme.current ? "true" : "false";
        const head = el("div", "theme-head");
        const titleWrap = el("div");
        titleWrap.append(el("div", "theme-title", theme.displayName));
        titleWrap.append(el("div", "list-meta", theme.tagline));
        head.append(titleWrap);
        head.append(el("div", "theme-badge", theme.current ? "当前主题" : theme.name));
        card.append(head);
        card.append(el("div", "command-desc", theme.summary));
        card.append(el("div", "path-line", `适合场景：${theme.bestFor}`));
        const actions = el("div", "theme-card-actions");
        if (theme.current) {
          actions.append(el("span", "theme-badge", "当前使用"));
        } else if (supportsThemeSwitch()) {
          const button = el("button", "button", "切换到此主题");
          button.type = "button";
          button.addEventListener("click", async () => {
            setButtonBusy(button, true, "切换中...");
            try {
              const data = await postActionJson("/api/actions/theme/switch", { theme: theme.name });
              showToast(data.message || `已切换到 ${theme.displayName}`, "success");
            } catch (error) {
              showToast(error.message, "error");
            } finally {
              setButtonBusy(button, false);
            }
          });
          actions.append(button);
        } else {
          actions.append(el("div", "status-inline", "该环境只能查看主题，不能在产品内切换。"));
        }
        card.append(actions);
        refs.themeGrid.append(card);
      });
    }

    function renderAdminView() {
      const admin = state.admin || {};
      const instances = admin.instances || [];
      const users = admin.users || [];
      const hasSeatVisibility = hasPermission("auditView") || hasPermission("adminWrite");
      const userOptions = users.map((user) => ({
        value: user.username,
        label: `${user.displayName} · ${user.username}`,
      }));
      clearNode(refs.adminSummaryList);
      clearNode(refs.adminRoleList);
      clearNode(refs.adminInstanceList);
      clearNode(refs.adminInstanceStudio);
      clearNode(refs.adminUserList);
      clearNode(refs.adminUserStudio);
      clearNode(refs.adminAuditFeed);

      const summaries = [
        {
          title: "安装舰队",
          body: `已登记 ${(admin.instanceSummary || {}).total || 0} 套安装`,
          meta: `可达 ${(admin.instanceSummary || {}).reachable || 0} · 缺失 ${(admin.instanceSummary || {}).missing || 0} · 异常 ${(admin.instanceSummary || {}).broken || 0}`,
        },
        {
          title: "现场负载",
          body: `${(admin.instanceSummary || {}).activeTasks || 0} 个活跃任务`,
          meta: "把实例活跃度和阻塞态放到同一个经营视角里持续观察。",
        },
        {
          title: "团队席位",
          body: `${(admin.seatSummary || {}).total || 0} 个账号已启用`,
          meta: `Owner ${(admin.seatSummary || {}).owner || 0} · Operator ${(admin.seatSummary || {}).operator || 0} · Viewer ${(admin.seatSummary || {}).viewer || 0}`,
        },
        {
          title: "治理动作",
          body: `${(admin.seatSummary || {}).actions24h || 0} 条操作 / 24h`,
          meta: `失败登录 ${(admin.seatSummary || {}).failedLogins24h || 0} 次`,
        },
        {
          title: "席位状态",
          body: `激活 ${(admin.seatSummary || {}).active || 0} · 停用 ${(admin.seatSummary || {}).suspended || 0}`,
          meta: hasSeatVisibility ? "Owner 可以直接在这里调整角色、停用席位和重置密码。" : "当前账号只看到聚合统计，不暴露具体席位名单。",
        },
        {
          title: "源仓库目录",
          body: (admin.workspace || {}).projectDir ? "已连接仓库源目录" : "仓库目录缺失",
          meta: "主题切换和运行时脚本会使用这个源目录。",
        },
        {
          title: "产品数据内核",
          body: (admin.workspace || {}).storagePath ? "SQLite 产品内核在线" : "数据库路径缺失",
          meta: "1.14.0 起账号与审计优先走 SQLite 存储层，而不是分散的 JSON 文件。",
        },
      ];
      summaries.forEach((item) => {
        const card = el("div", "admin-kpi-card");
        card.append(el("span", "", item.title));
        card.append(el("strong", "", item.body));
        card.append(el("p", "", item.meta));
        if (item.title === "源仓库目录" && (admin.workspace || {}).projectDir) {
          card.append(el("div", "admin-kpi-meta", (admin.workspace || {}).projectDir));
        } else if (item.title === "产品数据内核" && (admin.workspace || {}).storagePath) {
          card.append(el("div", "admin-kpi-meta", (admin.workspace || {}).storagePath));
        } else if (item.title === "现场负载") {
          card.append(el("div", "admin-kpi-meta", `阻塞任务 ${(admin.instanceSummary || {}).blockedTasks || 0} 个`));
        } else {
          card.append(el("div", "admin-kpi-meta", item.meta));
        }
        refs.adminSummaryList.append(card);
      });

      (admin.roleMatrix || []).forEach((role) => {
        const card = el("div", "admin-role-card");
        card.append(el("div", "deliverable-title", `${role.label} · ${role.role}`));
        card.append(el("p", "", role.description));
        const chips = el("div", "drawer-chip-row");
        [
          ["读数据", role.permissions.read],
          ["任务动作", role.permissions.taskWrite],
          ["会话对话", role.permissions.conversationWrite],
          ["主题切换", role.permissions.themeWrite],
          ["成员管理", role.permissions.adminWrite],
          ["审计查看", role.permissions.auditView],
        ].forEach(([label, enabled]) => {
          chips.append(el("span", "drawer-chip", `${label} · ${enabled ? "允许" : "禁止"}`));
        });
        card.append(chips);
        refs.adminRoleList.append(card);
      });
      if (!(admin.roleMatrix || []).length) {
        refs.adminRoleList.append(el("div", "empty", "当前还没有角色矩阵数据。"));
      }

      if (!instances.length) {
        refs.adminInstanceList.append(el("div", "empty", "当前还没有登记任何 OpenClaw 安装实例。"));
      } else {
        instances.forEach((instance) => {
          const card = el("div", "admin-instance-card");
          const head = el("div", "deliverable-head");
          const left = el("div");
          left.append(el("div", "deliverable-title", instance.label || instance.openclawDir));
          left.append(el("div", "list-meta", `${instance.themeLabel || instance.theme || "未知主题"} · ${instance.routerAgentId || "未知路由 Agent"}`));
          head.append(left);
          const toneMap = { current: "active", ready: "standby", broken: "blocked", missing: "blocked" };
          head.append(el("div", `status-pill status-${toneMap[instance.status] || "idle"}`, instance.statusLabel || instance.status || "未知"));
          card.append(head);
          card.append(el("p", "", instance.statusNote || "本地安装实例。"));
          card.append(el("div", "admin-instance-path", instance.openclawDir || "未记录目录"));
          if (instance.projectDir) {
            card.append(el("div", "admin-instance-path", `源仓库：${instance.projectDir}`));
          }
          const facts = el("div", "admin-instance-facts");
          [
            ["Agents", `${instance.agentCount || 0} 个`],
            ["Active", `${instance.activeTasks || 0} 个`],
            ["Blocked", `${instance.blockedTasks || 0} 个`],
            ["Snapshot", instance.updatedAgo || "等待快照"],
          ].forEach(([label, value]) => {
            const fact = el("div", "admin-mini-stat");
            fact.append(el("span", "", label));
            fact.append(el("strong", "", String(value)));
            facts.append(fact);
          });
          card.append(facts);
          const actions = el("div", "action-footer");
          actions.append(makeCopyButton(instance.openclawDir || "", "复制目录"));
          if (instance.projectDir) {
            actions.append(makeCopyButton(instance.projectDir, "复制仓库路径"));
          }
          if (hasPermission("adminWrite") && !instance.current) {
            const removeButton = el("button", "button secondary small", "移除登记");
            removeButton.type = "button";
            removeButton.addEventListener("click", async () => {
              setButtonBusy(removeButton, true, "移除中...");
              try {
                const data = await postActionJson("/api/actions/admin/instance/remove", {
                  openclawDir: instance.openclawDir,
                });
                showToast(data.message || "安装实例已移除。", "success");
              } catch (error) {
                showToast(error.message, "error");
              } finally {
                setButtonBusy(removeButton, false);
              }
            });
            actions.append(removeButton);
          }
          card.append(actions);
          refs.adminInstanceList.append(card);
        });
      }

      if (!hasPermission("adminWrite")) {
        refs.adminInstanceStudio.append(el("div", "empty", "只有 Owner 可以登记和维护安装实例。"));
      } else {
        const instanceCard = el("section", "studio-card");
        instanceCard.append(el("div", "studio-eyebrow", "Fleet Registry"));
        instanceCard.append(el("div", "deliverable-title", "登记新的 OpenClaw 安装"));
        instanceCard.append(el("div", "studio-copy", "输入另一套本地 OpenClaw 安装目录，Mission Control 会读取它的配置、主题和任务状态，把它纳入当前控制平面。"));
        const form = el("form", "studio-form");
        const labelInput = makeInput("例如：深圳交付中心", "", "text");
        const dirInput = makeInput("/Users/you/.openclaw-staging", "", "text");
        const submit = el("button", "button", "登记实例");
        submit.type = "submit";
        const inline = el("div", "status-inline", "需要目标目录里已有 openclaw.json。当前实例会自动同步，不需要手动重复登记。");
        form.append(makeField("显示名称", labelInput, "可选。留空时会自动用该实例主题名或目录名。"));
        form.append(makeField("OpenClaw 目录", dirInput, "例如另一套 `~/.openclaw-*` 安装。当前版本先支持本机本地路径。"));
        const footer = el("div", "action-footer");
        footer.append(submit);
        footer.append(inline);
        form.append(footer);
        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          if (!dirInput.value.trim()) {
            inline.textContent = "请先输入 OpenClaw 安装目录。";
            showToast("请先输入 OpenClaw 安装目录。", "warn");
            return;
          }
          setButtonBusy(submit, true, "登记中...");
          inline.textContent = "正在读取并登记安装实例。";
          try {
            const data = await postActionJson("/api/actions/admin/instance/register", {
              openclawDir: dirInput.value.trim(),
              label: labelInput.value.trim(),
            });
            inline.textContent = data.message || "安装实例已登记。";
            showToast(data.message || "安装实例已登记。", "success");
            labelInput.value = "";
            dirInput.value = "";
          } catch (error) {
            inline.textContent = error.message;
            showToast(error.message, "error");
          } finally {
            setButtonBusy(submit, false);
          }
        });
        instanceCard.append(form);
        refs.adminInstanceStudio.append(instanceCard);
      }

      if (!users.length) {
        const message = admin.hasUsers && !hasSeatVisibility
          ? "团队席位已经启用，但当前账号没有查看具体名单的权限。"
          : "还没有团队账号。建议先用 Owner Token 进入，然后创建首个 owner / operator / viewer 席位。";
        refs.adminUserList.append(el("div", "empty", message));
      } else {
        users.forEach((user) => {
          const card = el("div", "admin-user-card");
          const head = el("div", "deliverable-head");
          const left = el("div");
          left.append(el("div", "deliverable-title", user.displayName));
          left.append(el("div", "list-meta", `${user.username} · ${user.roleLabel}`));
          head.append(left);
          head.append(el("div", "theme-badge", user.status || "active"));
          card.append(head);
          const grid = el("div", "admin-user-grid");
          const primary = el("div");
          primary.append(el("p", "", user.roleDescription || "团队成员"));
          primary.append(el("div", "list-meta", `最近登录 ${user.lastLoginAt ? formatClock(user.lastLoginAt) : "还没有"}`));
          grid.append(primary);
          const meta = el("div", "admin-section-meta");
          [
            `角色 ${user.roleLabel || user.role || "未知"}`,
            `状态 ${user.status || "active"}`,
            `创建于 ${user.createdAt ? formatClock(user.createdAt) : "未知时间"}`,
          ].forEach((label) => meta.append(el("span", "drawer-chip", label)));
          grid.append(meta);
          card.append(grid);
          refs.adminUserList.append(card);
        });
      }

      if (!hasPermission("adminWrite")) {
        refs.adminUserStudio.append(el("div", "empty", "只有 Owner 可以在这里创建和管理团队席位。"));
      } else {
        const createCard = el("section", "studio-card");
        createCard.append(el("div", "studio-eyebrow", "Seat Provisioning"));
        createCard.append(el("div", "deliverable-title", "新增团队成员"));
        createCard.append(el("div", "studio-copy", "商业后台开始按席位和角色运转。这里创建的账号可以直接用用户名和密码登录。"));

        const form = el("form", "studio-form");
        const nameInput = makeInput("例如：Alice Zhang", "", "text");
        const userInput = makeInput("例如：alice 或 alice@company", "", "text");
        const roleInput = makeSelect([
          { value: "owner", label: "Owner" },
          { value: "operator", label: "Operator" },
          { value: "viewer", label: "Viewer" },
        ], "operator");
        const passwordInput = makeInput("至少 8 位密码", "", "password");
        const submit = el("button", "button", "创建席位");
        submit.type = "submit";
        const inline = el("div", "status-inline", "创建后会立刻写入团队账号库，并留下审计记录。");
        form.append(makeField("显示名称", nameInput, "用于顶部身份显示和审计日志。"));
        form.append(makeField("登录名", userInput, "建议用稳定的用户名或邮箱。"));
        form.append(makeField("角色", roleInput, "建议把日常运营同学放在 Operator，把只读看板同学放在 Viewer。"));
        form.append(makeField("初始密码", passwordInput, "建议后续再通过管理流程重置。"));
        const footer = el("div", "action-footer");
        footer.append(submit);
        footer.append(inline);
        form.append(footer);

        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          const payload = {
            displayName: nameInput.value.trim(),
            username: userInput.value.trim(),
            role: roleInput.value.trim().toLowerCase(),
            password: passwordInput.value.trim(),
          };
          if (!payload.username || !payload.role || !payload.password) {
            inline.textContent = "登录名、角色和密码都不能为空。";
            showToast("登录名、角色和密码都不能为空。", "warn");
            return;
          }
          setButtonBusy(submit, true, "创建中...");
          inline.textContent = "正在创建团队席位。";
          try {
            const data = await postActionJson("/api/actions/admin/user/create", payload);
            inline.textContent = data.message || "团队成员已创建。";
            showToast(data.message || "团队成员已创建。", "success");
            nameInput.value = "";
            userInput.value = "";
            roleInput.value = "operator";
            passwordInput.value = "";
          } catch (error) {
            inline.textContent = error.message;
            showToast(error.message, "error");
          } finally {
            setButtonBusy(submit, false);
          }
        });

        createCard.append(form);
        refs.adminUserStudio.append(createCard);

        const accessCard = el("section", "studio-card");
        accessCard.append(el("div", "studio-eyebrow", "Seat Governance"));
        accessCard.append(el("div", "deliverable-title", "调整角色与席位状态"));
        accessCard.append(el("div", "studio-copy", "这里可以直接升降权限、停用席位，也会自动阻止你把最后一个活跃 Owner 锁死。"));

        if (!userOptions.length) {
          accessCard.append(el("div", "empty", "先创建至少一个团队账号，才能继续做治理动作。"));
        } else {
          const accessForm = el("form", "studio-form");
          const accountInput = makeSelect(userOptions, userOptions[0].value);
          const accessRoleInput = makeSelect([
            { value: "owner", label: "Owner" },
            { value: "operator", label: "Operator" },
            { value: "viewer", label: "Viewer" },
          ], users[0].role || "operator");
          const statusInput = makeSelect([
            { value: "active", label: "激活" },
            { value: "suspended", label: "停用" },
          ], users[0].status || "active");
          const accessSubmit = el("button", "button", "应用席位变更");
          accessSubmit.type = "submit";
          const accessInline = el("div", "status-inline", "角色和账号状态会一起更新，并留下审计记录。");

          const syncAccessFields = () => {
            const selected = users.find((user) => user.username === accountInput.value);
            if (!selected) return;
            accessRoleInput.value = selected.role || "viewer";
            statusInput.value = selected.status || "active";
          };
          accountInput.addEventListener("change", syncAccessFields);
          syncAccessFields();

          accessForm.append(makeField("团队账号", accountInput, "建议优先管理真人席位，不要频繁复用共享账号。"));
          accessForm.append(makeField("角色", accessRoleInput, "Owner 具备完整治理权限，Operator 负责日常运行，Viewer 只读。"));
          accessForm.append(makeField("账号状态", statusInput, "停用后，该账号无法继续登录 Mission Control。"));
          const accessFooter = el("div", "action-footer");
          accessFooter.append(accessSubmit);
          accessFooter.append(accessInline);
          accessForm.append(accessFooter);

          accessForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            setButtonBusy(accessSubmit, true, "应用中...");
            accessInline.textContent = "正在更新席位治理配置。";
            try {
              const data = await postActionJson("/api/actions/admin/user/update_access", {
                username: accountInput.value,
                role: accessRoleInput.value,
                status: statusInput.value,
              });
              accessInline.textContent = data.message || "席位配置已更新。";
              showToast(data.message || "席位配置已更新。", "success");
            } catch (error) {
              accessInline.textContent = error.message;
              showToast(error.message, "error");
            } finally {
              setButtonBusy(accessSubmit, false);
            }
          });

          accessCard.append(accessForm);
        }
        refs.adminUserStudio.append(accessCard);

        const resetCard = el("section", "studio-card");
        resetCard.append(el("div", "studio-eyebrow", "Credential Care"));
        resetCard.append(el("div", "deliverable-title", "重置团队账号密码"));
        resetCard.append(el("div", "studio-copy", "当席位需要交接或密码泄露时，可以在这里快速重置，并让审计链路留下完整记录。"));

        if (!userOptions.length) {
          resetCard.append(el("div", "empty", "当前还没有可重置密码的团队账号。"));
        } else {
          const resetForm = el("form", "studio-form");
          const resetAccountInput = makeSelect(userOptions, userOptions[0].value);
          const resetPasswordInput = makeInput("新的密码，至少 8 位", "", "password");
          const resetSubmit = el("button", "button", "重置密码");
          resetSubmit.type = "submit";
          const resetInline = el("div", "status-inline", "密码会重新哈希后写入账号库，不会以明文保存在仓库里。");

          resetForm.append(makeField("团队账号", resetAccountInput, "请选择要重置密码的席位。"));
          resetForm.append(makeField("新密码", resetPasswordInput, "建议用临时强密码，后续再通过企业流程换成个人密码。"));
          const resetFooter = el("div", "action-footer");
          resetFooter.append(resetSubmit);
          resetFooter.append(resetInline);
          resetForm.append(resetFooter);

          resetForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (!resetPasswordInput.value.trim()) {
              resetInline.textContent = "请先输入新的密码。";
              showToast("请先输入新的密码。", "warn");
              return;
            }
            setButtonBusy(resetSubmit, true, "重置中...");
            resetInline.textContent = "正在重置密码。";
            try {
              const data = await postActionJson("/api/actions/admin/user/reset_password", {
                username: resetAccountInput.value,
                password: resetPasswordInput.value.trim(),
              });
              resetPasswordInput.value = "";
              resetInline.textContent = data.message || "密码已重置。";
              showToast(data.message || "密码已重置。", "success");
            } catch (error) {
              resetInline.textContent = error.message;
              showToast(error.message, "error");
            } finally {
              setButtonBusy(resetSubmit, false);
            }
          });

          resetCard.append(resetForm);
        }
        refs.adminUserStudio.append(resetCard);
      }

      if (!hasPermission("auditView")) {
        refs.adminAuditFeed.append(el("div", "empty", "当前账号没有查看审计日志的权限。"));
      } else if (!(admin.auditEvents || []).length) {
        refs.adminAuditFeed.append(el("div", "empty", "当前还没有审计记录。下一次登录、任务操作或主题切换后会开始沉淀。"));
      } else {
        (admin.auditEvents || []).forEach((event) => {
          const card = el("article", `event admin-audit-event event-${event.outcome === "success" ? "progress" : "flow"}`);
          const head = el("div", "event-head");
          const title = el("div");
          title.append(el("div", "event-title", `${event.actor} · ${event.action}`));
          title.append(el("div", "event-detail", `${event.role || "unknown"} · ${event.atAgo}`));
          head.append(title);
          head.append(el("div", "event-meta", event.outcome));
          card.append(head);
          card.append(el("div", "event-detail", event.headline || "没有额外说明。"));
          const metaText = Object.entries(event.detail || {})
            .map(([key, value]) => `${key}: ${value}`)
            .join(" · ");
          if (metaText) {
            card.append(el("div", "event-detail", metaText));
          }
          refs.adminAuditFeed.append(card);
        });
      }
    }

    function renderAgentsSummary() {
      const agents = filteredAgents();
      const counts = { active: 0, waiting: 0, blocked: 0, standby: 0, idle: 0 };
      let totalActiveTasks = 0;
      let totalBlockedTasks = 0;
      let totalHandoffs = 0;
      agents.forEach((agent) => {
        counts[agent.status] = (counts[agent.status] || 0) + 1;
        totalActiveTasks += Number(agent.activeTasks || 0);
        totalBlockedTasks += Number(agent.blockedTasks || 0);
        totalHandoffs += Number(agent.handoffs24h || 0);
      });
      const mostLoaded = [...agents].sort((left, right) => {
        const leftScore = Number(left.activeTasks || 0) * 10 + Number(left.blockedTasks || 0);
        const rightScore = Number(right.activeTasks || 0) * 10 + Number(right.blockedTasks || 0);
        return rightScore - leftScore;
      })[0] || null;
      const highlighted = [...agents].find((agent) => agent.focus) || mostLoaded;
      renderWorkspaceKpiCards(refs.agentsSummaryList, [
        {
          label: "团队覆盖",
          value: `${agents.length} 个 Agent`,
          note: `推进中 ${counts.active || 0} · 待反馈 ${counts.waiting || 0} · 空闲 ${counts.idle || 0}`,
          meta: `当前路由 Agent：${state.routerAgentId || "未知"}`,
        },
        {
          label: "在手负载",
          value: `${totalActiveTasks} 个任务`,
          note: `阻塞 ${totalBlockedTasks} · 24h 接力 ${totalHandoffs}`,
          meta: mostLoaded ? `当前最忙：${mostLoaded.title} · ${mostLoaded.activeTasks} 个在手任务` : "当前没有高负载 Agent。",
        },
        {
          label: "信号温度",
          value: `${(counts.active || 0) + (counts.standby || 0)} 个有现场感`,
          note: `待命 ${counts.standby || 0} · 阻塞 ${counts.blocked || 0}`,
          meta: highlighted ? `${highlighted.title}：${highlighted.focus || "最近有新的 progress signal。"}` : "等待新的 progress signal。",
        },
        {
          label: "运营重点",
          value: mostLoaded ? mostLoaded.title : "暂无高压点",
          note: mostLoaded ? `${mostLoaded.name} · 最近信号 ${mostLoaded.lastSeenAgo}` : "当前所有 Agent 负载比较均衡。",
          meta: mostLoaded ? `${mostLoaded.blockedTasks || 0} 个阻塞 · ${mostLoaded.handoffs24h || 0} 次接力` : "继续观察任务流入和状态变化。",
        },
      ]);
    }

    function renderTasksSummary() {
      const tasks = filteredTasks();
      const activeCount = tasks.filter((task) => task.active).length;
      const blockedCount = tasks.filter((task) => task.blocked).length;
      const doneCount = tasks.filter((task) => normalizeText(task.state) === "done").length;
      const ratios = tasks.map((task) => Number((task.todo || {}).ratio || 0));
      const averageRatio = ratios.length ? Math.round(ratios.reduce((sum, value) => sum + value, 0) / ratios.length) : 0;
      const mostAdvanced = [...tasks].sort((left, right) => Number((right.todo || {}).ratio || 0) - Number((left.todo || {}).ratio || 0))[0] || null;
      const focusTask = currentTaskForStudio();
      renderWorkspaceKpiCards(refs.tasksSummaryList, [
        {
          label: "筛选结果",
          value: `${tasks.length} 条任务`,
          note: `当前视图：${currentTaskFilterLabel()} · 交付物 ${filteredDeliverables().length} 个`,
          meta: tasks.length ? "先看聚焦任务，再判断要推进还是归档。" : "当前筛选下还没有任务。",
        },
        {
          label: "执行状态",
          value: `${activeCount} 条在推进`,
          note: `阻塞 ${blockedCount} · 已完成 ${doneCount}`,
          meta: activeCount ? "交付河道里仍有真实推进信号。" : "当前没有活跃中的任务。",
        },
        {
          label: "Todo 体感",
          value: `${averageRatio}% 平均完成度`,
          note: mostAdvanced ? `最高进度 ${mostAdvanced.todo?.ratio || 0}% · ${mostAdvanced.id}` : "当前没有可计算的 Todo 进度。",
          meta: mostAdvanced ? mostAdvanced.title : "任务还没形成明确的 Todo 拆分。",
        },
        {
          label: "焦点任务",
          value: focusTask ? focusTask.id : "尚未选中",
          note: focusTask ? `${focusTask.title} · ${focusTask.currentAgentLabel || focusTask.org || "未知负责人"}` : "打开任务卡片后，这里会跟着变化。",
          meta: focusTask ? (focusTask.currentUpdate || "当前没有最近进展说明。") : "先从执行台里点开一条任务。",
        },
      ]);
    }

    function renderStatusStrip() {
      clearNode(refs.agentStatusStrip);
      const counts = { active: 0, waiting: 0, blocked: 0, standby: 0, idle: 0 };
      filteredAgents().forEach((agent) => {
        counts[agent.status] = (counts[agent.status] || 0) + 1;
      });
      [
        ["推进中", counts.active, "有明确 progress signal，正在推进任务。"],
        ["待反馈", counts.waiting, "手里有任务，但最近没有新的推进信号。"],
        ["阻塞", counts.blocked, "存在阻塞任务，通常需要额外资源或用户判断。"],
        ["待命", counts.standby, "最近有活动或刚结束一轮接力。"],
        ["空闲", counts.idle, "当前没有活跃任务，也没有新的工作区信号。"],
      ].forEach(([label, value, note]) => {
        const card = el("div", "status-card");
        card.append(el("span", "", label));
        card.append(el("strong", "", String(value)));
        card.append(el("div", "status-note", note));
        refs.agentStatusStrip.append(card);
      });
    }

    function renderTaskFilters() {
      clearNode(refs.taskFilterRow);
      [
        ["active", "活跃任务"],
        ["blocked", "阻塞任务"],
        ["done", "已完成"],
        ["all", "全部任务"],
      ].forEach(([value, label]) => {
        const chip = el("button", "filter-chip", label);
        chip.type = "button";
        chip.dataset.active = String(taskFilter === value);
        chip.addEventListener("click", () => {
          taskFilter = value;
          renderAll();
        });
        refs.taskFilterRow.append(chip);
      });
    }

    function renderMeta() {
      refs.generatedAt.textContent = formatClock(state.generatedAt);
      refs.themeName.textContent = state.theme.displayName;
      refs.ownerTitle.textContent = state.ownerTitle;
      refs.installDir.textContent = state.openclawDir;
      refs.railThemeName.textContent = state.theme.displayName;
      refs.railOwnerTitle.textContent = state.ownerTitle;
      refs.railRouterAgent.textContent = state.routerAgentId || "未知";
      refs.railInstallDir.textContent = state.openclawDir;
      refs.jsonLink.href = dashboardJsonHref();
      if (supportsHttp) {
        const user = currentUser();
        refs.authStatus.textContent = `${user.displayName} · ${user.roleLabel || user.role || "Viewer"}`;
      } else {
        refs.authStatus.textContent = "快照模式";
      }
      renderCommandCards(refs.railCommandList, (state.commands || []).slice(0, 2), "暂无快速动作。");
    }

    function renderTaskActionSection(task) {
      const section = el("section", "drawer-section");
      section.append(el("h3", "", "任务操作"));
      if (!supportsActions()) {
        section.append(el("div", "empty", "请通过 `--serve` 启动本地产品并登录后，再在这里直接推进任务。"));
        return section;
      }
      if (!task.active && normalizeText(task.state) === "done") {
        section.append(el("div", "empty", "这条任务已经完成。若需要继续处理，建议重新创建一条后续任务。"));
        return section;
      }

      const grid = el("div", "drawer-action-grid");

      const progressCard = el("form", "studio-card studio-form");
      progressCard.append(el("div", "studio-eyebrow", "Progress"));
      progressCard.append(el("div", "deliverable-title", "追加进展"));
      const progressInput = makeTextarea(task.currentUpdate || "例如：正在拆解接口边界，准备给工程部下发子任务", "", 4);
      const todosInput = makeInput("用 | 分隔 todos，例如：调研|设计🔄|联调", "", "text");
      const markDoing = makeCheckbox("如果这条任务已经进入执行阶段，同时把状态切到 `Doing`。", normalizeText(task.state) !== "doing");
      const progressButton = el("button", "button", "同步进展");
      progressButton.type = "submit";
      const progressStatus = el("div", "status-inline", "进展会直接写回看板，并立即刷新页面。");
      progressCard.append(makeField("最新进展", progressInput, "建议写成一句完整的话，方便用户和 Agent 一眼读懂。"));
      progressCard.append(makeField("Todo 串", todosInput, "可选。支持 `已完成✅|进行中🔄|待开始` 这种格式。"));
      progressCard.append(markDoing.wrap);
      const progressFooter = el("div", "action-footer");
      progressFooter.append(progressButton);
      progressFooter.append(progressStatus);
      progressCard.append(progressFooter);
      progressCard.addEventListener("submit", async (event) => {
        event.preventDefault();
        const message = progressInput.value.trim();
        if (!message) {
          progressStatus.textContent = "请先写一条最新进展。";
          showToast("请先写一条最新进展。", "warn");
          return;
        }
        setButtonBusy(progressButton, true, "同步中...");
        progressStatus.textContent = "正在把进展写入任务链路。";
        try {
          const data = await postActionJson("/api/actions/task/progress", {
            taskId: task.id,
            message,
            todos: todosInput.value.trim(),
            markDoing: markDoing.input.checked,
          });
          progressStatus.textContent = data.message || "进展已同步。";
          showToast(data.message || "进展已同步。", "success");
        } catch (error) {
          progressStatus.textContent = error.message;
          showToast(error.message, "error");
        } finally {
          setButtonBusy(progressButton, false);
        }
      });
      grid.append(progressCard);

      const blockCard = el("form", "studio-card studio-form");
      blockCard.append(el("div", "studio-eyebrow", "Block"));
      blockCard.append(el("div", "deliverable-title", "标记阻塞"));
      const reasonInput = makeTextarea("例如：缺少线上环境访问权限，需要用户提供账号", "", 4);
      const blockButton = el("button", "button secondary", "记录阻塞");
      blockButton.type = "submit";
      const blockStatus = el("div", "status-inline", "阻塞会在 Agent 运营和任务河道里显著标红。");
      blockCard.append(makeField("阻塞原因", reasonInput, "尽量写清缺什么资源、谁能解除阻塞。"));
      const blockFooter = el("div", "action-footer");
      blockFooter.append(blockButton);
      blockFooter.append(blockStatus);
      blockCard.append(blockFooter);
      blockCard.addEventListener("submit", async (event) => {
        event.preventDefault();
        const reason = reasonInput.value.trim();
        if (!reason) {
          blockStatus.textContent = "请先写明阻塞原因。";
          showToast("请先写明阻塞原因。", "warn");
          return;
        }
        setButtonBusy(blockButton, true, "记录中...");
        blockStatus.textContent = "正在标记阻塞。";
        try {
          const data = await postActionJson("/api/actions/task/block", { taskId: task.id, reason });
          blockStatus.textContent = data.message || "任务已标记阻塞。";
          showToast(data.message || "任务已标记阻塞。", "warn");
          reasonInput.value = "";
        } catch (error) {
          blockStatus.textContent = error.message;
          showToast(error.message, "error");
        } finally {
          setButtonBusy(blockButton, false);
        }
      });
      grid.append(blockCard);

      const doneCard = el("form", "studio-card studio-form");
      doneCard.append(el("div", "studio-eyebrow", "Done"));
      doneCard.append(el("div", "deliverable-title", "交付完成"));
      const summaryInput = makeTextarea("例如：MVP 已发布到 staging，并完成冒烟验证", "", 4);
      const outputInput = makeInput("/path/to/output 或交付链接", task.output || "", "text");
      const doneButton = el("button", "button", "标记完成");
      doneButton.type = "submit";
      const doneStatus = el("div", "status-inline", "完成后，这条任务会进入交付物列表。");
      doneCard.append(makeField("完成摘要", summaryInput, "建议把最终产出、验证结果和后续提醒写在这里。"));
      doneCard.append(makeField("产出路径", outputInput, "可选。可以是本地路径、预览链接或文档地址。"));
      const doneFooter = el("div", "action-footer");
      doneFooter.append(doneButton);
      doneFooter.append(doneStatus);
      doneCard.append(doneFooter);
      doneCard.addEventListener("submit", async (event) => {
        event.preventDefault();
        const summary = summaryInput.value.trim();
        setButtonBusy(doneButton, true, "提交中...");
        doneStatus.textContent = "正在把任务归档到交付列表。";
        try {
          const data = await postActionJson("/api/actions/task/done", {
            taskId: task.id,
            summary,
            output: outputInput.value.trim(),
          });
          doneStatus.textContent = data.message || "任务已完成。";
          showToast(data.message || "任务已完成。", "success");
        } catch (error) {
          doneStatus.textContent = error.message;
          showToast(error.message, "error");
        } finally {
          setButtonBusy(doneButton, false);
        }
      });
      grid.append(doneCard);

      section.append(grid);
      return section;
    }

    function renderDrawerList(items, emptyText, onClick) {
      const wrap = el("div", "drawer-list");
      if (!items.length) {
        wrap.append(el("div", "empty", emptyText));
        return wrap;
      }
      items.forEach((item) => {
        const box = el("div", "drawer-list-item");
        const head = el("div", "drawer-item-head");
        const button = el("button", "drawer-link drawer-item-title");
        button.type = "button";
        button.textContent = item.title || item.headline || item.id || "未命名";
        if (onClick) {
          button.addEventListener("click", () => onClick(item));
        }
        head.append(button);
        if (item.meta) {
          head.append(el("div", "drawer-item-meta", item.meta));
        }
        box.append(head);
        if (item.detail) {
          box.append(el("div", "drawer-item-detail", item.detail));
        }
        wrap.append(box);
      });
      return wrap;
    }

    function renderTodoItems(todoItems) {
      const wrap = el("div", "todo-list");
      if (!todoItems.length) {
        wrap.append(el("div", "empty", "当前还没有拆出 todo。"));
        return wrap;
      }
      todoItems.forEach((todo) => {
        const row = el("div", `todo-item todo-${todo.status}`);
        row.append(el("span", "todo-dot"));
        row.append(el("div", "todo-label", todo.title));
        row.append(el("div", "todo-status", todo.status.replace("-", " ")));
        wrap.append(row);
      });
      return wrap;
    }

    function renderTaskReplay(replay) {
      const wrap = el("div", "drawer-flow");
      if (!replay.length) {
        wrap.append(el("div", "empty", "还没有可回放的 handoff 或 progress 事件。"));
        return wrap;
      }
      replay.forEach((entry) => {
        const box = el("div", "drawer-flow-item");
        const head = el("div", "drawer-item-head");
        head.append(el("div", "drawer-item-title", entry.headline));
        head.append(el("div", "drawer-item-meta", entry.atAgo || formatClock(entry.at)));
        box.append(head);
        if (entry.detail) {
          box.append(el("div", "drawer-item-detail", entry.detail));
        }
        if (entry.kind === "handoff") {
          box.append(el("div", "drawer-item-detail", `${entry.actorLabel} → ${entry.targetLabel}`));
        } else if (entry.actorLabel) {
          box.append(el("div", "drawer-item-detail", `执行者：${entry.actorLabel}`));
        }
        wrap.append(box);
      });
      return wrap;
    }

    function renderAgentDrawer(agent) {
      refs.drawerKicker.textContent = "Agent";
      refs.drawerTitle.textContent = agent.title;
      clearNode(refs.drawerBody);

      const hero = el("div", "drawer-section");
      hero.append(el("div", "drawer-muted", `${agent.name} · ${agent.id} · ${agent.model}`));
      const meta = el("div", "drawer-meta");
      meta.append(el("span", `status-pill status-${agent.status}`, agent.status));
      meta.append(el("span", "drawer-chip", `最近信号 ${agent.lastSeenAgo}`));
      meta.append(el("span", "drawer-chip", `工作区 ${agent.workspaceLastSeenAgo}`));
      meta.append(el("span", "drawer-chip", `会话 ${agent.sessionLastSeenAgo}`));
      hero.append(meta);
      hero.append(el("div", "focus", agent.focus || "当前没有明确的 progress signal。"));
      const heroActions = el("div", "action-footer");
      const talkButton = el("button", supportsConversationWrite() ? "button" : "button secondary", supportsConversationWrite() ? `和 ${agent.title} 对话` : `查看 ${agent.title} 会话`);
      talkButton.type = "button";
      talkButton.addEventListener("click", () => openConversationForAgent(agent.id));
      heroActions.append(talkButton);
      heroActions.append(el("span", "status-inline", "直接进入该 Agent 的主会话，不需要先从会话列表里翻找。"));
      hero.append(heroActions);
      refs.drawerBody.append(hero);

      const stats = el("div", "drawer-grid");
      [
        ["活跃任务", agent.activeTasks],
        ["阻塞任务", agent.blockedTasks],
        ["24h 接力", agent.handoffs24h],
      ].forEach(([label, value]) => {
        const box = el("div", "drawer-stat");
        box.append(el("span", "", label));
        box.append(el("strong", "", String(value)));
        stats.append(box);
      });
      refs.drawerBody.append(stats);

      const tasksSection = el("section", "drawer-section");
      tasksSection.append(el("h3", "", "在手任务"));
      tasksSection.append(
        renderDrawerList(
          agent.activeTaskCards || [],
          "当前没有正在承担的活跃任务。",
          (task) => openDrawer("task", task.id),
        ),
      );
      refs.drawerBody.append(tasksSection);

      const signalsSection = el("section", "drawer-section");
      signalsSection.append(el("h3", "", "最近信号"));
      signalsSection.append(
        renderDrawerList(
          agent.recentSignals || [],
          "还没有记录到足够的协同信号。",
          (signal) => signal.taskId && openDrawer("task", signal.taskId),
        ),
      );
      refs.drawerBody.append(signalsSection);
    }

    function renderTaskDrawer(task) {
      refs.drawerKicker.textContent = "Task Replay";
      refs.drawerTitle.textContent = task.title;
      clearNode(refs.drawerBody);

      const hero = el("div", "drawer-section");
      hero.append(el("div", "drawer-muted", `${task.id} · ${task.state}`));
      const meta = el("div", "drawer-meta");
      meta.append(el("span", "drawer-chip strong", `负责人 ${task.currentAgentLabel || task.org || "未知"}`));
      meta.append(el("span", "drawer-chip", `签收 ${task.owner || "未知"}`));
      meta.append(el("span", "drawer-chip", `最近更新 ${task.updatedAgo}`));
      hero.append(meta);
      hero.append(el("div", "focus", task.currentUpdate || "当前没有进展摘要。"));
      refs.drawerBody.append(hero);

      const overview = el("section", "drawer-section");
      overview.append(el("h3", "", "任务路线"));
      const route = el("div", "drawer-chip-row");
      if ((task.route || []).length) {
        task.route.forEach((step) => route.append(el("span", "drawer-chip", step)));
      } else {
        route.append(el("span", "drawer-chip", "还没有形成流转路径"));
      }
      overview.append(route);
      refs.drawerBody.append(overview);

      const todoSection = el("section", "drawer-section");
      todoSection.append(el("h3", "", "Todo 明细"));
      const progressTrack = el("div", "progress-track");
      const progressFill = el("div", "progress-fill");
      progressFill.style.width = `${task.todo.ratio || 0}%`;
      progressTrack.append(progressFill);
      todoSection.append(progressTrack);
      todoSection.append(renderTodoItems(task.todoItems || []));
      refs.drawerBody.append(todoSection);

      refs.drawerBody.append(renderTaskActionSection(task));

      const replaySection = el("section", "drawer-section");
      replaySection.append(el("h3", "", "协同回放"));
      replaySection.append(renderTaskReplay(task.replay || []));
      refs.drawerBody.append(replaySection);
    }

    function syncDrawer() {
      if (!selection.kind || !selection.id) return;
      const item = selection.kind === "agent" ? getAgent(selection.id) : getTask(selection.id);
      if (!item) {
        closeDrawer();
        return;
      }
      if (selection.kind === "agent") {
        renderAgentDrawer(item);
      } else {
        renderTaskDrawer(item);
      }
    }

    function openDrawer(kind, id) {
      selection = { kind, id };
      refs.scrim.hidden = false;
      refs.drawer.hidden = false;
      refs.drawer.dataset.open = "true";
      refs.drawer.setAttribute("aria-hidden", "false");
      syncDrawer();
    }

    function closeDrawer() {
      selection = { kind: null, id: null };
      refs.drawer.dataset.open = "false";
      refs.drawer.setAttribute("aria-hidden", "true");
      refs.scrim.hidden = true;
    }

    function applyViewState() {
      refs.navLinks.forEach((link) => {
        link.dataset.active = String(link.dataset.view === currentView);
      });
      refs.views.forEach((view) => {
        view.hidden = view.dataset.view !== currentView;
      });
      const meta = VIEW_META[currentView] || VIEW_META.overview;
      refs.viewTitle.textContent = meta.title;
      refs.viewSubtitle.textContent = searchQuery ? `${meta.subtitle} 当前筛选：${searchQuery}` : meta.subtitle;
    }

    function renderOverview() {
      renderMetrics();
      renderRelaysInto(refs.overviewRelayGrid, state.relays || [], "最近 24 小时还没有足够的接力记录。");
      renderAgentsInto(
        refs.overviewAgentGrid,
        filteredAgents().filter((agent) => agent.activeTasks || agent.recentSignals.length),
        "当前没有符合筛选条件的 Agent 现场。",
        6,
      );
      renderTasksInto(
        refs.overviewTaskList,
        filteredTasks().filter((task) => task.active),
        "当前没有符合筛选条件的活跃任务。",
        6,
      );
      renderEventsInto(
        refs.overviewEventFeed,
        filteredEvents(),
        "还没有匹配的事件时间线。",
        10,
      );
    }

    function renderAgentsView() {
      renderAgentsSummary();
      renderStatusStrip();
      renderAgentsInto(refs.agentsPageGrid, filteredAgents(), "当前没有匹配的 Agent。");
    }

    function renderTasksView() {
      renderTasksSummary();
      renderTaskActionStudio();
      renderTaskFocusCard();
      renderTaskFilters();
      renderTasksInto(refs.tasksPageList, filteredTasks(), "当前没有匹配的任务。");
      renderDeliverables();
      renderCommandCards(refs.taskCommandList, state.commands || [], "当前没有可用命令。");
    }

    function currentConversationSession() {
      return (((state.conversations || {}).sessions) || []).find((session) => session.key === conversationState.key) || null;
    }

    function currentConversationTargetAgentId() {
      const selected = currentConversationSession();
      return (
        conversationState.preferredAgentId ||
        selected?.agentId ||
        conversationState.agentId ||
        state.routerAgentId ||
        (((state.agents || [])[0]) || {}).id ||
        ""
      );
    }

    function currentConversationTargetAgent() {
      return getAgent(currentConversationTargetAgentId());
    }

    function focusConversationComposer() {
      requestAnimationFrame(() => {
        const input = refs.conversationStudio?.querySelector("[data-conversation-compose='true']");
        if (!input) return;
        input.focus();
        input.scrollIntoView({ block: "center", behavior: "smooth" });
      });
    }

    function openConversationForAgent(agentId) {
      if (!agentId) return;
      conversationState = {
        ...conversationState,
        key: "",
        agentId: "",
        sessionId: "",
        preferredAgentId: agentId,
        mode: "agent",
        transcript: null,
        loading: false,
        error: "",
      };
      selection = { kind: "agent", id: agentId };
      closeDrawer();
      if (currentView !== "conversations") {
        navigate("conversations");
      } else {
        renderAll();
      }
      focusConversationComposer();
    }

    async function loadConversationTranscript(agentId, sessionId, sessionKey = "", forceReload = false) {
      if (!agentId || !sessionId) {
        conversationState = {
          ...conversationState,
          key: sessionKey || "",
          agentId: agentId || "",
          sessionId: sessionId || "",
          preferredAgentId: agentId || conversationState.preferredAgentId,
          mode: agentId ? "agent" : conversationState.mode,
          transcript: null,
          loading: false,
          error: "",
        };
        renderAll();
        return;
      }
      if (
        !forceReload &&
        conversationState.loading &&
        conversationState.agentId === agentId &&
        conversationState.sessionId === sessionId
      ) {
        return;
      }
      if (
        !forceReload &&
        conversationState.transcript &&
        conversationState.agentId === agentId &&
        conversationState.sessionId === sessionId
      ) {
        conversationState = { ...conversationState, key: sessionKey || conversationState.key, error: "" };
        renderAll();
        return;
      }
      conversationState = {
        ...conversationState,
        key: sessionKey || conversationState.key,
        agentId,
        sessionId,
        preferredAgentId: agentId,
        mode: "session",
        loading: true,
        error: "",
      };
      renderAll();
      try {
        const query = new URLSearchParams({ agentId, sessionId }).toString();
        const data = await getJson(`/api/conversations/transcript?${query}`);
        conversationState = {
          ...conversationState,
          key: sessionKey || conversationState.key,
          agentId,
          sessionId,
          preferredAgentId: agentId,
          mode: "session",
          transcript: data.conversation || null,
          loading: false,
          error: "",
        };
      } catch (error) {
        conversationState = {
          ...conversationState,
          key: sessionKey || conversationState.key,
          agentId,
          sessionId,
          preferredAgentId: agentId,
          mode: "session",
          transcript: null,
          loading: false,
          error: error.message,
        };
      }
      renderAll();
    }

    function ensureConversationSelection() {
      const sessions = filteredConversations();
      if (!sessions.length) {
        conversationState = { ...conversationState, key: "", agentId: "", sessionId: "", transcript: null, loading: false, error: "" };
        return;
      }
      if (conversationState.mode === "agent" && conversationState.preferredAgentId) {
        return;
      }
      const current = sessions.find((session) => session.key === conversationState.key);
      if (current) {
        if (!conversationState.transcript && !conversationState.loading) {
          void loadConversationTranscript(current.agentId, current.sessionId, current.key);
        }
        return;
      }
      const fallback = sessions[0];
      void loadConversationTranscript(fallback.agentId, fallback.sessionId, fallback.key);
    }

    function renderConversationSummary() {
      const conversations = state.conversations || {};
      const selected = currentConversationSession();
      const targetAgent = currentConversationTargetAgent();
      renderWorkspaceKpiCards(refs.conversationSummaryList, [
        {
          label: "真实会话数",
          value: `${(conversations.summary || {}).total || 0} 个`,
          note: `24 小时活跃 ${(conversations.summary || {}).active24h || 0} · 可继续对话 ${(conversations.summary || {}).talkable || 0}`,
          meta: "产品直接读取 OpenClaw sessions，而不是自建影子消息系统。",
        },
        {
          label: "当前焦点",
          value: selected ? selected.label : targetAgent ? `${targetAgent.title} 主会话` : "还没有选中会话",
          note: selected ? `${selected.agentLabel} · ${selected.updatedAgo}` : targetAgent ? `${targetAgent.id} · 现在可以直接向它发问` : "选择任意会话后，这里会显示会话上下文。",
          meta: selected ? (selected.preview || "当前没有最近摘要。") : "你也可以直接点亮某个 Agent 的主会话。",
        },
        {
          label: "对话模式",
          value: supportsConversationWrite() ? "可直接继续发问" : "当前只读",
          note: supportsConversationWrite() ? "Owner / Operator 可以直接在产品里继续向任意 Agent 发问。" : "当前账号只有查看 transcript 的权限。",
          meta: "Viewer 只读，Owner / Operator 才能把产品当作实时协作入口。",
        },
        {
          label: "接入方式",
          value: "原生 OpenClaw 会话",
          note: "产品前端直接调用 OpenClaw 的 sessions 和 agent CLI，不另建影子消息系统。",
          meta: "你看到的 transcript 来自 agents/*/sessions/*.jsonl。",
        },
      ]);
    }

    function renderConversationList() {
      clearNode(refs.conversationList);
      const conversations = state.conversations || {};
      if (!conversations.supported) {
        refs.conversationList.append(el("div", "empty", conversations.error || "当前环境无法读取 OpenClaw 会话索引。"));
        return;
      }
      const sessions = filteredConversations();
      if (!sessions.length) {
        refs.conversationList.append(el("div", "empty", "当前没有匹配搜索条件的会话。"));
        return;
      }
      sessions.forEach((session) => {
        const card = el("article", "conversation-card");
        card.dataset.active = String(session.key === conversationState.key);
        card.tabIndex = 0;
        const head = el("div", "deliverable-head");
        const left = el("div");
        left.append(el("div", "deliverable-title", session.label));
        left.append(el("div", "list-meta", `${session.agentLabel} · ${session.sourceLabel} · ${session.updatedAgo}`));
        head.append(left);
        head.append(el("div", "theme-badge", session.talkable ? "可对话" : "只读"));
        card.append(head);
        card.append(el("div", "conversation-preview", session.preview || "暂时没有可展示的消息摘要。"));
        const chips = el("div", "drawer-chip-row");
        [
          session.model || "unknown model",
          session.provider || "unknown provider",
          session.kind || "direct",
          session.abortedLastRun ? "上次异常中断" : "最近运行正常",
        ].forEach((label) => chips.append(el("span", "drawer-chip", label)));
        card.append(chips);
        const open = () => void loadConversationTranscript(session.agentId, session.sessionId, session.key, false);
        card.addEventListener("click", open);
        card.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            open();
          }
        });
        refs.conversationList.append(card);
      });
    }

    function renderConversationTranscript() {
      clearNode(refs.conversationTranscript);
      const selected = currentConversationSession();
      if (conversationState.loading) {
        refs.conversationTranscript.append(el("div", "empty", "正在载入真实会话 transcript。"));
        return;
      }
      if (conversationState.error) {
        refs.conversationTranscript.append(el("div", "empty", conversationState.error));
        return;
      }
      if (!selected || !conversationState.transcript) {
        refs.conversationTranscript.append(el("div", "empty", "先从左侧选择一个会话，或直接向某个 Agent 的主会话发起对话。"));
        return;
      }

      const summary = el("div", "transcript-summary");
      [
        ["Agent", selected.agentLabel || selected.agentId],
        ["模型", conversationState.transcript.meta?.model || selected.model || "unknown"],
        ["轮次", (conversationState.transcript.stats || {}).turns || 0],
        ["工具", (conversationState.transcript.stats || {}).toolMessages || 0],
      ].forEach(([label, value]) => {
        const box = el("div", "transcript-stat");
        box.append(el("span", "", label));
        box.append(el("strong", "", String(value)));
        summary.append(box);
      });
      refs.conversationTranscript.append(summary);

      const items = conversationState.transcript.items || [];
      if (!items.length) {
        refs.conversationTranscript.append(el("div", "empty", "该会话暂时还没有可展示的消息。"));
        return;
      }
      items.forEach((item) => {
        const row = el("article", "transcript-message");
        row.dataset.kind = item.kind || "assistant";
        if (item.error) {
          row.dataset.error = "true";
        }
        row.append(el("div", "transcript-meta", `${item.title || "消息"} · ${item.at ? formatClock(item.at) : "未知时间"}`));
        row.append(el("div", "transcript-bubble", item.text || " "));
        refs.conversationTranscript.append(row);
      });
    }

    function renderConversationStudio() {
      clearNode(refs.conversationStudio);
      const conversations = state.conversations || {};
      const selected = currentConversationSession();
      const targetAgent = currentConversationTargetAgent();

      const launchCard = el("section", "studio-card");
      launchCard.append(el("div", "studio-eyebrow", "Agent Direct"));
      launchCard.append(el("div", "deliverable-title", "和每个 Agent 单独对话"));
      launchCard.append(el("div", "studio-copy", "这里不是只有“会话列表”，而是每个 Agent 都能被单独点亮。点一下，就会把发送区切到它的主会话。"));
      const launchGrid = el("div", "agent-launch-grid");
      if ((state.agents || []).length) {
        (state.agents || []).forEach((agent) => {
          const quick = el("button", "agent-launch-card");
          quick.type = "button";
          quick.dataset.active = String(currentConversationTargetAgentId() === agent.id);
          quick.addEventListener("click", () => openConversationForAgent(agent.id));
          quick.append(el("strong", "", agent.title));
          quick.append(el("span", "", `${agent.name} · ${agent.id}`));
          const meta = el("div", "agent-launch-meta");
          meta.append(el("span", "", `${agent.activeTasks} 个在手任务`));
          meta.append(el("span", "", `最近信号 ${agent.lastSeenAgo}`));
          quick.append(meta);
          launchGrid.append(quick);
        });
      } else {
        launchGrid.append(el("div", "empty", "当前没有可供对话的 Agent。"));
      }
      launchCard.append(launchGrid);
      refs.conversationStudio.append(launchCard);

      const sessionCard = el("section", "studio-card");
      sessionCard.append(el("div", "studio-eyebrow", "Session Focus"));
      if (!selected) {
        if (targetAgent) {
          sessionCard.append(el("div", "deliverable-title", `${targetAgent.title} 主会话已就绪`));
          sessionCard.append(el("div", "selection-meta", `${targetAgent.name} · ${targetAgent.id} · ${targetAgent.model}`));
          sessionCard.append(el("div", "studio-copy", "现在发送区会默认把消息发给这个 Agent 的主会话。你也可以随时从左侧切到它最近的一条真实 session。"));
          const chips = el("div", "drawer-chip-row");
          ["主会话直达", targetAgent.status, `${targetAgent.activeTasks} 个在手任务`].forEach((label) => {
            chips.append(el("span", "drawer-chip", label));
          });
          sessionCard.append(chips);
        } else {
          sessionCard.append(el("div", "deliverable-title", "还没有选中会话"));
          sessionCard.append(el("div", "studio-copy", "你可以从左侧选择一条真实会话，或者直接发给某个 Agent 的主会话。"));
        }
      } else {
        sessionCard.append(el("div", "deliverable-title", selected.label));
        sessionCard.append(el("div", "selection-meta", `${selected.agentLabel} · ${selected.sourceLabel} · ${selected.updatedAgo}`));
        sessionCard.append(el("div", "studio-copy", selected.preview || "这条会话还没有最近摘要。"));
        const chips = el("div", "drawer-chip-row");
        [
          selected.model || "unknown model",
          selected.provider || "unknown provider",
          selected.talkable ? "可继续对话" : "当前只读",
        ].forEach((label) => chips.append(el("span", "drawer-chip", label)));
        sessionCard.append(chips);
      }
      refs.conversationStudio.append(sessionCard);

      const composeCard = el("section", "studio-card");
      composeCard.append(el("div", "studio-eyebrow", "Talk"));
      composeCard.append(el("div", "deliverable-title", "直接向 Agent 发问"));
      composeCard.append(el("div", "studio-copy", "继续当前会话时，会把消息发进选中的 session；不继续时，会默认落到所选 Agent 的主会话。现在每个 Agent 都有自己的直达入口。"));

      if (!supportsConversationWrite()) {
        composeCard.append(el("div", "empty", conversations.supported ? "当前账号只有查看 transcript 的权限。" : "当前环境还不能访问真实会话。"));
        refs.conversationStudio.append(composeCard);
        return;
      }

      const agentOptions = (state.agents || []).map((agent) => ({
        value: agent.id,
        label: `${agent.title} · ${agent.id}`,
      }));
      if (!agentOptions.length) {
        composeCard.append(el("div", "empty", "当前没有可供对话的 Agent。"));
        refs.conversationStudio.append(composeCard);
        return;
      }

      const form = el("form", "studio-form");
      const agentInput = makeSelect(agentOptions, currentConversationTargetAgentId() || state.routerAgentId || agentOptions[0].value);
      const continueCurrent = makeCheckbox("继续当前选中的真实会话", Boolean(selected?.talkable));
      continueCurrent.input.disabled = !selected?.talkable;
      const thinkingInput = makeSelect([
        { value: "off", label: "off" },
        { value: "minimal", label: "minimal" },
        { value: "low", label: "low" },
        { value: "medium", label: "medium" },
        { value: "high", label: "high" },
      ], "low");
      const messageInput = makeTextarea("例如：汇总今天尚书省还没收口的事项，并告诉我下一步该拍板什么。", "", 5);
      messageInput.dataset.conversationCompose = "true";
      const submit = el("button", "button", "发送消息");
      submit.type = "submit";
      const inline = el("div", "status-inline", "发送成功后，右侧 transcript 会立即刷新成真实对话结果。");

      form.append(makeField("目标 Agent", agentInput, "如果你继续当前会话，这里会自动跟随所选 session 的 Agent。"));
      form.append(continueCurrent.wrap);
      form.append(makeField("Thinking", thinkingInput, "对复杂判断可切高一点；默认 low 更适合日常对话。"));
      form.append(makeField("消息内容", messageInput, "建议直接写结果导向的问题，不需要解释这套系统怎么工作。"));
      const footer = el("div", "action-footer");
      footer.append(submit);
      footer.append(inline);
      form.append(footer);

      agentInput.addEventListener("change", () => {
        conversationState = {
          ...conversationState,
          preferredAgentId: agentInput.value,
        };
      });

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const message = messageInput.value.trim();
        if (!message) {
          inline.textContent = "请先写一条消息。";
          showToast("请先写一条消息。", "warn");
          return;
        }
        const useCurrentSession = continueCurrent.input.checked && selected && selected.talkable;
        setButtonBusy(submit, true, "发送中...");
        inline.textContent = "正在向 OpenClaw Agent 发起真实对话。";
        try {
          const data = await postActionJson("/api/actions/conversations/send", {
            agentId: useCurrentSession ? selected.agentId : agentInput.value,
            sessionId: useCurrentSession ? selected.sessionId : "",
            message,
            thinking: thinkingInput.value,
          });
          if (data.conversation) {
            conversationState = {
              key: data.session?.key || conversationState.key,
              agentId: data.conversation.agentId || (data.session || {}).agentId || agentInput.value,
              sessionId: data.conversation.sessionId || (data.session || {}).sessionId || "",
              preferredAgentId: data.conversation.agentId || (data.session || {}).agentId || agentInput.value,
              mode: "session",
              transcript: data.conversation,
              loading: false,
              error: "",
            };
          }
          inline.textContent = data.message || "消息已发送。";
          messageInput.value = "";
          showToast(data.message || "消息已发送。", "success");
        } catch (error) {
          inline.textContent = error.message;
          showToast(error.message, "error");
        } finally {
          setButtonBusy(submit, false);
          renderAll();
        }
      });

      composeCard.append(form);
      refs.conversationStudio.append(composeCard);
    }

    function renderConversationsView() {
      ensureConversationSelection();
      renderConversationSummary();
      renderConversationList();
      renderConversationStudio();
      renderConversationTranscript();
      renderCommandCards(refs.conversationCommandList, (state.conversations || {}).commands || [], "当前没有可用的对话命令。");
    }

    function renderActivityView() {
      renderRelaysInto(refs.activityRelayGrid, state.relays || [], "最近 24 小时还没有形成 handoff 网络。");
      renderEventsInto(refs.activityEventFeed, filteredEvents(), "当前没有匹配的活动事件。");
    }

    function renderThemesView() {
      renderThemes();
      renderCommandCards(refs.themeCommandList, state.commands || [], "当前没有主题相关命令。");
    }

    function renderSkillsView() {
      const skills = state.skills || {};
      clearNode(refs.skillsSummaryList);
      clearNode(refs.skillsGuidanceList);
      clearNode(refs.skillsCatalogList);
      clearNode(refs.skillsStudio);
      clearNode(refs.skillsCommandList);

      if (!skills.supported) {
        const message = skills.error || "当前环境还没有关联到可用的 skill 工具。";
        refs.skillsSummaryList.append(el("div", "empty", message));
        refs.skillsCatalogList.append(el("div", "empty", "Skills Center 已启用，但当前安装还不能扫描本地 skill 目录。"));
        refs.skillsStudio.append(el("div", "empty", "等安装关联到仓库目录后，这里就可以直接创建和打包技能。"));
        renderCommandCards(refs.skillsCommandList, [], "当前没有可用的技能命令。");
        return;
      }

      const summary = skills.summary || {};
      const roots = skills.roots || [];
      [
        {
          title: "技能目录",
          body: `当前共发现 ${summary.total || 0} 个本地技能。`,
          meta: `Ready ${summary.ready || 0} · Warning ${summary.warning || 0} · Error ${summary.error || 0}`,
        },
        {
          title: "分发准备度",
          body: `已打包 ${(summary.packaged || 0)} 个 zip，可直接进入上传或分享流程。`,
          meta: "支持按 Anthropic Skills 指南做 zip 分发。",
        },
        {
          title: "OpenClaw 发布态",
          body: `已有 ${(summary.publishedToOpenClaw || 0)} 个本地 skill 发布进当前 OpenClaw managed skills 目录。`,
          meta: "发布后可被 `openclaw skills list` 和原生运行时直接识别。",
        },
        {
          title: "扫描范围",
          body: roots.map((item) => item.path).join(" · ") || "当前没有扫描根目录。",
          meta: "项目 skills/ 目录会作为默认技能源。",
        },
      ].forEach((item) => {
        const card = el("div", "deliverable-card");
        card.append(el("div", "deliverable-title", item.title));
        card.append(el("div", "command-desc", item.body));
        card.append(el("div", "path-line", item.meta));
        refs.skillsSummaryList.append(card);
      });

      (skills.guidance || []).forEach((item) => {
        const card = el("div", "deliverable-card");
        card.append(el("div", "deliverable-title", item.title));
        card.append(el("div", "command-desc", item.summary));
        refs.skillsGuidanceList.append(card);
      });
      if (!(skills.guidance || []).length) {
        refs.skillsGuidanceList.append(el("div", "empty", "当前还没有技能指南映射。"));
      }

      const visibleSkills = filteredSkills();
      if (!(skills.skills || []).length) {
        refs.skillsCatalogList.append(el("div", "empty", "当前还没有本地技能。你可以直接在右侧工作台里新建一个。"));
      } else if (!visibleSkills.length) {
        refs.skillsCatalogList.append(el("div", "empty", "当前没有匹配搜索条件的技能。"));
      } else {
        visibleSkills.forEach((skill) => {
          const card = el("div", "deliverable-card");
          const head = el("div", "deliverable-head");
          const left = el("div");
          left.append(el("div", "deliverable-title", skill.displayName || skill.name));
          left.append(el("div", "list-meta", `${skill.slug} · ${skill.categoryLabel} · ${skill.rootKind || "project"}`));
          head.append(left);
          head.append(el("div", "theme-badge", skill.status || "ready"));
          card.append(head);
          card.append(el("div", "command-desc", skill.description || "当前还没有技能描述。"));
          card.append(el("div", "path-line", skill.relativePath || skill.path || "未知路径"));

          const chips = el("div", "drawer-chip-row");
          [
            `质量分 ${skill.qualityScore || 0}`,
            `字数 ${skill.wordCount || 0}`,
            skill.hasScripts ? "带 scripts/" : "无 scripts/",
            skill.hasReferences ? "带 references/" : "无 references/",
            skill.package && skill.package.exists ? "已打包" : "未打包",
            skill.publishedToOpenClaw ? "已发布到 OpenClaw" : "未发布到 OpenClaw",
          ].forEach((label) => chips.append(el("span", "drawer-chip", label)));
          card.append(chips);

          if ((skill.notes || []).length) {
            card.append(el("div", "path-line", (skill.notes || []).join(" · ")));
          }
          if ((skill.issues || []).length) {
            (skill.issues || []).slice(0, 3).forEach((issue) => {
              card.append(el("div", "event-detail", `${issue.kind === "error" ? "错误" : "提醒"}：${issue.message}`));
            });
          }

          const actions = el("div", "panel-actions");
          if (skill.package && skill.package.exists) {
            actions.append(makeCopyButton(skill.package.path, "复制 zip 路径"));
          }
          if (hasPermission("adminWrite")) {
            const publishButton = el("button", "button secondary", skill.publishedToOpenClaw ? "重新发布" : "发布到 OpenClaw");
            publishButton.type = "button";
            publishButton.addEventListener("click", async () => {
              setButtonBusy(publishButton, true, "发布中...");
              try {
                const data = await postActionJson("/api/actions/skills/publish", { slug: skill.slug });
                showToast(data.message || `技能 ${skill.slug} 已发布到 OpenClaw。`, "success");
              } catch (error) {
                showToast(error.message, "error");
              } finally {
                setButtonBusy(publishButton, false);
              }
            });
            actions.append(publishButton);

            const packButton = el("button", "button secondary", skill.package && skill.package.exists ? "重新打包" : "打包技能");
            packButton.type = "button";
            packButton.addEventListener("click", async () => {
              setButtonBusy(packButton, true, "打包中...");
              try {
                const data = await postActionJson("/api/actions/skills/package", { slug: skill.slug });
                showToast(data.message || `技能 ${skill.slug} 已打包。`, "success");
              } catch (error) {
                showToast(error.message, "error");
              } finally {
                setButtonBusy(packButton, false);
              }
            });
            actions.append(packButton);
          }
          card.append(actions);
          refs.skillsCatalogList.append(card);
        });
      }

      if (!hasPermission("adminWrite")) {
        refs.skillsStudio.append(el("div", "empty", "只有 Owner 可以在产品里新建和打包技能。"));
      } else {
        const scaffoldCard = el("section", "studio-card");
        scaffoldCard.append(el("div", "studio-eyebrow", "Skill Scaffold"));
        scaffoldCard.append(el("div", "deliverable-title", "创建一个新 skill"));
        scaffoldCard.append(el("div", "studio-copy", "直接生成 Anthropic 风格的 skill 目录、frontmatter 和说明骨架，方便后续继续打磨。"));

        const scaffoldForm = el("form", "studio-form");
        const slugInput = makeInput("例如：linear-sprint-review", "", "text");
        const titleInput = makeInput("例如：Linear Sprint Review", "", "text");
        const descriptionInput = makeTextarea("写清这个 skill 做什么，再让它在 frontmatter 里补上触发句。", "", 4);
        const triggerInput = makeInput("例如：review the sprint, summarize sprint health", "", "text");
        const categoryInput = makeSelect([
          { value: "document-asset-creation", label: "Document & Asset Creation" },
          { value: "workflow-automation", label: "Workflow Automation" },
          { value: "mcp-enhancement", label: "MCP Enhancement" },
        ], "workflow-automation");
        const mcpServerInput = makeInput("可选：Linear / Notion / custom-mcp", "", "text");
        const includeScripts = makeCheckbox("生成 scripts/ 占位目录", true);
        const includeReferences = makeCheckbox("生成 references/ 占位目录", true);
        const includeAssets = makeCheckbox("生成 assets/ 占位目录", false);
        const scaffoldSubmit = el("button", "button", "创建 skill");
        scaffoldSubmit.type = "submit";
        const scaffoldStatus = el("div", "status-inline", "生成后会立即重新扫描技能目录，并显示校验结果。");

        scaffoldForm.append(makeField("skill slug", slugInput, "必须是 kebab-case，例如 `my-skill-name`。"));
        scaffoldForm.append(makeField("显示标题", titleInput, "用于 SKILL.md 的主标题。"));
        scaffoldForm.append(makeField("能力描述", descriptionInput, "写 what，触发句会和下方 trigger phrase 一起组成 frontmatter description。"));
        scaffoldForm.append(makeField("触发短语", triggerInput, "尽量写成用户真的会说的话。"));
        scaffoldForm.append(makeField("类别", categoryInput, "按 Anthropic Guide 的三大类来归档。"));
        scaffoldForm.append(makeField("MCP Server", mcpServerInput, "可选。适合 MCP Enhancement 场景。"));
        scaffoldForm.append(includeScripts.wrap);
        scaffoldForm.append(includeReferences.wrap);
        scaffoldForm.append(includeAssets.wrap);
        const scaffoldFooter = el("div", "action-footer");
        scaffoldFooter.append(scaffoldSubmit);
        scaffoldFooter.append(scaffoldStatus);
        scaffoldForm.append(scaffoldFooter);

        scaffoldForm.addEventListener("submit", async (event) => {
          event.preventDefault();
          const payload = {
            slug: slugInput.value.trim(),
            title: titleInput.value.trim(),
            description: descriptionInput.value.trim(),
            triggerPhrase: triggerInput.value.trim(),
            category: categoryInput.value,
            includeScripts: includeScripts.input.checked,
            includeReferences: includeReferences.input.checked,
            includeAssets: includeAssets.input.checked,
            mcpServer: mcpServerInput.value.trim(),
          };
          if (!payload.slug || !payload.title || !payload.description) {
            scaffoldStatus.textContent = "slug、标题和描述不能为空。";
            showToast("slug、标题和描述不能为空。", "warn");
            return;
          }
          setButtonBusy(scaffoldSubmit, true, "创建中...");
          scaffoldStatus.textContent = "正在生成新的 skill。";
          try {
            const data = await postActionJson("/api/actions/skills/scaffold", payload);
            scaffoldStatus.textContent = data.message || "skill 已创建。";
            showToast(data.message || "skill 已创建。", "success");
            slugInput.value = "";
            titleInput.value = "";
            descriptionInput.value = "";
            triggerInput.value = "";
            mcpServerInput.value = "";
            includeScripts.input.checked = true;
            includeReferences.input.checked = true;
            includeAssets.input.checked = false;
          } catch (error) {
            scaffoldStatus.textContent = error.message;
            showToast(error.message, "error");
          } finally {
            setButtonBusy(scaffoldSubmit, false);
          }
        });

        scaffoldCard.append(scaffoldForm);
        refs.skillsStudio.append(scaffoldCard);

        const packageCard = el("section", "studio-card");
        packageCard.append(el("div", "studio-eyebrow", "Distribution"));
        packageCard.append(el("div", "deliverable-title", "打包 skill zip"));
        packageCard.append(el("div", "studio-copy", "把 skill 打成 zip，方便上传到 Claude.ai 或进入你自己的分发流程。"));
        if (!(skills.skills || []).length) {
          packageCard.append(el("div", "empty", "先创建至少一个 skill，才能继续打包。"));
        } else {
          const packageForm = el("form", "studio-form");
          const skillSelect = makeSelect(
            (skills.skills || []).map((skill) => ({ value: skill.slug, label: `${skill.displayName} · ${skill.slug}` })),
            (skills.skills || [])[0].slug,
          );
          const packageSubmit = el("button", "button", "打包 zip");
          packageSubmit.type = "submit";
          const packageStatus = el("div", "status-inline", "zip 会输出到 `dist/skills/`，便于分享和上传。");
          packageForm.append(makeField("选择 skill", skillSelect, "打包时会保留顶层 skill 文件夹。"));
          const packageFooter = el("div", "action-footer");
          packageFooter.append(packageSubmit);
          packageFooter.append(packageStatus);
          packageForm.append(packageFooter);
          packageForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            setButtonBusy(packageSubmit, true, "打包中...");
            packageStatus.textContent = "正在打包 skill zip。";
            try {
              const data = await postActionJson("/api/actions/skills/package", { slug: skillSelect.value });
              packageStatus.textContent = data.message || "skill 已打包。";
              showToast(data.message || "skill 已打包。", "success");
            } catch (error) {
              packageStatus.textContent = error.message;
              showToast(error.message, "error");
            } finally {
              setButtonBusy(packageSubmit, false);
            }
          });
          packageCard.append(packageForm);
        }
        refs.skillsStudio.append(packageCard);
      }

      renderCommandCards(refs.skillsCommandList, skills.commands || [], "当前没有可用的技能命令。");
    }

    function renderOpenClawView() {
      const data = state.openclaw || {};
      clearNode(refs.openclawSummaryList);
      clearNode(refs.openclawCompatList);
      clearNode(refs.openclawChannelsList);
      clearNode(refs.openclawNativeSkillsList);
      clearNode(refs.openclawCommandList);

      if (!data.supported) {
        const message = data.error || "当前环境无法读取 OpenClaw 运行态。";
        refs.openclawSummaryList.append(el("div", "empty", message));
        refs.openclawCompatList.append(el("div", "empty", "OpenClaw 控制面暂时不可用。"));
        refs.openclawChannelsList.append(el("div", "empty", "没有可展示的 channel / gateway 数据。"));
        refs.openclawNativeSkillsList.append(el("div", "empty", "没有可展示的原生 skill 数据。"));
        renderCommandCards(refs.openclawCommandList, data.commands || [], "当前没有可用的 OpenClaw 命令。");
        return;
      }

      [
        {
          title: "OpenClaw 版本",
          body: (data.version || {}).raw || "unknown",
          meta: `release ${(data.version || {}).release || "unknown"} · build ${(data.version || {}).build || "unknown"}`,
        },
        {
          title: "配置校验",
          body: (data.config || {}).valid ? "当前配置已通过 schema 校验。" : "当前配置没有通过 schema 校验。",
          meta: (data.config || {}).path || "未知配置路径",
        },
        {
          title: "Gateway 健康",
          body: (data.gateway || {}).ok ? "Gateway 正常返回 health JSON。" : "Gateway 当前没有返回健康状态。",
          meta: `agent ${(data.gateway || {}).agentCount || 0} · default ${(data.gateway || {}).defaultAgentId || "unknown"} · ${((data.gateway || {}).durationMs || 0)}ms`,
        },
        {
          title: "原生 Skills",
          body: `OpenClaw 当前识别 ${(data.nativeSkills || {}).total || 0} 个原生 skills，其中 ${(data.nativeSkills || {}).eligible || 0} 个可直接使用。`,
          meta: `bundled ${(data.nativeSkills || {}).bundled || 0} · external ${(data.nativeSkills || {}).external || 0} · repo published ${((state.skills || {}).summary || {}).publishedToOpenClaw || 0}`,
        },
      ].forEach((item) => {
        const card = el("div", "deliverable-card");
        card.append(el("div", "deliverable-title", item.title));
        card.append(el("div", "command-desc", item.body));
        card.append(el("div", "path-line", item.meta));
        refs.openclawSummaryList.append(card);
      });

      (data.compatibility || []).forEach((item) => {
        const card = el("div", "deliverable-card");
        const head = el("div", "deliverable-head");
        const left = el("div");
        left.append(el("div", "deliverable-title", item.title));
        left.append(el("div", "command-desc", item.body));
        head.append(left);
        head.append(el("div", "theme-badge", item.status || "ready"));
        card.append(head);
        if (item.meta) {
          card.append(el("div", "path-line", item.meta));
        }
        refs.openclawCompatList.append(card);
      });
      if (!(data.compatibility || []).length) {
        refs.openclawCompatList.append(el("div", "empty", "当前还没有 OpenClaw 兼容性判断结果。"));
      }

      if (!((data.gateway || {}).channels || []).length) {
        refs.openclawChannelsList.append(el("div", "empty", "当前还没有 channel 健康数据。"));
      } else {
        ((data.gateway || {}).channels || []).forEach((channel) => {
          const card = el("div", "deliverable-card");
          const head = el("div", "deliverable-head");
          const left = el("div");
          left.append(el("div", "deliverable-title", channel.title));
          left.append(el("div", "list-meta", channel.meta || "unknown"));
          head.append(left);
          head.append(el("div", "theme-badge", channel.healthy ? "healthy" : "warning"));
          card.append(head);
          card.append(el("div", "command-desc", channel.detail || "无额外信息"));
          card.append(el("div", "path-line", channel.running ? "运行中" : "未运行"));
          refs.openclawChannelsList.append(card);
        });
      }

      const nativeSkills = data.nativeSkills || {};
      const skillSummaryCard = el("div", "deliverable-card");
      skillSummaryCard.append(el("div", "deliverable-title", "原生 Skills 摘要"));
      skillSummaryCard.append(el("div", "command-desc", `Eligible ${nativeSkills.eligible || 0} · Disabled ${nativeSkills.disabled || 0} · Blocked ${nativeSkills.blocked || 0}`));
      skillSummaryCard.append(el("div", "path-line", nativeSkills.managedSkillsDir || "当前没有返回 managed skills 目录。"));
      skillSummaryCard.append(el("div", "path-line", `Top missing bins: ${(nativeSkills.missingBins || []).map((item) => `${item.name}(${item.count})`).join(" · ") || "none"}`));
      refs.openclawNativeSkillsList.append(skillSummaryCard);

      (nativeSkills.sampleEligible || []).slice(0, 4).forEach((item) => {
        const card = el("div", "deliverable-card");
        card.append(el("div", "deliverable-title", `可用 · ${item.title}`));
        card.append(el("div", "list-meta", item.meta || ""));
        card.append(el("div", "command-desc", item.detail || ""));
        refs.openclawNativeSkillsList.append(card);
      });
      (nativeSkills.sampleMissing || []).slice(0, 4).forEach((item) => {
        const card = el("div", "deliverable-card");
        card.append(el("div", "deliverable-title", `待补齐 · ${item.title}`));
        card.append(el("div", "list-meta", item.meta || ""));
        card.append(el("div", "command-desc", item.detail || ""));
        refs.openclawNativeSkillsList.append(card);
      });
      (nativeSkills.warnings || []).slice(0, 3).forEach((warning) => {
        const card = el("div", "deliverable-card");
        card.append(el("div", "deliverable-title", "运行时提醒"));
        card.append(el("div", "command-desc", warning));
        refs.openclawNativeSkillsList.append(card);
      });

      renderCommandCards(refs.openclawCommandList, data.commands || [], "当前没有可用的 OpenClaw 命令。");
    }

    function renderAdminSurface() {
      renderAdminView();
    }

    function renderSkillsSurface() {
      renderSkillsView();
    }

    function renderOpenClawSurface() {
      renderOpenClawView();
    }

    function renderAll() {
      renderMeta();
      applyViewState();
      renderOverview();
      renderAgentsView();
      renderTasksView();
      renderConversationsView();
      renderActivityView();
      renderThemesView();
      renderSkillsSurface();
      renderOpenClawSurface();
      renderAdminSurface();
      syncDrawer();
    }

    async function fetchLatestDashboard(reason = "manual") {
      if (!supportsHttp || paused || fetchInFlight) return;
      fetchInFlight = true;
      try {
        const response = await fetch(`${dashboardApiHref()}?_=${Date.now()}`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        state = await response.json();
        lastSyncAt = Date.now();
        renderAll();
        connectionMode = reason === "stream" ? "live" : connectionMode;
      } catch (_error) {
        connectionMode = "degraded";
      } finally {
        fetchInFlight = false;
      }
    }

    function disconnectLive() {
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    }

    function connectLive() {
      if (!supportsHttp || paused) return;
      if (!window.EventSource) {
        connectionMode = "snapshot";
        return;
      }
      disconnectLive();
      connectionMode = "connecting";
      setLiveStatus("正在建立实时连接...", "warn");
      eventSource = new EventSource(dashboardEventsHref());
      eventSource.addEventListener("dashboard", async () => {
        await fetchLatestDashboard("stream");
      });
      eventSource.onopen = () => {
        connectionMode = "live";
        lastSyncAt = Date.now();
      };
      eventSource.onerror = () => {
        if (paused) return;
        connectionMode = "degraded";
        disconnectLive();
        reconnectTimer = setTimeout(() => connectLive(), 4000);
      };
    }

    refs.navLinks.forEach((link) => {
      link.addEventListener("click", () => navigate(link.dataset.view));
    });
    refs.layoutButtons.forEach((button) => {
      button.addEventListener("click", () => setLayoutMode(button.dataset.layout));
    });
    refs.toggleRail.addEventListener("click", toggleRail);
    refs.globalSearch.addEventListener("input", (event) => {
      searchQuery = event.target.value.trim();
      renderAll();
    });
    refs.refreshNow.addEventListener("click", async () => {
      if (supportsHttp) {
        await fetchLatestDashboard("manual");
      } else {
        location.reload();
      }
    });
    refs.toggleRefresh.addEventListener("click", async () => {
      paused = !paused;
      refs.toggleRefresh.textContent = paused ? "恢复实时刷新" : "暂停实时刷新";
      if (paused) {
        disconnectLive();
        setLiveStatus("实时刷新已暂停", "paused");
      } else {
        await fetchLatestDashboard("manual");
        connectLive();
      }
    });
    refs.scrim.addEventListener("click", closeDrawer);
    refs.drawerClose.addEventListener("click", closeDrawer);

    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeDrawer();
      }
    });
    window.addEventListener("click", (event) => {
      if (refs.drawer.dataset.open !== "true") return;
      if (refs.drawer.contains(event.target)) return;
      if (event.target.closest(".click-card")) return;
      if (event.target.closest(".drawer-link")) return;
      closeDrawer();
    });
    window.addEventListener("popstate", () => {
      currentView = getViewFromLocation();
      renderAll();
    });
    window.addEventListener("hashchange", () => {
      if (!supportsHttp) {
        currentView = getViewFromLocation();
        renderAll();
      }
    });

    setInterval(() => {
      if (paused) return;
      if (!supportsHttp) {
        setLiveStatus("当前是本地快照模式", "idle");
        return;
      }
      const ageSeconds = Math.max(0, Math.floor((Date.now() - lastSyncAt) / 1000));
      if (connectionMode === "live") {
        setLiveStatus(`实时连接中 · 最近同步 ${ageSeconds} 秒前`, "live");
      } else if (connectionMode === "connecting") {
        setLiveStatus("正在建立实时连接...", "warn");
      } else if (connectionMode === "degraded") {
        setLiveStatus(`连接中断，正在重连 · 最近同步 ${ageSeconds} 秒前`, "warn");
      } else {
        setLiveStatus(`快照模式 · 最近同步 ${ageSeconds} 秒前`, "idle");
      }
    }, 1000);

    applyLayoutPrefs();
    renderAll();
    if (supportsHttp) {
      connectLive();
      fetchLatestDashboard("manual");
    } else {
      setLiveStatus("当前是本地快照模式", "idle");
    }
  </script>
</body>
</html>
"""


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


def now_iso():
    return now_utc().isoformat().replace("+00:00", "Z")


def epoch_ms_to_iso(value):
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return ""


PAYLOAD_CACHE = {}


def cached_payload(cache_key, ttl_seconds, builder):
    now = time.time()
    cached = PAYLOAD_CACHE.get(cache_key)
    if cached and now - cached["ts"] < ttl_seconds:
        return deepcopy(cached["value"])
    value = builder()
    PAYLOAD_CACHE[cache_key] = {"ts": now, "value": deepcopy(value)}
    return value


def clear_cached_payloads():
    PAYLOAD_CACHE.clear()


def parse_openclaw_release(value):
    if not value:
        return None
    parts = []
    for item in str(value).split("."):
        if not item.isdigit():
            return None
        parts.append(int(item))
    return tuple(parts)


def is_supported_openclaw_release(value):
    parsed = parse_openclaw_release(value)
    baseline = parse_openclaw_release(OPENCLAW_BASELINE_RELEASE)
    if not parsed or not baseline:
        return False
    return parsed >= baseline


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


def parse_json_payload(*candidates, default=None):
    decoder = json.JSONDecoder()
    for candidate in candidates:
        if not candidate:
            continue
        text = str(candidate).strip()
        if not text:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        for index, char in enumerate(text):
            if char not in "[{":
                continue
            try:
                payload, _end = decoder.raw_decode(text[index:])
                return payload
            except json.JSONDecodeError:
                continue
    return deepcopy(default)


def load_config(openclaw_dir):
    return load_json(Path(openclaw_dir) / "openclaw.json", {})


def legacy_project_metadata(config):
    metadata = config.get("sanshengLiubu", {}) if isinstance(config, dict) else {}
    return deepcopy(metadata) if isinstance(metadata, dict) else {}


def project_metadata_path(openclaw_dir):
    return Path(openclaw_dir) / "sansheng-liubu.json"


def infer_theme_name_from_agents(config):
    agent_ids = {agent.get("id") for agent in load_agents(config) if isinstance(agent, dict)}
    if "assistant" in agent_ids:
        return "corporate"
    if "secretary" in agent_ids:
        return "startup"
    if "taizi" in agent_ids:
        return "imperial"
    return "imperial"


def load_project_metadata(openclaw_dir, config=None):
    path = project_metadata_path(openclaw_dir)
    data = load_json(path, {})
    config = config or load_config(openclaw_dir)
    legacy = legacy_project_metadata(config)
    if isinstance(data, dict) and data:
        return {**legacy, **data}
    if legacy:
        return legacy
    inferred_theme = infer_theme_name_from_agents(config)
    return {
        "theme": inferred_theme,
        "displayName": THEME_CATALOG.get(inferred_theme, {}).get("displayName", inferred_theme),
        "projectDir": "",
        "taskPrefix": "",
    }


def load_agents(config):
    return config.get("agents", {}).get("list", [])


def get_router_agent_id(config):
    for agent in load_agents(config):
        if agent.get("default"):
            return agent["id"]
    agents = load_agents(config)
    return agents[0]["id"] if agents else "taizi"


CONVERSATION_SOURCE_LABELS = {
    "main": "主会话",
    "telegram": "Telegram",
    "qqbot": "QQ Bot",
    "feishu": "飞书",
    "whatsapp": "WhatsApp",
    "discord": "Discord",
    "slack": "Slack",
    "cron": "定时任务",
    "subagent": "子代理",
}
READ_ONLY_CONVERSATION_SOURCES = {"cron", "subagent"}


def conversation_source_from_key(session_key):
    parts = str(session_key or "").split(":")
    return parts[2] if len(parts) > 2 else "main"


def conversation_label(session):
    session_key = str(session.get("key", "") or "")
    parts = session_key.split(":")
    source = conversation_source_from_key(session_key)
    agent_id = session.get("agentId", "")
    if source == "main":
        return f"{agent_id} · 主会话"
    if source in {"telegram", "qqbot", "feishu", "whatsapp", "discord", "slack"}:
        target = parts[-1] if len(parts) >= 5 else ""
        target_label = target[:18] + "..." if len(target) > 18 else target
        kind_label = "群组" if "group" in parts else "私聊"
        return f"{CONVERSATION_SOURCE_LABELS.get(source, source)} · {kind_label} {target_label}".strip()
    if source == "cron":
        return f"{agent_id} · 定时任务"
    if source == "subagent":
        return f"{agent_id} · 子代理会话"
    return session_key or agent_id or "未命名会话"


def session_transcript_path(openclaw_dir, agent_id, session_id):
    if not agent_id or not session_id:
        return None
    path = Path(openclaw_dir) / "agents" / agent_id / "sessions" / f"{session_id}.jsonl"
    return path if path.exists() else None


def extract_text_from_content(content):
    texts = []
    for item in content or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and item.get("text"):
            texts.append(str(item.get("text")))
    return "\n\n".join(part.strip() for part in texts if part and str(part).strip()).strip()


def summarize_json(value, max_chars=180):
    try:
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        rendered = str(value)
    rendered = rendered.strip()
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 1].rstrip() + "…"


def parse_transcript_items(transcript_path, limit=120):
    if not transcript_path or not Path(transcript_path).exists():
        return {
            "items": [],
            "preview": "",
            "meta": {"model": "", "provider": "", "thinkingLevel": ""},
            "stats": {"turns": 0, "userMessages": 0, "assistantMessages": 0, "toolMessages": 0},
        }

    items = []
    preview = ""
    meta = {"model": "", "provider": "", "thinkingLevel": ""}
    user_messages = 0
    assistant_messages = 0
    tool_messages = 0
    lines = Path(transcript_path).read_text(encoding="utf-8", errors="replace").splitlines()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry_type = entry.get("type")
        if entry_type == "model_change":
            meta["model"] = entry.get("modelId", "") or meta["model"]
            meta["provider"] = entry.get("provider", "") or meta["provider"]
            continue
        if entry_type == "thinking_level_change":
            meta["thinkingLevel"] = entry.get("thinkingLevel", "") or meta["thinkingLevel"]
            continue
        if entry_type != "message":
            continue

        payload = entry.get("message", {}) if isinstance(entry.get("message"), dict) else {}
        role = payload.get("role", "")
        timestamp = entry.get("timestamp") or payload.get("timestamp") or ""
        content = payload.get("content", []) if isinstance(payload.get("content"), list) else []

        if role in {"user", "assistant"}:
            text = extract_text_from_content(content)
            if text:
                items.append(
                    {
                        "id": entry.get("id", ""),
                        "kind": role,
                        "title": "用户" if role == "user" else "Agent",
                        "text": text,
                        "at": timestamp,
                    }
                )
                preview = text
                if role == "user":
                    user_messages += 1
                else:
                    assistant_messages += 1
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "toolCall":
                    continue
                tool_messages += 1
                items.append(
                    {
                        "id": part.get("id", entry.get("id", "")),
                        "kind": "tool_call",
                        "title": f"调用工具 · {part.get('name', 'unknown')}",
                        "text": summarize_json(part.get("arguments", {})),
                        "at": timestamp,
                    }
                )
            continue

        if role == "toolResult":
            tool_messages += 1
            text = extract_text_from_content(content) or summarize_json(payload.get("details", {}))
            items.append(
                {
                    "id": entry.get("id", ""),
                    "kind": "tool_result",
                    "title": f"工具结果 · {payload.get('toolName', 'unknown')}",
                    "text": text or "工具没有返回可展示文本。",
                    "at": timestamp,
                    "error": bool(payload.get("isError")),
                }
            )
            if text:
                preview = text

    if limit and len(items) > limit:
        items = items[-limit:]
    return {
        "items": items,
        "preview": preview,
        "meta": meta,
        "stats": {
            "turns": user_messages + assistant_messages,
            "userMessages": user_messages,
            "assistantMessages": assistant_messages,
            "toolMessages": tool_messages,
        },
    }


def load_conversation_catalog(openclaw_dir, config, agent_labels, limit=36):
    openclaw_dir = Path(openclaw_dir).expanduser().resolve()

    def build():
        env = openclaw_command_env(openclaw_dir)
        result = run_command(["openclaw", "sessions", "--all-agents", "--json"], env=env)
        payload = parse_json_payload(result.stdout, result.stderr, default=None)
        if payload is None:
            return {
                "supported": False,
                "error": (result.stderr or result.stdout or "读取会话目录失败。").strip(),
                "summary": {"total": 0, "talkable": 0, "active24h": 0},
                "sessions": [],
                "commands": [],
            }

        now = now_utc()
        items = []
        for session in payload.get("sessions", []) or []:
            updated_at = epoch_ms_to_iso(session.get("updatedAt"))
            updated_dt = parse_iso(updated_at)
            source = conversation_source_from_key(session.get("key"))
            transcript_path = session_transcript_path(openclaw_dir, session.get("agentId", ""), session.get("sessionId", ""))
            transcript_preview = parse_transcript_items(transcript_path, limit=18)
            items.append(
                {
                    "key": session.get("key", ""),
                    "agentId": session.get("agentId", ""),
                    "agentLabel": agent_labels.get(session.get("agentId", ""), session.get("agentId", "")),
                    "sessionId": session.get("sessionId", ""),
                    "kind": session.get("kind", "direct"),
                    "source": source,
                    "sourceLabel": CONVERSATION_SOURCE_LABELS.get(source, source),
                    "talkable": source not in READ_ONLY_CONVERSATION_SOURCES,
                    "label": conversation_label(session),
                    "updatedAt": updated_at,
                    "updatedAgo": format_age(updated_dt, now),
                    "model": session.get("model", ""),
                    "provider": session.get("modelProvider") or session.get("providerOverride") or "",
                    "contextTokens": session.get("contextTokens"),
                    "totalTokens": session.get("totalTokens"),
                    "abortedLastRun": bool(session.get("abortedLastRun")),
                    "preview": transcript_preview.get("preview", "") or "暂时还没有可展示的文本消息。",
                    "transcriptPath": str(transcript_path) if transcript_path else "",
                }
            )

        items.sort(
            key=lambda item: parse_iso(item.get("updatedAt")) or datetime.fromtimestamp(0, tz=timezone.utc),
            reverse=True,
        )
        active24h = sum(
            1
            for item in items
            if (parse_iso(item.get("updatedAt")) or datetime.fromtimestamp(0, tz=timezone.utc)) >= now - timedelta(hours=24)
        )
        talkable = sum(1 for item in items if item.get("talkable"))
        return {
            "supported": True,
            "error": "",
            "summary": {
                "total": len(items),
                "talkable": talkable,
                "active24h": active24h,
            },
            "sessions": items[:limit],
            "commands": [
                {
                    "label": "列出全部会话",
                    "command": f'OPENCLAW_STATE_DIR="{openclaw_dir}" OPENCLAW_CONFIG_PATH="{openclaw_dir / "openclaw.json"}" openclaw sessions --all-agents --json',
                    "description": "查看当前安装目录里的真实 OpenClaw 会话索引。",
                },
                {
                    "label": "与路由 Agent 对话",
                    "command": f'OPENCLAW_STATE_DIR="{openclaw_dir}" OPENCLAW_CONFIG_PATH="{openclaw_dir / "openclaw.json"}" openclaw agent --agent {get_router_agent_id(config)} --message "你好" --json',
                    "description": "从终端直接向当前路由 Agent 发起一轮真实对话。",
                },
            ],
        }

    return cached_payload(("conversation-catalog", str(openclaw_dir)), 10, build)


def load_conversation_transcript(openclaw_dir, agent_id, session_id):
    path = session_transcript_path(openclaw_dir, agent_id, session_id)
    transcript = parse_transcript_items(path, limit=140)
    return {
        "agentId": agent_id,
        "sessionId": session_id,
        "path": str(path) if path else "",
        "items": transcript.get("items", []),
        "stats": transcript.get("stats", {}),
        "meta": transcript.get("meta", {}),
    }


def find_conversation_session(conversations, agent_id, session_id):
    for session in conversations.get("sessions", []) or []:
        if session.get("agentId") == agent_id and session.get("sessionId") == session_id:
            return session
    return None


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
    data = load_json(Path(workspace) / "data" / "tasks_source.json", [])
    return data if isinstance(data, list) else data.get("tasks", [])


def merge_tasks(openclaw_dir, config):
    merged = {}
    for agent in load_agents(config):
        workspace = Path(agent.get("workspace", "")) if agent.get("workspace") else Path(openclaw_dir) / f"workspace-{agent['id']}"
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
    workspace = Path(workspace)
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
    return deduped[-8:]


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


def build_label_maps(agents, kanban_cfg, router_agent_id):
    agent_labels = dict(kanban_cfg.get("agent_labels", {}))
    reverse = defaultdict(set)

    for agent in agents:
        agent_id = agent["id"]
        title_label = agent_labels.get(agent_id) or agent.get("identity", {}).get("name") or agent_id
        agent_labels.setdefault(agent_id, title_label)
        reverse[title_label].add(agent_id)
        reverse[agent_id].add(agent_id)

        identity_name = agent.get("identity", {}).get("name")
        if identity_name:
            reverse[identity_name].add(agent_id)

    if router_agent_id not in agent_labels:
        agent_labels[router_agent_id] = next(
            (agent.get("identity", {}).get("name", router_agent_id) for agent in agents if agent["id"] == router_agent_id),
            router_agent_id,
        )
    reverse[agent_labels[router_agent_id]].add(router_agent_id)

    return agent_labels, reverse


def build_task_replay(task, label_to_agent_ids, now):
    replay = []

    for entry in task.get("flow_log", []):
        at = parse_iso(entry.get("at"))
        from_label = entry.get("from") or "?"
        to_label = entry.get("to") or "?"
        replay.append(
            {
                "kind": "handoff",
                "at": entry.get("at", ""),
                "atAgo": format_age(at, now) if at else "未知时间",
                "actorLabel": from_label,
                "actorId": sorted(label_to_agent_ids.get(from_label, []))[0] if label_to_agent_ids.get(from_label) else "",
                "targetLabel": to_label,
                "targetId": sorted(label_to_agent_ids.get(to_label, []))[0] if label_to_agent_ids.get(to_label) else "",
                "headline": f"{from_label} -> {to_label}",
                "detail": entry.get("remark", ""),
            }
        )

    for entry in task.get("progress_log", []):
        at = parse_iso(entry.get("at"))
        actor_label = entry.get("agentLabel") or entry.get("agent") or "Agent"
        replay.append(
            {
                "kind": "progress",
                "at": entry.get("at", ""),
                "atAgo": format_age(at, now) if at else "未知时间",
                "actorLabel": actor_label,
                "actorId": entry.get("agent", ""),
                "targetLabel": "",
                "targetId": "",
                "headline": f"{actor_label} 正在推进",
                "detail": entry.get("text", ""),
            }
        )

    replay.sort(key=lambda item: parse_iso(item.get("at")) or datetime.fromtimestamp(0, tz=timezone.utc))
    return replay


def status_for_agent(active_count, blocked_count, signal_dt, last_seen, now):
    if blocked_count:
        return "blocked"
    if active_count and signal_dt and now - signal_dt <= timedelta(minutes=20):
        return "active"
    if active_count:
        return "waiting"
    if last_seen and now - last_seen <= timedelta(minutes=20):
        return "standby"
    return "idle"


def build_dashboard_data(openclaw_dir):
    openclaw_dir = Path(openclaw_dir)
    config = load_config(openclaw_dir)
    metadata = load_project_metadata(openclaw_dir, config=config)
    agents = load_agents(config)
    router_agent_id = get_router_agent_id(config)
    kanban_cfg = load_kanban_config(openclaw_dir, router_agent_id)
    now = now_utc()
    tasks = merge_tasks(openclaw_dir, config)
    theme_name = metadata.get("theme", "imperial")
    theme_style = THEME_STYLES.get(theme_name, THEME_STYLES["imperial"])

    agent_labels, label_to_agent_ids = build_label_maps(agents, kanban_cfg, router_agent_id)

    task_counts_by_agent = Counter()
    blocked_counts_by_agent = Counter()
    latest_focus_by_agent = {}
    latest_focus_dt_by_agent = {}
    relay_counter = Counter()
    relay_last_at = {}
    handoffs_24h_by_agent = Counter()
    agent_signals = defaultdict(list)
    global_events = []
    task_index = []
    active_tasks = []
    deliverables = []

    recent_threshold = now - timedelta(hours=24)

    for task in tasks:
        replay = build_task_replay(task, label_to_agent_ids, now)
        current_agent = current_agent_for_task(task, kanban_cfg, router_agent_id)
        state = str(task.get("state", task.get("status", ""))).lower()
        todo = todo_summary(task)
        todo_items = [
            {
                "title": item.get("title", ""),
                "status": item.get("status", "not-started"),
            }
            for item in task.get("todos", [])
        ]

        task_record = {
            "id": task.get("id"),
            "title": task.get("title", task.get("id", "Untitled Task")),
            "state": task.get("state", task.get("status", "Unknown")),
            "owner": task.get("official", ""),
            "org": task.get("org", ""),
            "currentAgent": current_agent,
            "currentAgentLabel": agent_labels.get(current_agent, current_agent or task.get("org", "?")),
            "currentUpdate": task.get("now") or task.get("currentUpdate") or "",
            "updatedAt": task.get("updatedAt", ""),
            "updatedAgo": format_age(parse_iso(task.get("updatedAt")), now),
            "output": task.get("output", ""),
            "todo": todo,
            "todoItems": todo_items,
            "route": task_route(task),
            "blocked": state == "blocked",
            "active": state not in TERMINAL_STATES,
            "replay": list(reversed(replay[-24:])),
        }
        task_index.append(task_record)
        if state in TERMINAL_STATES or task.get("output"):
            deliverables.append(
                {
                    "id": task_record["id"],
                    "title": task_record["title"],
                    "state": task_record["state"],
                    "owner": task_record["owner"],
                    "updatedAt": task_record["updatedAt"],
                    "updatedAgo": task_record["updatedAgo"],
                    "summary": task_record["currentUpdate"],
                    "output": task_record["output"],
                }
            )

        if current_agent and task_record["active"]:
            task_counts_by_agent[current_agent] += 1
            if state == "blocked":
                blocked_counts_by_agent[current_agent] += 1
            progress_event = latest_progress_event(task)
            signal_dt = parse_iso((progress_event or {}).get("at")) or parse_iso(task.get("updatedAt"))
            if current_agent not in latest_focus_dt_by_agent or (
                signal_dt and signal_dt >= latest_focus_dt_by_agent[current_agent]
            ):
                latest_focus_dt_by_agent[current_agent] = signal_dt
                latest_focus_by_agent[current_agent] = task_record["currentUpdate"] or task_record["title"]

        for replay_event in replay:
            global_events.append(
                {
                    "type": replay_event["kind"],
                    "at": replay_event.get("at", ""),
                    "title": task_record["title"],
                    "taskId": task_record["id"],
                    "headline": replay_event["headline"],
                    "detail": replay_event.get("detail", ""),
                }
            )

            if replay_event["kind"] == "handoff":
                at = parse_iso(replay_event.get("at"))
                if at and at >= recent_threshold:
                    edge = (replay_event["actorLabel"], replay_event["targetLabel"])
                    relay_counter[edge] += 1
                    relay_last_at[edge] = max(at, relay_last_at.get(edge, at))
                    if replay_event.get("actorId"):
                        handoffs_24h_by_agent[replay_event["actorId"]] += 1
                    if replay_event.get("targetId"):
                        handoffs_24h_by_agent[replay_event["targetId"]] += 1

                if replay_event.get("actorId"):
                    agent_signals[replay_event["actorId"]].append(
                        {
                            "title": task_record["title"],
                            "taskId": task_record["id"],
                            "meta": replay_event["atAgo"],
                            "detail": f"移交给 {replay_event['targetLabel']} · {replay_event.get('detail', '')}".strip(" ·"),
                        }
                    )
                if replay_event.get("targetId"):
                    agent_signals[replay_event["targetId"]].append(
                        {
                            "title": task_record["title"],
                            "taskId": task_record["id"],
                            "meta": replay_event["atAgo"],
                            "detail": f"从 {replay_event['actorLabel']} 接到任务 · {replay_event.get('detail', '')}".strip(" ·"),
                        }
                    )
            elif replay_event.get("actorId"):
                agent_signals[replay_event["actorId"]].append(
                    {
                        "title": task_record["title"],
                        "taskId": task_record["id"],
                        "meta": replay_event["atAgo"],
                        "detail": replay_event.get("detail", ""),
                    }
                )

        if task_record["active"]:
            active_tasks.append(task_record)

    active_tasks.sort(
        key=lambda item: parse_iso(item.get("updatedAt")) or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )
    task_index.sort(
        key=lambda item: parse_iso(item.get("updatedAt")) or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )
    global_events.sort(
        key=lambda item: parse_iso(item.get("at")) or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )
    deliverables.sort(
        key=lambda item: parse_iso(item.get("updatedAt")) or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
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
        active_task_cards = [
            {
                "id": task["id"],
                "title": task["title"],
                "state": task["state"],
                "updatedAgo": task["updatedAgo"],
            }
            for task in active_tasks
            if task.get("currentAgent") == agent_id
        ]
        status = status_for_agent(
            task_counts_by_agent[agent_id],
            blocked_counts_by_agent[agent_id],
            signal_dt,
            last_seen,
            now,
        )
        if status in {"active", "waiting", "blocked"}:
            active_agent_count += 1

        agent_cards.append(
            {
                "id": agent_id,
                "name": agent.get("identity", {}).get("name", agent_id),
                "title": agent_labels.get(agent_id, agent_id),
                "model": agent.get("model", "default"),
                "status": status,
                "activeTasks": task_counts_by_agent[agent_id],
                "blockedTasks": blocked_counts_by_agent[agent_id],
                "focus": latest_focus_by_agent.get(agent_id, ""),
                "lastSeenAgo": format_age(last_seen, now),
                "lastSeenAt": last_seen.isoformat().replace("+00:00", "Z") if last_seen else "",
                "workspaceLastSeenAgo": format_age(workspace_dt, now),
                "sessionLastSeenAgo": format_age(session_dt, now),
                "handoffs24h": handoffs_24h_by_agent[agent_id],
                "activeTaskCards": active_task_cards[:6],
                "recentSignals": agent_signals[agent_id][:8],
            }
        )

    relays = []
    for edge, count in relay_counter.most_common(10):
        relays.append(
            {
                "from": edge[0],
                "to": edge[1],
                "count": count,
                "lastAt": relay_last_at[edge].isoformat().replace("+00:00", "Z"),
                "lastAgo": format_age(relay_last_at[edge], now),
            }
        )

    completed_today = sum(
        1
        for task in task_index
        if str(task.get("state", "")).lower() == "done"
        and (parse_iso(task.get("updatedAt")) or now) >= now - timedelta(days=1)
    )
    blocked_total = sum(1 for task in active_tasks if task.get("blocked"))
    signal_count = sum(
        1
        for event in global_events
        if parse_iso(event.get("at")) and parse_iso(event.get("at")) >= now - timedelta(hours=1)
    )
    theme_catalog = []
    for theme_key, meta in THEME_CATALOG.items():
        theme_catalog.append(
            {
                "name": theme_key,
                "displayName": meta["displayName"],
                "language": meta.get("language", "zh-CN"),
                "tagline": meta["tagline"],
                "bestFor": meta["bestFor"],
                "summary": meta["summary"],
                "current": theme_key == theme_name,
            }
        )
    product_commands = [
        {
            "label": "打开实时面板",
            "command": f"python3 {openclaw_dir}/workspace-{router_agent_id}/scripts/collaboration_dashboard.py --serve --dir {openclaw_dir}",
            "description": "启动完整 Mission Control 本地应用。",
        },
        {
            "label": "查看健康状态",
            "command": f"python3 {openclaw_dir}/workspace-{router_agent_id}/scripts/health_dashboard.py --dir {openclaw_dir}",
            "description": "快速检查各 Agent 工作区和任务状态。",
        },
        {
            "label": "导出当前快照",
            "command": f"python3 {openclaw_dir}/workspace-{router_agent_id}/scripts/collaboration_dashboard.py --dir {openclaw_dir}",
            "description": "生成最新 HTML 和 JSON 快照。",
        },
    ]
    admin_data = build_admin_data(openclaw_dir, config, now, include_sensitive=False)
    conversation_data = load_conversation_catalog(openclaw_dir, config, agent_labels)
    skills_data = load_skills_catalog(openclaw_dir, config=config)
    openclaw_data = load_openclaw_control_data(openclaw_dir)
    context_hub_data = load_context_hub_data(openclaw_dir)
    management_data = build_management_data(openclaw_dir, task_index, conversation_data, deliverables, agent_cards, global_events, relays, now)
    orchestration_data = build_orchestration_data(openclaw_dir, agent_cards, task_index, router_agent_id, now)
    native_skill_names = set(openclaw_data.pop("_nativeSkillNames", []))
    managed_skills_root = str((openclaw_data.get("nativeSkills", {}) or {}).get("managedSkillsDir", "") or "").strip()
    managed_skills_dir = Path(managed_skills_root).expanduser() if managed_skills_root else None
    published_count = 0
    for skill in skills_data.get("skills", []):
        managed_skill_path = managed_skills_dir / skill.get("slug", "") if managed_skills_dir else None
        published = skill.get("slug") in native_skill_names or bool(
            managed_skill_path and (managed_skill_path / "SKILL.md").exists()
        )
        skill["publishedToOpenClaw"] = published
        if published:
            published_count += 1
    if isinstance(skills_data.get("summary"), dict):
        skills_data["summary"]["publishedToOpenClaw"] = published_count

    return {
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "generatedAgo": "刚刚",
        "openclawDir": str(openclaw_dir),
        "routerAgentId": router_agent_id,
        "theme": {
            "name": theme_name,
            "displayName": metadata.get("displayName", theme_name),
            "language": THEME_CATALOG.get(theme_name, {}).get("language", "zh-CN"),
            "styles": theme_style,
        },
        "themeCatalog": theme_catalog,
        "ownerTitle": kanban_cfg.get("owner_title", "用户"),
        "agents": agent_cards,
        "tasks": active_tasks[:24],
        "taskIndex": task_index[:72],
        "deliverables": deliverables[:24],
        "events": global_events[:42],
        "relays": relays,
        "commands": product_commands,
        "admin": admin_data,
        "management": management_data,
        "orchestration": orchestration_data,
        "conversations": conversation_data,
        "skills": skills_data,
        "openclaw": openclaw_data,
        "contextHub": context_hub_data,
        "metrics": {
            "activeTasks": len(active_tasks),
            "activeAgents": active_agent_count,
            "blockedTasks": blocked_total,
            "completedToday": completed_today,
            "handoffs24h": sum(item["count"] for item in relays),
            "signals1h": signal_count,
        },
    }


def normalize_for_signature(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key in {"signature", "generatedAt", "generatedAgo"} or key.endswith("Ago"):
                continue
            cleaned[key] = normalize_for_signature(item)
        return cleaned
    if isinstance(value, list):
        return [normalize_for_signature(item) for item in value]
    return value


def dashboard_signature(data):
    raw = json.dumps(normalize_for_signature(data), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def safe_json_for_script(data):
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def render_html(data):
    styles = data["theme"]["styles"]
    style_vars = "\n".join(
        [
            f"      --bg: {styles['bg']};",
            f"      --bg2: {styles['bg2']};",
            f"      --ink: {styles['ink']};",
            f"      --muted: {styles['muted']};",
            f"      --accent: {styles['accent']};",
            f"      --accentStrong: {styles['accentStrong']};",
            f"      --accentSoft: {styles['accentSoft']};",
            f"      --panel: {styles['panel']};",
            f"      --line: {styles['line']};",
            f"      --ok: {styles['ok']};",
            f"      --warn: {styles['warn']};",
            f"      --danger: {styles['danger']};",
        ]
    )
    return (
        HTML_TEMPLATE.replace("__STYLE_VARS__", style_vars)
        .replace("__INITIAL_STATE__", safe_json_for_script(data))
    )


def write_dashboard_files(openclaw_dir, data, output_dir=None):
    openclaw_dir = Path(openclaw_dir)
    output_dir = Path(output_dir) if output_dir else openclaw_dir / "dashboard"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "collaboration-dashboard.json"
    html_path = output_dir / "collaboration-dashboard.html"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    return {"json": json_path, "html": html_path}


def build_dashboard_bundle(openclaw_dir, output_dir=None):
    data = build_dashboard_data(openclaw_dir)
    data["signature"] = dashboard_signature(data)
    paths = write_dashboard_files(openclaw_dir, data, output_dir=output_dir)
    return data, paths


def read_env_value(openclaw_dir, key):
    env_path = Path(openclaw_dir) / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, value = line.split("=", 1)
        if current_key == key:
            return value.strip()
    return ""


def dashboard_dir(openclaw_dir):
    path = Path(openclaw_dir) / "dashboard"
    path.mkdir(parents=True, exist_ok=True)
    return path


def users_store_path(openclaw_dir):
    return dashboard_dir(openclaw_dir) / "product_users.json"


def audit_log_path(openclaw_dir):
    return dashboard_dir(openclaw_dir) / "audit-log.jsonl"


def normalize_username(value):
    return str(value or "").strip().lower()


def role_meta(role):
    return USER_ROLES.get(role, USER_ROLES["viewer"])


def permissions_for_role(role):
    return {
        "read": "read" in role_meta(role)["permissions"],
        "taskWrite": "task_write" in role_meta(role)["permissions"],
        "conversationWrite": "conversation_write" in role_meta(role)["permissions"],
        "themeWrite": "theme_write" in role_meta(role)["permissions"],
        "adminWrite": "admin_write" in role_meta(role)["permissions"],
        "auditView": "audit_view" in role_meta(role)["permissions"],
    }


def encode_base64url(raw):
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def decode_base64url(raw):
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def hash_password(password, salt=None, iterations=PASSWORD_HASH_ITERATIONS):
    if not password:
        raise ValueError("password required")
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        encode_base64url(salt_bytes),
        encode_base64url(digest),
    )


def verify_password(password, encoded):
    try:
        algorithm, iterations_text, salt_text, digest_text = str(encoded).split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = hash_password(
            password,
            salt=decode_base64url(salt_text),
            iterations=int(iterations_text),
        )
        return hmac.compare_digest(expected, encoded)
    except Exception:
        return False


def load_product_users(openclaw_dir):
    return store_load_product_users(openclaw_dir)


def save_product_users(openclaw_dir, users):
    return store_save_product_users(openclaw_dir, users)


def safe_user_record(user):
    role = user.get("role", "viewer")
    meta = role_meta(role)
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "displayName": user.get("displayName") or user.get("username"),
        "role": role,
        "roleLabel": meta["label"],
        "roleDescription": meta["description"],
        "status": user.get("status", "active"),
        "createdAt": user.get("createdAt", ""),
        "lastLoginAt": user.get("lastLoginAt", ""),
    }


def create_product_user(openclaw_dir, username, display_name, role, password):
    username = normalize_username(username)
    if not username:
        raise RuntimeError("用户名不能为空。")
    if role not in USER_ROLES:
        raise RuntimeError(f"未知角色：{role}")
    if len(password or "") < 8:
        raise RuntimeError("密码至少需要 8 位。")
    users = load_product_users(openclaw_dir)
    if any(user["username"] == username for user in users):
        raise RuntimeError(f"账号 {username} 已存在。")
    user = {
        "id": secrets.token_hex(8),
        "username": username,
        "displayName": (display_name or username).strip(),
        "role": role,
        "passwordHash": hash_password(password),
        "status": "active",
        "createdAt": now_iso(),
        "lastLoginAt": "",
    }
    users.append(user)
    save_product_users(openclaw_dir, users)
    return safe_user_record(user)


def find_product_user_entry(users, username):
    normalized = normalize_username(username)
    for index, user in enumerate(users):
        if user["username"] == normalized:
            return index, user
    return -1, None


def ensure_active_owner_guard(users, target_user, next_role=None, next_status=None):
    if not target_user:
        return
    current_role = target_user.get("role", "viewer")
    current_status = target_user.get("status", "active")
    role_after = next_role or current_role
    status_after = next_status or current_status
    active_owners = [
        user for user in users if user.get("role") == "owner" and user.get("status", "active") == "active"
    ]
    target_is_last_active_owner = (
        current_role == "owner"
        and current_status == "active"
        and len(active_owners) <= 1
    )
    if target_is_last_active_owner and (role_after != "owner" or status_after != "active"):
        raise RuntimeError("至少要保留一个激活状态的 Owner，不能把最后一个 Owner 降级或停用。")


def update_product_user_access(openclaw_dir, username, role, status):
    username = normalize_username(username)
    if not username:
        raise RuntimeError("请先选择一个团队账号。")
    if role not in USER_ROLES:
        raise RuntimeError(f"未知角色：{role}")
    if status not in {"active", "suspended"}:
        raise RuntimeError(f"未知账号状态：{status}")
    users = load_product_users(openclaw_dir)
    index, user = find_product_user_entry(users, username)
    if not user:
        raise RuntimeError(f"账号 {username} 不存在。")
    ensure_active_owner_guard(users, user, next_role=role, next_status=status)
    users[index]["role"] = role
    users[index]["status"] = status
    save_product_users(openclaw_dir, users)
    return safe_user_record(users[index])


def reset_product_user_password(openclaw_dir, username, password):
    username = normalize_username(username)
    if not username:
        raise RuntimeError("请先选择一个团队账号。")
    if len(password or "") < 8:
        raise RuntimeError("重置后的密码至少需要 8 位。")
    users = load_product_users(openclaw_dir)
    index, user = find_product_user_entry(users, username)
    if not user:
        raise RuntimeError(f"账号 {username} 不存在。")
    users[index]["passwordHash"] = hash_password(password)
    save_product_users(openclaw_dir, users)
    return safe_user_record(users[index])


def update_product_user_login(openclaw_dir, username):
    users = load_product_users(openclaw_dir)
    updated = False
    for user in users:
        if user["username"] == normalize_username(username):
            user["lastLoginAt"] = now_iso()
            updated = True
            break
    if updated:
        save_product_users(openclaw_dir, users)


def append_audit_event(openclaw_dir, action, actor, outcome="success", detail="", meta=None):
    return store_append_audit_event(openclaw_dir, action, actor, outcome=outcome, detail=detail, meta=meta)


def load_audit_events(openclaw_dir, limit=80):
    return store_load_audit_events(openclaw_dir, limit=limit)


def default_installation_label(config, openclaw_dir):
    metadata = load_project_metadata(openclaw_dir, config=config)
    theme_name = metadata.get("theme", "imperial")
    return (
        metadata.get("displayName")
        or THEME_CATALOG.get(theme_name, {}).get("displayName")
        or Path(openclaw_dir).expanduser().name
        or str(openclaw_dir)
    )


def sync_current_installation_registry(openclaw_dir, config):
    resolved_dir = str(Path(openclaw_dir).expanduser().resolve())
    metadata = load_project_metadata(openclaw_dir, config=config)
    return store_upsert_product_installation(
        openclaw_dir,
        {
            "openclawDir": resolved_dir,
            "label": default_installation_label(config, resolved_dir),
            "projectDir": str(metadata.get("projectDir", "")).strip(),
            "theme": str(metadata.get("theme", "imperial")).strip(),
            "routerAgentId": get_router_agent_id(config),
        },
    )


def summarize_installation_record(current_openclaw_dir, installation, now):
    openclaw_path = Path(str(installation.get("openclawDir", "") or "")).expanduser()
    current_path = Path(current_openclaw_dir).expanduser().resolve()
    resolved_target = openclaw_path.resolve() if openclaw_path.exists() else openclaw_path
    summary = {
        "id": installation.get("id", ""),
        "label": installation.get("label") or openclaw_path.name or str(openclaw_path),
        "openclawDir": str(openclaw_path),
        "projectDir": installation.get("projectDir", ""),
        "theme": installation.get("theme", ""),
        "themeLabel": THEME_CATALOG.get(installation.get("theme", ""), {}).get("displayName", installation.get("theme", "") or "未知主题"),
        "routerAgentId": installation.get("routerAgentId", ""),
        "agentCount": 0,
        "activeTasks": 0,
        "blockedTasks": 0,
        "status": "missing",
        "statusLabel": "目录缺失",
        "statusNote": "登记的 OpenClaw 目录当前不存在，建议检查路径或移除旧实例。",
        "updatedAt": installation.get("updatedAt", ""),
        "updatedAgo": format_age(parse_iso(installation.get("updatedAt")), now),
        "current": resolved_target == current_path,
    }
    config_path = openclaw_path / "openclaw.json"
    if not openclaw_path.exists():
        return summary
    if not config_path.exists():
        summary["status"] = "broken"
        summary["statusLabel"] = "缺少配置"
        summary["statusNote"] = "目录存在，但没有找到 openclaw.json。"
        return summary
    try:
        config = load_config(openclaw_path)
        metadata = load_project_metadata(openclaw_path, config=config)
        theme_name = metadata.get("theme", "") or summary["theme"] or "imperial"
        tasks = merge_tasks(openclaw_path, config)
        active_tasks = 0
        blocked_tasks = 0
        for task in tasks:
            state = str(task.get("state", task.get("status", ""))).lower()
            if state not in TERMINAL_STATES:
                active_tasks += 1
            if state == "blocked":
                blocked_tasks += 1
        generated_at = ""
        dashboard_snapshot = load_json(openclaw_path / "dashboard" / "collaboration-dashboard.json", {})
        if isinstance(dashboard_snapshot, dict):
            generated_at = dashboard_snapshot.get("generatedAt", "") or ""
        updated_at = generated_at or installation.get("updatedAt", "")
        summary.update(
            {
                "label": metadata.get("displayName") or summary["label"],
                "projectDir": metadata.get("projectDir", "") or summary["projectDir"],
                "theme": theme_name,
                "themeLabel": THEME_CATALOG.get(theme_name, {}).get("displayName", theme_name),
                "routerAgentId": get_router_agent_id(config),
                "agentCount": len(load_agents(config)),
                "activeTasks": active_tasks,
                "blockedTasks": blocked_tasks,
                "status": "current" if summary["current"] else "ready",
                "statusLabel": "当前实例" if summary["current"] else "可管理",
                "statusNote": "本地路径可达，配置完整，可以纳入产品控制平面。" if not summary["current"] else "这就是你当前打开的 Mission Control 所属实例。",
                "updatedAt": updated_at,
                "updatedAgo": format_age(parse_iso(updated_at), now) if updated_at else summary["updatedAgo"],
            }
        )
        return summary
    except Exception as error:
        summary["status"] = "broken"
        summary["statusLabel"] = "读取失败"
        summary["statusNote"] = f"读取安装实例时发生异常：{error}"
        return summary


def register_installation(openclaw_dir, target_dir, label=""):
    raw_target = str(target_dir or "").strip()
    if not raw_target:
        raise RuntimeError("请先输入 OpenClaw 安装目录。")
    candidate = Path(raw_target).expanduser()
    if not candidate.exists():
        raise RuntimeError(f"目录不存在：{candidate}")
    resolved = candidate.resolve()
    config_path = resolved / "openclaw.json"
    if not config_path.exists():
        raise RuntimeError(f"目录 {resolved} 中没有找到 openclaw.json。")
    config = load_config(resolved)
    if not load_agents(config):
        raise RuntimeError("该安装目录的 openclaw.json 没有可识别的 agents。")
    metadata = load_project_metadata(resolved, config=config)
    theme_name = metadata.get("theme", "imperial")
    entry = store_upsert_product_installation(
        openclaw_dir,
        {
            "openclawDir": str(resolved),
            "label": str(label or "").strip() or default_installation_label(config, resolved),
            "projectDir": str(metadata.get("projectDir", "")).strip(),
            "theme": theme_name,
            "routerAgentId": get_router_agent_id(config),
        },
    )
    return entry


def remove_installation(openclaw_dir, target_dir):
    raw_target = str(target_dir or "").strip()
    if not raw_target:
        raise RuntimeError("请先选择要移除的安装实例。")
    current_dir = str(Path(openclaw_dir).expanduser().resolve())
    candidate = str(Path(raw_target).expanduser().resolve())
    if candidate == current_dir:
        raise RuntimeError("不能移除当前正在运行的 Mission Control 实例。")
    if not store_delete_product_installation(openclaw_dir, candidate):
        raise RuntimeError("指定的安装实例不存在。")
    return candidate


def find_tenant_record(openclaw_dir, tenant_ref):
    tenant_ref = str(tenant_ref or "").strip()
    if not tenant_ref:
        return None
    for tenant in store_list_tenants(openclaw_dir):
        if tenant.get("id") == tenant_ref or tenant.get("slug") == tenant_ref:
            return tenant
    return None


def tenant_primary_openclaw_dir(openclaw_dir, tenant):
    if not tenant:
        return None
    candidate = str(tenant.get("primaryOpenclawDir", "")).strip()
    if candidate:
        return Path(candidate).expanduser().resolve()
    installations = store_list_tenant_installations(openclaw_dir, tenant.get("id", ""))
    primary = next((item for item in installations if item.get("role") == "primary"), None)
    if primary and primary.get("openclawDir"):
        return Path(primary["openclawDir"]).expanduser().resolve()
    if installations and installations[0].get("openclawDir"):
        return Path(installations[0]["openclawDir"]).expanduser().resolve()
    return None


def build_tenant_admin_data(openclaw_dir, now):
    tenants = store_list_tenants(openclaw_dir)
    tenant_installations = store_list_tenant_installations(openclaw_dir)
    installation_registry = {
        item.get("openclawDir"): item
        for item in store_load_product_installations(openclaw_dir)
    }
    api_keys_by_tenant = defaultdict(list)
    for item in store_list_tenant_api_keys(openclaw_dir):
        api_keys_by_tenant[item.get("tenantId", "")].append(item)

    installation_groups = defaultdict(list)
    for item in tenant_installations:
        installation_groups[item.get("tenantId", "")].append(item)

    items = []
    for tenant in tenants:
        primary_dir = tenant_primary_openclaw_dir(openclaw_dir, tenant)
        tenant_summary = None
        if primary_dir and primary_dir.exists():
            try:
                tenant_config = load_config(primary_dir)
                tenant_tasks = merge_tasks(primary_dir, tenant_config)
                tenant_summary = {
                    "taskIndex": tenant_tasks,
                    "agents": load_agents(tenant_config),
                    "generatedAt": max(
                        [item.get("updatedAt", "") for item in tenant_tasks if item.get("updatedAt")] or [now_iso()]
                    ),
                }
            except Exception:
                tenant_summary = None
        installations = installation_groups.get(tenant.get("id", ""), [])
        task_index = (tenant_summary or {}).get("taskIndex", [])
        agents = (tenant_summary or {}).get("agents", [])
        items.append(
            {
                **tenant,
                "statusLabel": "Active" if tenant.get("status") == "active" else "Suspended",
                "primaryOpenclawDir": str(primary_dir) if primary_dir else tenant.get("primaryOpenclawDir", ""),
                "installationCount": len(installations),
                "activeTasks": sum(
                    1
                    for task in task_index
                    if str(task.get("state", "")).strip().lower() not in TERMINAL_STATES
                ),
                "blockedTasks": sum(1 for task in task_index if task.get("blocked")),
                "agentCount": len(agents),
                "apiKeyCount": len(api_keys_by_tenant.get(tenant.get("id", ""), [])),
                "lastUpdatedAt": (tenant_summary or {}).get("generatedAt", ""),
                "lastUpdatedAgo": format_age(parse_iso((tenant_summary or {}).get("generatedAt", "")), now)
                if (tenant_summary or {}).get("generatedAt")
                else "未同步",
                "installations": [
                    {
                        **item,
                        "theme": installation_registry.get(item.get("openclawDir", ""), {}).get("theme", ""),
                        "registeredLabel": installation_registry.get(item.get("openclawDir", ""), {}).get("label", item.get("label", "")),
                    }
                    for item in installations
                ],
            }
        )

    return {
        "items": items,
        "installations": tenant_installations,
        "apiKeys": [
            {
                **item,
                "tenantName": next(
                    (tenant.get("name") for tenant in tenants if tenant.get("id") == item.get("tenantId")),
                    item.get("tenantId", ""),
                ),
            }
            for item in store_list_tenant_api_keys(openclaw_dir)
        ],
        "summary": {
            "total": len(items),
            "active": sum(1 for item in items if item.get("status") == "active"),
            "installations": len(tenant_installations),
            "apiKeys": sum(len(values) for values in api_keys_by_tenant.values()),
        },
    }


def api_scope_allows(granted_scopes, required_scope):
    required_scope = str(required_scope or "").strip()
    scopes = {str(item).strip() for item in granted_scopes or [] if str(item).strip()}
    if not required_scope:
        return True
    if "*" in scopes or required_scope in scopes:
        return True
    resource, _, action = required_scope.partition(":")
    if resource and f"{resource}:*" in scopes:
        return True
    if action and f"*:{action}" in scopes:
        return True
    if "tenant:read" in scopes and action == "read":
        return True
    return False


def build_admin_data(openclaw_dir, config, now, include_sensitive=True):
    sync_current_installation_registry(openclaw_dir, config)
    users = [safe_user_record(user) for user in load_product_users(openclaw_dir)]
    audit_events = load_audit_events(openclaw_dir, limit=60)
    installations = [
        summarize_installation_record(openclaw_dir, item, now)
        for item in store_load_product_installations(openclaw_dir)
    ]
    counts = Counter(user["role"] for user in users)
    status_counts = Counter(user.get("status", "active") for user in users)
    actions_24h = 0
    failed_logins_24h = 0
    recent_events = []
    for event in audit_events:
        at = parse_iso(event.get("at"))
        if at and at >= now - timedelta(hours=24):
            actions_24h += 1
            if event.get("action") == "login" and event.get("outcome") != "success":
                failed_logins_24h += 1
        actor = event.get("actor", {})
        recent_events.append(
            {
                "id": event.get("id"),
                "action": event.get("action", "event"),
                "outcome": event.get("outcome", "success"),
                "headline": event.get("detail") or event.get("action", "event"),
                "detail": event.get("meta", {}),
                "actor": actor.get("displayName") or actor.get("username") or "system",
                "role": actor.get("role", ""),
                "at": event.get("at", ""),
                "atAgo": format_age(at, now) if at else "未知时间",
            }
        )
    role_matrix = [
        {
            "role": role,
            "label": meta["label"],
            "description": meta["description"],
            "permissions": permissions_for_role(role),
        }
        for role, meta in USER_ROLES.items()
    ]
    metadata = load_project_metadata(openclaw_dir, config=config)
    tenant_admin = build_tenant_admin_data(openclaw_dir, now)
    return {
        "workspace": {
            "displayName": metadata.get("displayName") or metadata.get("theme", "Mission Control"),
            "projectDir": metadata.get("projectDir", ""),
            "openclawDir": str(openclaw_dir),
            "storagePath": str(dashboard_store_path(openclaw_dir)),
        },
        "instanceSummary": {
            "total": len(installations),
            "reachable": sum(1 for item in installations if item.get("status") in {"ready", "current"}),
            "broken": sum(1 for item in installations if item.get("status") == "broken"),
            "missing": sum(1 for item in installations if item.get("status") == "missing"),
            "activeTasks": sum(int(item.get("activeTasks") or 0) for item in installations),
        },
        "seatSummary": {
            "total": len(users),
            "owner": counts["owner"],
            "operator": counts["operator"],
            "viewer": counts["viewer"],
            "active": status_counts["active"],
            "suspended": status_counts["suspended"],
            "actions24h": actions_24h,
            "failedLogins24h": failed_logins_24h,
        },
        "instances": installations if include_sensitive else [item for item in installations if item.get("current")],
        "users": users if include_sensitive else [],
        "auditEvents": recent_events[:32] if include_sensitive else [],
        "roleMatrix": role_matrix,
        "tenants": tenant_admin["items"] if include_sensitive else [],
        "tenantInstallations": tenant_admin["installations"] if include_sensitive else [],
        "tenantApiKeys": tenant_admin["apiKeys"] if include_sensitive else [],
        "tenantSummary": tenant_admin["summary"],
        "hasUsers": bool(users),
    }


def resolve_dashboard_auth_token(openclaw_dir):
    for key in ("DASHBOARD_AUTH_TOKEN", "GATEWAY_AUTH_TOKEN"):
        value = os.environ.get(key) or read_env_value(openclaw_dir, key)
        if value:
            return value
    return ""


def sign_session_payload(auth_token, payload_text):
    return hmac.new(auth_token.encode("utf-8"), payload_text.encode("utf-8"), hashlib.sha256).hexdigest()


def encode_session_cookie(auth_token, session_data):
    payload = encode_base64url(json.dumps(session_data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{sign_session_payload(auth_token, payload)}"


def decode_session_cookie(auth_token, cookie_value):
    try:
        payload, signature = str(cookie_value or "").split(".", 1)
        if not hmac.compare_digest(signature, sign_session_payload(auth_token, payload)):
            return None
        data = json.loads(decode_base64url(payload).decode("utf-8"))
        expires_at = parse_iso(data.get("expiresAt"))
        if expires_at and expires_at < now_utc():
            return None
        return data
    except Exception:
        return None


def expected_action_value(auth_token):
    if not auth_token:
        return ""
    return hmac.new(auth_token.encode("utf-8"), b"sansheng-liubu-dashboard-actions", hashlib.sha256).hexdigest()


def resolve_project_dir(openclaw_dir, config=None):
    env_project_dir = os.environ.get("SANSHENG_LIUBU_PROJECT_DIR", "").strip()
    if env_project_dir:
        candidate = Path(env_project_dir).expanduser().resolve()
        if (candidate / "bin" / "switch_theme.py").exists():
            return candidate

    config = config or load_config(openclaw_dir)
    metadata = load_project_metadata(openclaw_dir, config=config)
    project_dir = str(metadata.get("projectDir", "")).strip()
    if project_dir:
        candidate = Path(project_dir).expanduser().resolve()
        if (candidate / "bin" / "switch_theme.py").exists():
            return candidate

    for parent in Path(__file__).resolve().parents:
        if (parent / "bin" / "switch_theme.py").exists() and (parent / "themes").exists():
            return parent
    return None


def runtime_script_path(openclaw_dir, script_name):
    config = load_config(openclaw_dir)
    router_agent_id = get_router_agent_id(config)
    candidate = Path(openclaw_dir) / f"workspace-{router_agent_id}" / "scripts" / script_name
    if candidate.exists():
        return candidate
    fallback = Path(__file__).resolve().with_name(script_name)
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"Missing runtime script: {script_name}")


def openclaw_command_env(openclaw_dir):
    env = os.environ.copy()
    resolved_dir = str(Path(openclaw_dir).expanduser().resolve())
    env["OPENCLAW_STATE_DIR"] = resolved_dir
    env["OPENCLAW_CONFIG_PATH"] = str(Path(resolved_dir) / "openclaw.json")
    return env


def run_command(args, cwd=None, env=None):
    process = subprocess.run(
        [str(arg) for arg in args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=False,
    )
    return process


def run_python_script(script_path, args, cwd=None):
    process = run_command(["python3", str(script_path), *[str(arg) for arg in args]], cwd=cwd)
    output_parts = [part.strip() for part in (process.stdout, process.stderr) if part and part.strip()]
    return process, "\n".join(output_parts)


def openclaw_browser_command(profile=""):
    args = ["openclaw", "browser"]
    normalized = str(profile or "").strip()
    if normalized:
        args.extend(["--browser-profile", normalized])
    return args


def join_command_output(process):
    return "\n".join(part.strip() for part in (process.stdout, process.stderr) if part and part.strip()).strip()


def context_hub_bin():
    explicit = str(os.environ.get("CHUB_BIN", "")).strip()
    if explicit:
        return explicit
    return shutil.which("chub") or ""


def parse_context_hub_version(text):
    for line in str(text or "").splitlines():
        line = line.strip()
        if "Context Hub CLI v" in line:
            return line.rsplit("v", 1)[-1].strip()
    return ""


def context_hub_config_path():
    return Path.home() / ".chub" / "config.yaml"


def context_hub_annotations_path():
    return Path.home() / ".chub" / "annotations"


def summarize_context_hub_config(path):
    summary = {
        "path": str(path),
        "exists": path.exists(),
        "sourceCount": 0,
        "sourcePolicy": "",
        "refreshInterval": "",
        "telemetry": "",
        "feedback": "",
    }
    if not path.exists():
        return summary
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("- name:"):
                summary["sourceCount"] += 1
            elif line.startswith("source:"):
                summary["sourcePolicy"] = line.split(":", 1)[1].strip().strip('"')
            elif line.startswith("refresh_interval:"):
                summary["refreshInterval"] = line.split(":", 1)[1].strip()
            elif line.startswith("telemetry:"):
                summary["telemetry"] = line.split(":", 1)[1].strip()
            elif line.startswith("feedback:"):
                summary["feedback"] = line.split(":", 1)[1].strip()
    except Exception:
        return summary
    return summary


def run_context_hub_command(args, cwd=None):
    binary = context_hub_bin()
    if not binary:
        raise RuntimeError("当前环境未安装 Context Hub CLI（chub）。")
    return run_command([binary, *[str(arg) for arg in args]], cwd=cwd)


def load_context_hub_data(openclaw_dir):
    def build():
        binary = context_hub_bin()
        config_path = context_hub_config_path()
        annotations_path = context_hub_annotations_path()
        config_summary = summarize_context_hub_config(config_path)
        data = {
            "supported": True,
            "installed": bool(binary),
            "binary": binary,
            "version": "",
            "status": "warning",
            "config": config_summary,
            "cache": {"exists": False, "sources": []},
            "annotations": {
                "path": str(annotations_path),
                "total": 0,
                "items": [],
            },
            "recommended": [
                {"label": "OpenAI SDK", "query": "openai", "id": "openai/chat"},
                {"label": "Browser automation", "query": "browser automation", "id": "playwright"},
                {"label": "Stripe payments", "query": "stripe payments", "id": "stripe/api"},
                {"label": "Supabase", "query": "supabase", "id": "supabase"},
            ],
            "commands": [
                {
                    "label": "Search docs",
                    "command": "chub search openai --json",
                    "description": "搜索最新可用文档和技能。",
                },
                {
                    "label": "Fetch a doc",
                    "command": "chub get openai/chat --lang py --json",
                    "description": "抓取指定文档正文，支持语言和增量文件。",
                },
                {
                    "label": "List annotations",
                    "command": "chub annotate --list --json",
                    "description": "查看本机已经积累的注释记忆。",
                },
                {
                    "label": "Refresh registry",
                    "command": "chub update --json",
                    "description": "更新 Context Hub 本地 registry 缓存。",
                },
            ],
        }
        if not binary:
            return data

        help_result = run_context_hub_command(["help"])
        data["version"] = parse_context_hub_version(help_result.stdout or help_result.stderr)

        cache_result = run_context_hub_command(["cache", "status", "--json"])
        cache_payload = parse_json_payload(cache_result.stdout, cache_result.stderr, default={"exists": False, "sources": []})
        if isinstance(cache_payload, dict):
            data["cache"] = cache_payload

        annotations_result = run_context_hub_command(["annotate", "--list", "--json"])
        annotation_items = parse_json_payload(annotations_result.stdout, annotations_result.stderr, default=[])
        if isinstance(annotation_items, list):
            data["annotations"] = {
                "path": str(annotations_path),
                "total": len(annotation_items),
                "items": annotation_items[:20],
            }

        data["status"] = "ready" if data["installed"] else "warning"
        return data

    return cached_payload(("context-hub", str(Path(openclaw_dir).expanduser().resolve())), 10, build)


def perform_context_hub_install():
    process = run_command(["npm", "install", "-g", "@aisuite/chub"])
    output = join_command_output(process)
    if process.returncode != 0:
        raise RuntimeError(output or "安装 Context Hub CLI 失败。")
    help_result = run_context_hub_command(["help"])
    return {
        "installed": True,
        "version": parse_context_hub_version(help_result.stdout or help_result.stderr),
        "output": output or join_command_output(help_result),
    }


def perform_context_hub_update():
    process = run_context_hub_command(["update", "--json"])
    payload = parse_json_payload(process.stdout, process.stderr, default=None)
    output = join_command_output(process)
    if process.returncode != 0 and payload is None:
        raise RuntimeError(output or "更新 Context Hub registry 失败。")
    return {"payload": payload, "output": output}


def perform_context_hub_search(query, lang="", tags="", limit=8):
    normalized_query = str(query or "").strip()
    if not normalized_query:
        raise RuntimeError("请先输入要检索的内容。")
    args = ["search", normalized_query, "--json", "--limit", str(limit or 8)]
    if lang:
        args.extend(["--lang", lang])
    if tags:
        args.extend(["--tags", tags])
    process = run_context_hub_command(args)
    payload = parse_json_payload(process.stdout, process.stderr, default=None)
    if process.returncode != 0 or not isinstance(payload, dict):
        raise RuntimeError(join_command_output(process) or "Context Hub 搜索失败。")
    return payload


def perform_context_hub_get(entry_id, lang="", full=False, files=""):
    normalized_id = str(entry_id or "").strip()
    if not normalized_id:
        raise RuntimeError("请先输入要获取的文档 ID。")
    args = ["get", normalized_id, "--json"]
    if lang:
        args.extend(["--lang", lang])
    if full:
        args.append("--full")
    if files:
        args.extend(["--file", files])
    process = run_context_hub_command(args)
    payload = parse_json_payload(process.stdout, process.stderr, default=None)
    if process.returncode != 0 or not isinstance(payload, dict):
        raise RuntimeError(join_command_output(process) or f"获取 Context Hub 文档失败：{normalized_id}")
    return payload


def perform_context_hub_annotate(entry_id, note="", clear=False):
    normalized_id = str(entry_id or "").strip()
    if not normalized_id:
        raise RuntimeError("请先输入要标注的文档 ID。")
    args = ["annotate", normalized_id]
    if clear:
        args.append("--clear")
    else:
        normalized_note = str(note or "").strip()
        if not normalized_note:
            raise RuntimeError("请先输入要保存的 annotation。")
        args.append(normalized_note)
    args.append("--json")
    process = run_context_hub_command(args)
    payload = parse_json_payload(process.stdout, process.stderr, default=None)
    if process.returncode != 0 or not isinstance(payload, dict):
        raise RuntimeError(join_command_output(process) or f"保存 Context Hub annotation 失败：{normalized_id}")
    return payload


def perform_context_hub_feedback(entry_id, rating, comment="", labels=None, lang="", file_path="", agent="", model=""):
    normalized_id = str(entry_id or "").strip()
    normalized_rating = str(rating or "").strip().lower()
    if not normalized_id:
        raise RuntimeError("请先输入要反馈的文档 ID。")
    if normalized_rating not in {"up", "down"}:
        raise RuntimeError("反馈只能是 up 或 down。")
    args = ["feedback", normalized_id, normalized_rating]
    normalized_comment = str(comment or "").strip()
    if normalized_comment:
        args.append(normalized_comment)
    for label in labels or []:
        if str(label).strip():
            args.extend(["--label", str(label).strip()])
    if lang:
        args.extend(["--lang", lang])
    if file_path:
        args.extend(["--file", file_path])
    if agent:
        args.extend(["--agent", agent])
    if model:
        args.extend(["--model", model])
    args.append("--json")
    process = run_context_hub_command(args)
    payload = parse_json_payload(process.stdout, process.stderr, default=None)
    if process.returncode != 0 or not isinstance(payload, dict):
        raise RuntimeError(join_command_output(process) or f"发送 Context Hub feedback 失败：{normalized_id}")
    if payload.get("status") == "error":
        raise RuntimeError(payload.get("reason") or "发送 Context Hub feedback 失败。")
    return payload


def perform_gateway_service_action(openclaw_dir, action):
    action_name = str(action or "").strip().lower()
    if action_name not in {"start", "restart", "stop", "status"}:
        raise RuntimeError(f"不支持的 gateway 动作：{action_name}")
    env = openclaw_command_env(openclaw_dir)
    args = ["openclaw", "gateway", action_name]
    if action_name == "status":
        args.extend(["--require-rpc", "--json"])
    process = run_command(args, env=env)
    payload = parse_json_payload(process.stdout, process.stderr, default=None)
    output = join_command_output(process)
    if process.returncode != 0 and payload is None:
        raise RuntimeError(output or f"gateway {action_name} 执行失败。")
    return {"action": action_name, "payload": payload, "output": output}


def perform_browser_extension_action(openclaw_dir, action):
    action_name = str(action or "").strip().lower()
    if action_name not in {"install", "path"}:
        raise RuntimeError(f"不支持的 browser extension 动作：{action_name}")
    env = openclaw_command_env(openclaw_dir)
    args = ["openclaw", "browser", "extension", action_name]
    process = run_command(args, env=env)
    output = join_command_output(process)
    if process.returncode != 0 and action_name != "path":
        raise RuntimeError(output or f"browser extension {action_name} 执行失败。")
    return {"action": action_name, "output": output, "ok": process.returncode == 0}


def perform_browser_start(openclaw_dir, profile=""):
    env = openclaw_command_env(openclaw_dir)
    process = run_command([*openclaw_browser_command(profile), "start"], env=env)
    output = join_command_output(process)
    if process.returncode != 0:
        raise RuntimeError(output or "browser start 执行失败。")
    return {"output": output}


def perform_browser_create_profile(openclaw_dir, name, driver="openclaw", color="", cdp_url=""):
    profile_name = str(name or "").strip()
    if not profile_name:
        raise RuntimeError("profile 名称不能为空。")
    env = openclaw_command_env(openclaw_dir)
    args = ["openclaw", "browser", "create-profile", "--name", profile_name]
    normalized_driver = str(driver or "").strip()
    if normalized_driver:
        args.extend(["--driver", normalized_driver])
    normalized_color = str(color or "").strip()
    if normalized_color:
        args.extend(["--color", normalized_color])
    normalized_cdp = str(cdp_url or "").strip()
    if normalized_cdp:
        args.extend(["--cdp-url", normalized_cdp])
    process = run_command(args, env=env)
    output = join_command_output(process)
    if process.returncode != 0:
        raise RuntimeError(output or "browser profile 创建失败。")
    return {"name": profile_name, "output": output}


def perform_browser_open(openclaw_dir, url, profile=""):
    normalized_url = str(url or "").strip()
    if not normalized_url:
        raise RuntimeError("URL 不能为空。")
    env = openclaw_command_env(openclaw_dir)
    process = run_command([*openclaw_browser_command(profile), "open", normalized_url], env=env)
    output = join_command_output(process)
    if process.returncode != 0:
        raise RuntimeError(output or "browser open 执行失败。")
    return {"url": normalized_url, "output": output}


def perform_browser_snapshot(openclaw_dir, profile="", selector="", target_id="", limit=120):
    env = openclaw_command_env(openclaw_dir)
    args = [*openclaw_browser_command(profile), "snapshot", "--format", "ai", "--limit", str(limit)]
    normalized_selector = str(selector or "").strip()
    normalized_target = str(target_id or "").strip()
    if normalized_selector:
        args.extend(["--selector", normalized_selector])
    if normalized_target:
        args.extend(["--target-id", normalized_target])
    process = run_command(args, env=env)
    output = join_command_output(process)
    if process.returncode != 0:
        raise RuntimeError(output or "browser snapshot 执行失败。")
    return {"output": output}


def perform_browser_plan(openclaw_dir, steps, profile=""):
    if not isinstance(steps, list) or not steps:
        raise RuntimeError("browser plan 不能为空，且必须是动作数组。")
    env = openclaw_command_env(openclaw_dir)
    results = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise RuntimeError(f"第 {index} 步必须是对象。")
        action = str(step.get("action", "")).strip().lower()
        target_id = str(step.get("targetId", "")).strip()
        args = [*openclaw_browser_command(profile)]
        if action == "open":
            url = str(step.get("url", "")).strip()
            if not url:
                raise RuntimeError(f"第 {index} 步 open 缺少 url。")
            args.extend(["open", url])
        elif action == "snapshot":
            args.extend(["snapshot", "--format", str(step.get("format", "ai") or "ai"), "--limit", str(step.get("limit", 120) or 120)])
            selector = str(step.get("selector", "")).strip()
            if selector:
                args.extend(["--selector", selector])
        elif action == "click":
            ref = str(step.get("ref", "")).strip()
            if not ref:
                raise RuntimeError(f"第 {index} 步 click 缺少 ref。")
            args.extend(["click", ref])
            if step.get("double"):
                args.append("--double")
        elif action == "wait":
            args.append("wait")
            if step.get("time") is not None:
                args.extend(["--time", str(step.get("time"))])
            if step.get("selector"):
                args.append(str(step.get("selector")))
            if step.get("text"):
                args.extend(["--text", str(step.get("text"))])
            if step.get("url"):
                args.extend(["--url", str(step.get("url"))])
        elif action == "fill":
            fields = step.get("fields", [])
            if not isinstance(fields, list) or not fields:
                raise RuntimeError(f"第 {index} 步 fill 缺少 fields。")
            args.extend(["fill", "--fields", json.dumps(fields, ensure_ascii=False)])
        else:
            raise RuntimeError(f"第 {index} 步是不支持的 browser 动作：{action}")

        if target_id:
            args.extend(["--target-id", target_id])
        process = run_command(args, env=env)
        output = join_command_output(process)
        if process.returncode != 0:
            raise RuntimeError(output or f"第 {index} 步 {action} 执行失败。")
        results.append({"index": index, "action": action, "output": output})
    return {"results": results}


def perform_task_create(openclaw_dir, title, remark=""):
    openclaw_dir = Path(openclaw_dir)
    config = load_config(openclaw_dir)
    router_agent_id = get_router_agent_id(config)
    kanban_cfg = load_kanban_config(openclaw_dir, router_agent_id)
    kanban_script = runtime_script_path(openclaw_dir, "kanban_update.py")
    prefix = kanban_cfg.get("task_prefix", "TASK")
    planner_title = kanban_cfg.get("state_org_map", {}).get("Zhongshu") or "Planner"

    next_id_result, next_id_output = run_python_script(kanban_script, ["next-id", prefix])
    if next_id_result.returncode != 0:
        raise RuntimeError(next_id_output or "无法生成新的任务号。")
    task_id = next_id_output.splitlines()[-1].strip()
    if not task_id:
        raise RuntimeError("任务号生成失败。")

    args = ["create", task_id, title, "Zhongshu", planner_title, planner_title]
    if remark:
        args.append(remark)
    create_result, create_output = run_python_script(kanban_script, args)
    if create_result.returncode != 0:
        raise RuntimeError(create_output or "创建任务失败。")
    return task_id


def perform_task_progress(openclaw_dir, task_id, message, todos="", mark_doing=False):
    kanban_script = runtime_script_path(openclaw_dir, "kanban_update.py")
    if mark_doing:
        state_result, state_output = run_python_script(kanban_script, ["state", task_id, "Doing", message])
        if state_result.returncode != 0:
            raise RuntimeError(state_output or "无法把任务切换到执行中。")
    args = ["progress", task_id, message]
    if todos:
        args.append(todos)
    progress_result, progress_output = run_python_script(kanban_script, args)
    if progress_result.returncode != 0:
        raise RuntimeError(progress_output or "进展同步失败。")


def perform_task_block(openclaw_dir, task_id, reason):
    kanban_script = runtime_script_path(openclaw_dir, "kanban_update.py")
    result, output = run_python_script(kanban_script, ["block", task_id, reason])
    if result.returncode != 0:
        raise RuntimeError(output or "阻塞标记失败。")


def perform_task_done(openclaw_dir, task_id, output_path="", summary=""):
    kanban_script = runtime_script_path(openclaw_dir, "kanban_update.py")
    args = ["done", task_id]
    if output_path or summary:
        args.append(output_path)
    if summary:
        args.append(summary)
    result, output = run_python_script(kanban_script, args)
    if result.returncode != 0:
        raise RuntimeError(output or "任务完成写回失败。")


def perform_conversation_send(openclaw_dir, agent_id, message, session_id="", thinking="low"):
    if not agent_id:
        raise RuntimeError("请先选择一个 Agent。")
    text = str(message or "").strip()
    if not text:
        raise RuntimeError("消息不能为空。")
    env = openclaw_command_env(openclaw_dir)
    args = ["openclaw", "agent", "--agent", agent_id, "--message", text, "--json", "--timeout", "120"]
    if session_id:
        args.extend(["--session-id", session_id])
    if thinking:
        args.extend(["--thinking", thinking])
    result = run_command(args, env=env)
    payload = parse_json_payload(result.stdout, result.stderr, default=None)
    if result.returncode != 0 or payload is None:
        raise RuntimeError((result.stderr or result.stdout or "会话发送失败。").strip())
    status = str(payload.get("status", "")).lower()
    if status not in {"ok", "completed", "success"} and payload.get("ok") is False:
        raise RuntimeError(summarize_json(payload))
    return payload


def perform_theme_switch(openclaw_dir, theme_name):
    project_dir = resolve_project_dir(openclaw_dir)
    if not project_dir:
        raise RuntimeError("当前安装没有关联仓库目录，暂时无法在产品内切换主题。")
    switch_script = project_dir / "bin" / "switch_theme.py"
    if not switch_script.exists():
        raise RuntimeError(f"缺少主题切换脚本: {switch_script}")
    result, output = run_python_script(
        switch_script,
        ["--theme", theme_name, "--dir", str(Path(openclaw_dir).expanduser().resolve())],
        cwd=project_dir,
    )
    if result.returncode != 0:
        raise RuntimeError(output or f"切换主题失败: {theme_name}")


def skills_cli_path(openclaw_dir, config=None):
    project_dir = resolve_project_dir(openclaw_dir, config=config)
    if not project_dir:
        return None, None
    cli_path = project_dir / "bin" / "skill_utils.py"
    if not cli_path.exists():
        return project_dir, None
    return project_dir, cli_path


def load_skills_catalog(openclaw_dir, config=None):
    project_dir, cli_path = skills_cli_path(openclaw_dir, config=config)
    if not project_dir or not cli_path:
        return {
            "supported": False,
            "error": "当前安装没有关联可用的 skill 工具脚本。",
            "summary": {"total": 0, "ready": 0, "warning": 0, "error": 0, "packaged": 0, "categories": {}},
            "skills": [],
            "guidance": [],
            "commands": [],
        }

    def build():
        result, output = run_python_script(
            cli_path,
            ["list", "--project-dir", str(project_dir)],
            cwd=project_dir,
        )
        if result.returncode != 0:
            return {
                "supported": False,
                "error": output or "读取技能目录失败。",
                "summary": {"total": 0, "ready": 0, "warning": 0, "error": 0, "packaged": 0, "categories": {}},
                "skills": [],
                "guidance": [],
                "commands": [],
            }

        payload = parse_json_payload(result.stdout, output, default=None)
        if payload is None:
            return {
                "supported": False,
                "error": output or "技能目录输出不是合法 JSON。",
                "summary": {"total": 0, "ready": 0, "warning": 0, "error": 0, "packaged": 0, "categories": {}},
                "skills": [],
                "guidance": [],
                "commands": [],
            }

        payload["supported"] = True
        payload["commands"] = [
            {
                "label": "扫描技能目录",
                "command": f"python3 {cli_path} list --project-dir {project_dir}",
                "description": "查看当前 skills 目录、校验状态和打包准备度。",
            },
            {
                "label": "校验技能质量",
                "command": f"python3 {cli_path} validate --project-dir {project_dir}",
                "description": "按 Anthropic Skills 指南检查 frontmatter、结构和触发质量。",
            },
        ]
        return payload

    return cached_payload(("local-skills", str(project_dir), str(Path(openclaw_dir).expanduser().resolve())), 10, build)


def top_counter_items(counter, limit=6):
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def load_openclaw_control_data(openclaw_dir):
    openclaw_dir = Path(openclaw_dir).expanduser().resolve()

    def build():
        env = openclaw_command_env(openclaw_dir)
        local_config = load_config(openclaw_dir)
        try:
            version_result = run_command(["openclaw", "--version"], env=env)
        except FileNotFoundError:
            return {
                "supported": False,
                "error": "未检测到 openclaw CLI。",
                "version": {"raw": "unknown", "release": "", "build": ""},
                "config": {"valid": False, "path": str(openclaw_dir / "openclaw.json"), "error": "missing_cli"},
                "gateway": {"ok": False, "channels": [], "agentCount": 0, "defaultAgentId": "", "error": "missing_cli"},
                "nativeSkills": {
                    "total": 0,
                    "eligible": 0,
                    "disabled": 0,
                    "blocked": 0,
                    "bundled": 0,
                    "external": 0,
                    "sampleEligible": [],
                    "sampleMissing": [],
                    "missingBins": [],
                    "missingEnv": [],
                    "missingConfig": [],
                    "sourceBreakdown": [],
                    "warnings": [],
                },
                "compatibility": [],
                "commands": [],
                "_nativeSkillNames": [],
            }

        version_raw = (version_result.stdout or version_result.stderr or "").strip()
        release_text = ""
        build_text = ""
        if version_raw.startswith("OpenClaw "):
            after_name = version_raw.split("OpenClaw ", 1)[1]
            if " (" in after_name and after_name.endswith(")"):
                release_text, build_text = after_name[:-1].split(" (", 1)
            else:
                release_text = after_name

        config_result = run_command(["openclaw", "config", "validate", "--json"], env=env)
        config_payload = parse_json_payload(config_result.stdout, config_result.stderr, default=None)
        if config_payload is None:
            config_payload = {
                "valid": False,
                "path": str(openclaw_dir / "openclaw.json"),
                "error": (config_result.stderr or config_result.stdout or "config_validate_failed").strip(),
            }

        health_result = run_command(["openclaw", "gateway", "health", "--json"], env=env)
        health_payload = parse_json_payload(health_result.stdout, health_result.stderr, default=None)
        if health_payload is None:
            health_payload = {
                "ok": False,
                "error": (health_result.stderr or health_result.stdout or "gateway_health_failed").strip(),
                "channels": {},
                "agents": [],
            }

        gateway_status_result = run_command(["openclaw", "gateway", "status", "--require-rpc", "--json"], env=env)
        gateway_status_payload = parse_json_payload(gateway_status_result.stdout, gateway_status_result.stderr, default=None)
        if gateway_status_payload is None:
            gateway_status_payload = {
                "service": {"runtime": {"status": "unknown"}},
                "gateway": {"bindMode": "", "port": None, "probeUrl": ""},
                "rpc": {
                    "ok": False,
                    "error": (gateway_status_result.stderr or gateway_status_result.stdout or "gateway_status_failed").strip(),
                    "url": "",
                },
                "config": {},
            }
        rpc_payload = gateway_status_payload.get("rpc", {}) if isinstance(gateway_status_payload, dict) else {}
        service_payload = gateway_status_payload.get("service", {}) if isinstance(gateway_status_payload, dict) else {}
        gateway_runtime_payload = gateway_status_payload.get("gateway", {}) if isinstance(gateway_status_payload, dict) else {}
        rpc_ok = bool(rpc_payload.get("ok"))

        browser_status_payload = {
            "ok": False,
            "running": False,
            "profile": "",
            "targets": 0,
            "error": rpc_payload.get("error", "") if isinstance(rpc_payload, dict) else "",
        }
        browser_profiles_payload = {"profiles": []}
        if rpc_ok:
            browser_status_result = run_command(["openclaw", "browser", "status", "--json"], env=env)
            parsed_browser_status = parse_json_payload(browser_status_result.stdout, browser_status_result.stderr, default=None)
            if isinstance(parsed_browser_status, dict):
                browser_status_payload = parsed_browser_status
            else:
                browser_status_payload = {
                    "ok": False,
                    "running": False,
                    "profile": "",
                    "targets": 0,
                    "error": (browser_status_result.stderr or browser_status_result.stdout or "browser_status_failed").strip(),
                }

            browser_profiles_result = run_command(["openclaw", "browser", "profiles", "--json"], env=env)
            parsed_browser_profiles = parse_json_payload(browser_profiles_result.stdout, browser_profiles_result.stderr, default=None)
            if isinstance(parsed_browser_profiles, dict):
                browser_profiles_payload = parsed_browser_profiles
            elif isinstance(parsed_browser_profiles, list):
                browser_profiles_payload = {"profiles": parsed_browser_profiles}
            else:
                browser_profiles_payload = {"profiles": []}

        skills_result = run_command(["openclaw", "skills", "list", "--json"], env=env)
        native_skills_payload = parse_json_payload(skills_result.stdout, skills_result.stderr, default={"skills": []})
        native_skill_entries = native_skills_payload.get("skills", []) if isinstance(native_skills_payload, dict) else []
        managed_skills_dir = native_skills_payload.get("managedSkillsDir", "") if isinstance(native_skills_payload, dict) else ""
        workspace_dir = native_skills_payload.get("workspaceDir", "") if isinstance(native_skills_payload, dict) else ""
        skills_check_result = run_command(["openclaw", "skills", "check", "--json"], env=env)
        skills_check_payload = parse_json_payload(skills_check_result.stdout, skills_check_result.stderr, default={"summary": {}, "missingRequirements": []})
        if not isinstance(skills_check_payload, dict):
            skills_check_payload = {"summary": {}, "missingRequirements": []}

        source_counter = Counter(item.get("source", "unknown") for item in native_skill_entries)
        missing_bins = Counter()
        missing_env = Counter()
        missing_config = Counter()
        sample_eligible = []
        sample_missing = []
        native_skill_names = []
        bundled = 0
        external = 0
        disabled = 0
        blocked = 0
        eligible = 0
        for item in native_skill_entries:
            name = item.get("name", "")
            if name:
                native_skill_names.append(name)
            if item.get("bundled"):
                bundled += 1
            else:
                external += 1
            if item.get("disabled"):
                disabled += 1
            if item.get("blockedByAllowlist"):
                blocked += 1
            if item.get("eligible"):
                eligible += 1
                if len(sample_eligible) < 8:
                    sample_eligible.append(
                        {
                            "title": item.get("name", "unknown"),
                            "meta": f"{item.get('source', 'unknown')} · {'bundled' if item.get('bundled') else 'external'}",
                            "detail": item.get("description", ""),
                        }
                    )
            missing = item.get("missing", {}) if isinstance(item.get("missing"), dict) else {}
            for bin_name in missing.get("bins", []) or []:
                missing_bins[bin_name] += 1
            for env_name in missing.get("env", []) or []:
                missing_env[env_name] += 1
            for config_name in missing.get("config", []) or []:
                missing_config[config_name] += 1
            if not item.get("eligible") and len(sample_missing) < 8:
                reasons = []
                if missing.get("bins"):
                    reasons.append(f"缺少命令: {', '.join(missing.get('bins', [])[:2])}")
                if missing.get("env"):
                    reasons.append(f"缺少环境变量: {', '.join(missing.get('env', [])[:2])}")
                if missing.get("config"):
                    reasons.append(f"缺少配置: {', '.join(missing.get('config', [])[:2])}")
                sample_missing.append(
                    {
                        "title": item.get("name", "unknown"),
                        "meta": item.get("source", "unknown"),
                        "detail": " · ".join(reasons) or item.get("description", ""),
                    }
                )

        browser_profiles = browser_profiles_payload.get("profiles", []) if isinstance(browser_profiles_payload, dict) else []
        normalized_browser_profiles = []
        preferred_profile_names = {"user", "chrome-relay"}
        browser_profile_names = set()
        for item in browser_profiles:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("profile") or item.get("id") or "").strip()
            if not name:
                continue
            browser_profile_names.add(name)
            normalized_browser_profiles.append(
                {
                    "name": name,
                    "running": bool(item.get("running")),
                    "detail": item.get("description") or item.get("path") or item.get("label") or "",
                }
            )
        recommended_profiles = [
            {
                "name": "user",
                "title": "user",
                "detail": "复用用户已登录的本地 Chrome / Chromium 会话，适合真实业务站点联调。",
                "available": "user" in browser_profile_names,
            },
            {
                "name": "chrome-relay",
                "title": "chrome-relay",
                "detail": "通过 Chrome relay / DevTools attach 连接浏览器，适合新版浏览器自动化能力。",
                "available": "chrome-relay" in browser_profile_names,
            },
        ]

        channel_entries = []
        health_channels = health_payload.get("channels", {}) if isinstance(health_payload, dict) else {}
        channel_order = health_payload.get("channelOrder", []) if isinstance(health_payload, dict) else []
        health_labels = health_payload.get("channelLabels", {}) if isinstance(health_payload, dict) else {}
        ordered_names = channel_order or list(health_channels.keys())
        for channel_name in ordered_names:
            channel = health_channels.get(channel_name, {})
            probe = channel.get("probe", {}) if isinstance(channel.get("probe"), dict) else {}
            detail = ""
            if channel_name == "telegram" and isinstance(probe.get("bot"), dict):
                detail = probe["bot"].get("username", "")
            elif channel_name == "feishu":
                detail = probe.get("appId", "")
            channel_entries.append(
                {
                    "title": health_labels.get(channel_name, channel_name),
                    "meta": "configured" if channel.get("configured") else "not configured",
                    "detail": detail or channel.get("lastError") or "无额外信息",
                    "healthy": bool(probe.get("ok")) if probe else bool(channel.get("configured")),
                    "running": bool(channel.get("running")),
                }
            )

        agent_params = []
        config_agents = ((local_config.get("agents", {}) if isinstance(local_config, dict) else {}) or {}).get("list", [])
        for agent in config_agents if isinstance(config_agents, list) else []:
            if not isinstance(agent, dict):
                continue
            params = agent.get("params", {})
            if not params:
                continue
            agent_params.append(
                {
                    "id": agent.get("id", ""),
                    "workspace": agent.get("workspace", ""),
                    "params": params,
                    "summary": ", ".join(f"{key}={value}" for key, value in list(params.items())[:5]),
                }
            )

        compatibility = [
            {
                "title": "OpenClaw 版本",
                "status": "ready" if is_supported_openclaw_release(release_text) else "warning",
                "body": version_raw or "unknown",
                "meta": f"当前产品按 OpenClaw {OPENCLAW_BASELINE_RELEASE}+ 适配。",
            },
            {
                "title": "配置校验",
                "status": "ready" if config_payload.get("valid") else "error",
                "body": "openclaw.json 已通过 schema 校验。" if config_payload.get("valid") else "当前配置未通过 schema 校验。",
                "meta": config_payload.get("path") or str(openclaw_dir / "openclaw.json"),
            },
            {
                "title": "Gateway 健康",
                "status": "ready" if health_payload.get("ok") else "warning",
                "body": "Gateway 健康检查通过。" if health_payload.get("ok") else "Gateway 健康检查失败或未返回结构化结果。",
                "meta": f"channel {len(channel_entries)} · agent {len(health_payload.get('agents', []) or [])}",
            },
            {
                "title": "Gateway RPC",
                "status": "ready" if rpc_ok else "warning",
                "body": "Gateway RPC 严格检查通过。" if rpc_ok else "新版 `gateway status --require-rpc` 未通过，浏览器和部分实时控制能力会受影响。",
                "meta": rpc_payload.get("url") or gateway_runtime_payload.get("probeUrl") or "no rpc url",
            },
            {
                "title": "原生 Skills",
                "status": "ready" if native_skill_entries else "warning",
                "body": f"OpenClaw 当前识别到 {len(native_skill_entries)} 个原生 skills，其中 {eligible} 个可直接使用。",
                "meta": f"bundled {bundled} · external {external}",
            },
            {
                "title": "Managed Skills 目录",
                "status": "ready" if managed_skills_dir else "warning",
                "body": managed_skills_dir or "当前没有返回 managed skills 目录。",
                "meta": workspace_dir or str(openclaw_dir),
            },
            {
                "title": "Browser Live Session",
                "status": "ready" if rpc_ok and preferred_profile_names.intersection(browser_profile_names) else "warning",
                "body": "新版浏览器 live session/profile 能力已可用。" if rpc_ok and preferred_profile_names.intersection(browser_profile_names) else "建议补 browser profile 或先修复 RPC，才能稳定接入新版浏览器能力。",
                "meta": ", ".join(sorted(browser_profile_names)) if browser_profile_names else "recommended: user, chrome-relay",
            },
        ]

        env_prefix = f'OPENCLAW_STATE_DIR="{openclaw_dir}" OPENCLAW_CONFIG_PATH="{openclaw_dir / "openclaw.json"}"'
        return {
            "supported": True,
            "error": "",
            "version": {"raw": version_raw, "release": release_text, "build": build_text},
            "config": config_payload,
            "gateway": {
                "ok": bool(health_payload.get("ok")),
                "durationMs": health_payload.get("durationMs"),
                "defaultAgentId": health_payload.get("defaultAgentId", ""),
                "agentCount": len(health_payload.get("agents", []) or []),
                "channels": channel_entries,
                "error": health_payload.get("error", ""),
                "rpc": {
                    "ok": rpc_ok,
                    "url": rpc_payload.get("url", ""),
                    "error": rpc_payload.get("error", ""),
                    "serviceStatus": (((service_payload.get("runtime", {}) if isinstance(service_payload.get("runtime"), dict) else {}) or {}).get("status", "")),
                    "bindMode": gateway_runtime_payload.get("bindMode", ""),
                    "port": gateway_runtime_payload.get("port"),
                    "probeUrl": gateway_runtime_payload.get("probeUrl", ""),
                },
            },
            "browser": {
                "ok": bool(browser_status_payload.get("ok")) if isinstance(browser_status_payload, dict) else False,
                "running": bool(browser_status_payload.get("running")) if isinstance(browser_status_payload, dict) else False,
                "profile": browser_status_payload.get("profile", "") if isinstance(browser_status_payload, dict) else "",
                "targets": browser_status_payload.get("targets", 0) if isinstance(browser_status_payload, dict) else 0,
                "error": browser_status_payload.get("error", "") if isinstance(browser_status_payload, dict) else "",
                "profiles": normalized_browser_profiles,
                "recommendedProfiles": recommended_profiles,
            },
            "nativeSkills": {
                "total": len(native_skill_entries),
                "eligible": eligible,
                "disabled": disabled,
                "blocked": blocked,
                "bundled": bundled,
                "external": external,
                "managedSkillsDir": managed_skills_dir,
                "workspaceDir": workspace_dir,
                "sampleEligible": sample_eligible,
                "sampleMissing": sample_missing,
                "missingBins": top_counter_items(missing_bins),
                "missingEnv": top_counter_items(missing_env),
                "missingConfig": top_counter_items(missing_config),
                "sourceBreakdown": top_counter_items(source_counter),
                "warnings": [line.strip() for line in (skills_result.stderr or "").splitlines() if line.strip()],
                "check": {
                    "summary": skills_check_payload.get("summary", {}),
                    "missingRequirements": skills_check_payload.get("missingRequirements", []),
                    "warnings": [line.strip() for line in (skills_check_result.stderr or "").splitlines() if line.strip()],
                },
            },
            "agentParams": agent_params,
            "compatibility": compatibility,
            "commands": [
                {
                    "label": "OpenClaw Dashboard",
                    "command": f"{env_prefix} openclaw dashboard --no-open",
                    "description": "输出官方 Control UI 地址，不在浏览器里自动打开。",
                },
                {
                    "label": "Schema 校验",
                    "command": f"{env_prefix} openclaw config validate --json",
                    "description": "校验当前安装目录里的 openclaw.json 是否仍然有效。",
                },
                {
                    "label": "Gateway 健康",
                    "command": f"{env_prefix} openclaw gateway health --json",
                    "description": "获取当前 Gateway、channels、agents 的结构化健康数据。",
                },
                {
                    "label": "Gateway RPC 严格检查",
                    "command": f"{env_prefix} openclaw gateway status --require-rpc --json",
                    "description": "检查新版 Gateway RPC 是否真正在线，适合排查浏览器与实时控制链路。",
                },
                {
                    "label": "Browser Status",
                    "command": f"{env_prefix} openclaw browser status --json",
                    "description": "查看新版浏览器运行态、当前 profile 和实时 attach 状态。",
                },
                {
                    "label": "Browser Profiles",
                    "command": f"{env_prefix} openclaw browser profiles --json",
                    "description": "查看可用的浏览器 profiles，重点关注 `user` 和 `chrome-relay`。",
                },
                {
                    "label": "原生 Skills",
                    "command": f"{env_prefix} openclaw skills list --json",
                    "description": "查看 OpenClaw 当前可识别的 skills 目录和可用性。",
                },
                {
                    "label": "Doctor",
                    "command": f"{env_prefix} openclaw doctor --non-interactive",
                    "description": "运行官方健康检查与修复建议流程。",
                },
                {
                    "label": "Onboard",
                    "command": f"{env_prefix} openclaw onboard",
                    "description": "进入官方 onboarding wizard，配置 gateway、workspace 和 skills。",
                },
            ],
            "_nativeSkillNames": native_skill_names,
        }

    return cached_payload(("openclaw-control", str(openclaw_dir)), 30, build)


def agent_response_latency_samples(openclaw_dir, agent_id, limit=8):
    sessions_dir = Path(openclaw_dir) / "agents" / str(agent_id or "").strip() / "sessions"
    if not sessions_dir.exists():
        return []
    samples = []
    session_files = sorted(
        sessions_dir.glob("*.jsonl"),
        key=lambda item: item.stat().st_mtime if item.exists() else 0,
        reverse=True,
    )[:3]
    for path in session_files:
        pending_user_at = None
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            tail_lines = list(deque(handle, maxlen=140))
        for raw in tail_lines:
            line = raw.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "message":
                continue
            payload = entry.get("message", {}) if isinstance(entry.get("message"), dict) else {}
            role = payload.get("role")
            at = parse_iso(entry.get("timestamp") or payload.get("timestamp"))
            if not at:
                continue
            if role == "user":
                pending_user_at = at
            elif role == "assistant" and pending_user_at:
                delta = max((at - pending_user_at).total_seconds(), 0)
                samples.append(delta)
                pending_user_at = None
    return samples[-limit:]


def compute_agent_health_data(openclaw_dir, agents, task_index, deliverables, now):
    completed_by_agent = Counter()
    recent_completed_by_agent = Counter()
    for task in task_index:
        if str(task.get("state", "")).lower() not in TERMINAL_STATES:
            continue
        agent_id = task.get("currentAgent") or ""
        if not agent_id:
            continue
        completed_by_agent[agent_id] += 1
        updated_dt = parse_iso(task.get("updatedAt"))
        if updated_dt and updated_dt >= now - timedelta(days=7):
            recent_completed_by_agent[agent_id] += 1

    cards = []
    score_bands = {"excellent": 0, "stable": 0, "watch": 0, "critical": 0}
    for agent in agents:
        latency_samples = agent_response_latency_samples(openclaw_dir, agent.get("id"))
        avg_latency_seconds = round(sum(latency_samples) / len(latency_samples), 1) if latency_samples else 0.0
        active = int(agent.get("activeTasks") or 0)
        blocked = int(agent.get("blockedTasks") or 0)
        completed = recent_completed_by_agent[agent.get("id")] or completed_by_agent[agent.get("id")]
        throughput_base = max(active + blocked + completed, 1)
        completion_rate = round((completed / throughput_base) * 100)
        block_rate = round((blocked / throughput_base) * 100)
        if not latency_samples:
            latency_score = 72
        elif avg_latency_seconds <= 90:
            latency_score = 96
        elif avg_latency_seconds <= 240:
            latency_score = 86
        elif avg_latency_seconds <= 480:
            latency_score = 70
        else:
            latency_score = 52
        completion_score = min(100, 50 + completion_rate)
        block_score = max(24, 100 - block_rate)
        score = round(latency_score * 0.25 + completion_score * 0.45 + block_score * 0.30)
        if score >= 85:
            band = "excellent"
        elif score >= 70:
            band = "stable"
        elif score >= 55:
            band = "watch"
        else:
            band = "critical"
        score_bands[band] += 1
        cards.append(
            {
                "id": agent.get("id"),
                "title": agent.get("title") or agent.get("id"),
                "status": agent.get("status"),
                "score": score,
                "band": band,
                "activeTasks": active,
                "blockedTasks": blocked,
                "completedTasks7d": completed,
                "completionRate": completion_rate,
                "blockRate": block_rate,
                "avgResponseSeconds": avg_latency_seconds,
                "handoffs24h": int(agent.get("handoffs24h") or 0),
                "focus": agent.get("focus", ""),
                "lastSeenAgo": agent.get("lastSeenAgo", ""),
            }
        )
    cards.sort(key=lambda item: (-item["score"], item["blockedTasks"], item["title"]))
    summary = {
        "averageScore": round(sum(item["score"] for item in cards) / len(cards)) if cards else 0,
        "excellent": score_bands["excellent"],
        "stable": score_bands["stable"],
        "watch": score_bands["watch"],
        "critical": score_bands["critical"],
    }
    return {"summary": summary, "agents": cards}


def build_operational_reports(task_index, relays, events, management_runs, health_data, now):
    daily = []
    for offset in range(6, -1, -1):
        day_start = (now - timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        completed = 0
        blocked = 0
        signals = 0
        for task in task_index:
            updated_dt = parse_iso(task.get("updatedAt"))
            if not updated_dt or not (day_start <= updated_dt < day_end):
                continue
            state = str(task.get("state", "")).lower()
            if state in TERMINAL_STATES:
                completed += 1
            if task.get("blocked"):
                blocked += 1
        for event in events:
            event_dt = parse_iso(event.get("at"))
            if event_dt and day_start <= event_dt < day_end:
                signals += 1
        daily.append(
            {
                "date": day_start.strftime("%m-%d"),
                "completed": completed,
                "blocked": blocked,
                "signals": signals,
            }
        )

    bottlenecks = []
    for agent in (health_data.get("agents") or [])[:6]:
        if agent.get("blockedTasks") or agent.get("band") in {"watch", "critical"}:
            bottlenecks.append(
                {
                    "title": agent["title"],
                    "detail": f"阻塞 {agent['blockedTasks']} · 完成率 {agent['completionRate']}%",
                    "type": "agent",
                }
            )
    stage_counter = Counter(run.get("stageKey", "unknown") for run in management_runs if run.get("status") == "blocked")
    for stage_key, count in stage_counter.most_common(3):
        bottlenecks.append(
            {
                "title": f"{stage_key} 阶段阻塞",
                "detail": f"{count} 条管理 Run 目前卡在这里",
                "type": "stage",
            }
        )
    relay_leaders = [
        {
            "route": f"{item.get('from')} -> {item.get('to')}",
            "count": item.get("count", 0),
            "lastAgo": item.get("lastAgo", ""),
        }
        for item in (relays or [])[:5]
    ]
    return {
        "daily": daily,
        "weekly": {
            "completed": sum(item["completed"] for item in daily),
            "blockedTouches": sum(item["blocked"] for item in daily),
            "signals": sum(item["signals"] for item in daily),
            "relayCount": sum(item.get("count", 0) for item in relays),
        },
        "bottlenecks": bottlenecks[:6],
        "relayLeaders": relay_leaders,
    }


def summarize_notification_target(channel):
    channel_type = str((channel or {}).get("type") or "").strip().lower()
    target = str((channel or {}).get("target") or "").strip()
    if channel_type == "telegram":
        return target or "Telegram chat"
    if channel_type == "feishu":
        return target or "Feishu webhook"
    return target or "Webhook"


def recommended_management_rules():
    return [
        {
            "name": "阻塞超过 30 分钟自动升级",
            "description": "当任务阻塞超过 30 分钟时，自动生成运营告警，提醒负责人介入。",
            "triggerType": "blocked_task_timeout",
            "thresholdMinutes": 30,
            "cooldownMinutes": 90,
            "severity": "warning",
            "matchText": "",
            "status": "active",
            "channelIds": [],
        },
        {
            "name": "S 级任务完成自动通知",
            "description": "关键任务完成后，自动向运营群同步结果。",
            "triggerType": "critical_task_done",
            "thresholdMinutes": 0,
            "cooldownMinutes": 240,
            "severity": "critical",
            "matchText": "S级",
            "status": "active",
            "channelIds": [],
        },
        {
            "name": "Agent 离线超过 20 分钟提醒",
            "description": "当核心 Agent 长时间没有新信号时，自动发出巡检提醒。",
            "triggerType": "agent_offline",
            "thresholdMinutes": 20,
            "cooldownMinutes": 60,
            "severity": "warning",
            "matchText": "",
            "status": "active",
            "channelIds": [],
        },
    ]


def bootstrap_management_rules(openclaw_dir):
    existing = store_list_automation_rules(openclaw_dir)
    existing_names = {item.get("name", "") for item in existing}
    created = []
    for payload in recommended_management_rules():
        if payload["name"] in existing_names:
            continue
        created.append(store_save_automation_rule(openclaw_dir, payload))
    return {"created": created, "total": len(created)}


def render_management_weekly_report(openclaw_dir, management, theme, generated_at):
    report = management.get("reports", {}) if isinstance(management, dict) else {}
    health = management.get("agentHealth", {}) if isinstance(management, dict) else {}
    automation = management.get("automation", {}) if isinstance(management, dict) else {}
    weekly = report.get("weekly", {}) if isinstance(report, dict) else {}
    lines = [
        "# Mission Control Weekly Ops Report",
        "",
        f"- Generated At: {generated_at}",
        f"- Theme: {theme.get('displayName', theme.get('name', 'unknown')) if isinstance(theme, dict) else 'unknown'}",
        "",
        "## Weekly Summary",
        "",
        f"- Completed Tasks: {weekly.get('completed', 0)}",
        f"- Blocked Touches: {weekly.get('blockedTouches', 0)}",
        f"- Activity Signals: {weekly.get('signals', 0)}",
        f"- Relay Count: {weekly.get('relayCount', 0)}",
        f"- Average Agent Health: {(health.get('summary') or {}).get('averageScore', 0)} / 100",
        f"- Active Rules: {(automation.get('summary') or {}).get('activeRules', 0)}",
        f"- Open Alerts: {(automation.get('summary') or {}).get('openAlerts', 0)}",
        "",
        "## Top Bottlenecks",
        "",
    ]
    bottlenecks = report.get("bottlenecks", []) if isinstance(report, dict) else []
    if bottlenecks:
        for item in bottlenecks:
            lines.append(f"- {item.get('title', 'Unknown')}: {item.get('detail', '')}")
    else:
        lines.append("- No major bottlenecks were detected this week.")
    lines.extend(["", "## Relay Leaders", ""])
    relay_leaders = report.get("relayLeaders", []) if isinstance(report, dict) else []
    if relay_leaders:
        for item in relay_leaders:
            lines.append(f"- {item.get('route', 'Unknown')}: {item.get('count', 0)} handoffs, last {item.get('lastAgo', 'unknown')}")
    else:
        lines.append("- No standout relay routes this week.")
    lines.extend(["", "## Agent Health", ""])
    for agent in (health.get("agents", []) if isinstance(health, dict) else [])[:8]:
        lines.append(
            f"- {agent.get('title', 'Agent')}: score {agent.get('score', 0)}, completion {agent.get('completionRate', 0)}%, blocked {agent.get('blockedTasks', 0)}, avg response {agent.get('avgResponseSeconds', 0)}s"
        )
    return "\n".join(lines).strip() + "\n"


def export_management_weekly_report(openclaw_dir):
    data = build_dashboard_data(openclaw_dir)
    output_path = dashboard_dir(openclaw_dir) / "weekly-ops-report.md"
    output_path.write_text(
        render_management_weekly_report(openclaw_dir, data.get("management", {}), data.get("theme", {}), data.get("generatedAt", now_iso())),
        encoding="utf-8",
    )
    return {"path": str(output_path), "generatedAt": data.get("generatedAt", now_iso())}


def default_orchestration_workflow(agents, router_agent_id):
    preferred_order = [router_agent_id] + [agent.get("id") for agent in agents if agent.get("id") != router_agent_id]
    picked = [item for item in preferred_order if item][:4]
    lane_defs = [
        {"id": "intake", "title": "Intake", "subtitle": "需求进入与分拣"},
        {"id": "build", "title": "Engineering", "subtitle": "方案与执行"},
        {"id": "quality", "title": "Quality", "subtitle": "审议与验收"},
        {"id": "ops", "title": "Ops", "subtitle": "发布与运营收口"},
    ]
    nodes = []
    for index, lane in enumerate(lane_defs):
        agent_id = picked[index] if index < len(picked) else (picked[-1] if picked else "")
        nodes.append(
            {
                "id": f"node-{lane['id']}",
                "laneId": lane["id"],
                "title": lane["title"],
                "agentId": agent_id,
                "handoffNote": "在产品中可视化调整此阶段的负责 Agent 与交接语义。",
            }
        )
    return {
        "id": "starter-workflow",
        "name": "Starter Delivery Flow",
        "description": "默认的工程 -> 质量 -> 运维闭环，可作为编排 IDE 的起点。",
        "status": "draft",
        "lanes": lane_defs,
        "nodes": nodes,
        "meta": {"starter": True},
    }


def summarize_context_packet(entry):
    detail = str(entry.get("detail") or "").strip()
    if entry.get("kind") == "handoff":
        risk = "high" if not detail else ("watch" if len(detail) < 12 else "good")
        summary = detail or "这次 handoff 没有写交接说明。"
    else:
        risk = "watch" if not detail else ("good" if len(detail) >= 18 else "watch")
        summary = detail or "当前进展没有附带明确上下文。"
    return {"summary": summary, "risk": risk}


def build_orchestration_replay(task):
    replay = sorted(
        [item for item in (task.get("replay") or []) if isinstance(item, dict)],
        key=lambda item: parse_iso(item.get("at")) or datetime.fromtimestamp(0, tz=timezone.utc),
    )
    if not replay:
        return {
            "taskId": task.get("id", ""),
            "title": task.get("title", ""),
            "entries": [],
            "durationMinutes": 0,
            "initiator": task.get("route", [task.get("currentAgentLabel", "")])[0] if task.get("route") else task.get("currentAgentLabel", ""),
            "owner": task.get("currentAgentLabel", ""),
            "contextLossCount": 0,
        }
    first_dt = parse_iso(replay[0].get("at"))
    last_dt = parse_iso(replay[-1].get("at"))
    entries = []
    context_loss_count = 0
    for index, entry in enumerate(replay):
        next_dt = parse_iso(replay[index + 1].get("at")) if index + 1 < len(replay) else None
        current_dt = parse_iso(entry.get("at"))
        packet = summarize_context_packet(entry)
        if packet["risk"] != "good":
            context_loss_count += 1
        entries.append(
            {
                **entry,
                "durationToNextMinutes": round(max((next_dt - current_dt).total_seconds(), 0) / 60, 1) if current_dt and next_dt else 0,
                "contextPacket": packet,
            }
        )
    return {
        "taskId": task.get("id", ""),
        "title": task.get("title", ""),
        "entries": entries,
        "durationMinutes": round(max((last_dt - first_dt).total_seconds(), 0) / 60, 1) if first_dt and last_dt else 0,
        "initiator": (replay[0].get("actorLabel") or task.get("route", [""])[0] or task.get("currentAgentLabel", "")).strip(),
        "owner": task.get("currentAgentLabel", ""),
        "contextLossCount": context_loss_count,
    }


def build_orchestration_data(openclaw_dir, agents, task_index, router_agent_id, now):
    workflows = store_list_orchestration_workflows(openclaw_dir)
    routing_policies = store_list_routing_policies(openclaw_dir)
    if not workflows:
        workflows = [default_orchestration_workflow(agents, router_agent_id)]
    replays = []
    for task in task_index[:24]:
        if not task.get("id"):
            continue
        replay = build_orchestration_replay(task)
        replay.update(
            {
                "state": task.get("state", ""),
                "updatedAgo": task.get("updatedAgo", ""),
                "route": task.get("route", []),
                "blocked": bool(task.get("blocked")),
            }
        )
        replays.append(replay)
    replays.sort(key=lambda item: item.get("durationMinutes", 0), reverse=True)

    strategy_summary = Counter(policy.get("strategyType", "unknown") for policy in routing_policies)
    context_hotspots = sorted(
        [
            {
                "taskId": item.get("taskId", ""),
                "title": item.get("title", ""),
                "contextLossCount": item.get("contextLossCount", 0),
                "owner": item.get("owner", ""),
                "durationMinutes": item.get("durationMinutes", 0),
            }
            for item in replays
            if item.get("contextLossCount", 0) > 0
        ],
        key=lambda item: (-item["contextLossCount"], -item["durationMinutes"]),
    )[:8]
    return {
        "summary": {
            "workflowCount": len(workflows),
            "activePolicies": sum(1 for item in routing_policies if item.get("status") == "active"),
            "replayCount": len(replays),
            "contextLossHotspots": len(context_hotspots),
            "strategyBreakdown": dict(strategy_summary),
        },
        "workflows": workflows,
        "routingPolicies": routing_policies,
        "replays": replays[:18],
        "contextHotspots": context_hotspots,
        "commands": [
            {
                "label": "路由 Agent 现状",
                "command": f'OPENCLAW_STATE_DIR="{openclaw_dir}" openclaw agent --agent {router_agent_id} --message "summarize routing policy" --json',
                "description": "直接向当前路由 Agent 询问现有调度逻辑。",
            }
        ],
    }


def send_notification_message(channel, alert):
    channel_type = str(channel.get("type") or "").strip().lower()
    target = str(channel.get("target") or "").strip()
    secret = str(channel.get("secret") or "").strip()
    title = str(alert.get("title") or "Mission Control Alert").strip()
    detail = str(alert.get("detail") or "").strip()
    message = f"{title}\n{detail}".strip()

    if target.startswith("fixture://"):
        return {"ok": True, "detail": f"fixture delivered to {target}"}

    if channel_type == "telegram":
        if not secret or not target:
            raise RuntimeError("Telegram 通知需要 bot token 和 chat id。")
        request = Request(
            f"https://api.telegram.org/bot{secret}/sendMessage",
            data=json.dumps({"chat_id": target, "text": message}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    elif channel_type == "feishu":
        if not target:
            raise RuntimeError("飞书通知需要 webhook 地址。")
        request = Request(
            target,
            data=json.dumps({"msg_type": "text", "content": {"text": message}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    elif channel_type == "webhook":
        if not target:
            raise RuntimeError("Webhook 通知需要 URL。")
        request = Request(
            target,
            data=json.dumps({"title": title, "text": detail, "alert": alert}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    else:
        raise RuntimeError(f"不支持的通知类型: {channel_type}")

    try:
        with urlopen(request, timeout=8) as response:
            body = response.read().decode("utf-8", "replace")
            return {"ok": 200 <= response.status < 300, "detail": body[:320] or f"HTTP {response.status}"}
    except HTTPError as error:
        raise RuntimeError(f"通知推送失败: HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"通知推送失败: {error.reason}") from error


def evaluate_automation_rules(openclaw_dir, task_index, agents, management_runs, now):
    rules = store_list_automation_rules(openclaw_dir)
    channels = {item["id"]: item for item in store_list_notification_channels(openclaw_dir)}
    existing_deliveries = store_list_notification_deliveries(openclaw_dir, limit=240)
    delivery_map = {(item.get("alertId"), item.get("channelId")): item for item in existing_deliveries}
    rule_map = {item["id"]: item for item in rules}
    active_keys_by_rule = defaultdict(set)
    triggered = []

    for rule in rules:
        if rule.get("status") != "active":
            continue
        trigger_type = rule.get("triggerType")
        threshold_minutes = int(rule.get("thresholdMinutes") or 0)
        match_text = str(rule.get("matchText") or "").strip().lower()
        if trigger_type == "blocked_task_timeout":
            for task in task_index:
                updated_dt = parse_iso(task.get("updatedAt"))
                if not task.get("blocked") or not updated_dt:
                    continue
                age_minutes = int((now - updated_dt).total_seconds() // 60)
                if age_minutes < threshold_minutes:
                    continue
                active_keys_by_rule[rule["id"]].add(task["id"])
                alert = store_upsert_automation_alert(
                    openclaw_dir,
                    {
                        "ruleId": rule["id"],
                        "eventKey": task["id"],
                        "title": f"任务 {task['id']} 已阻塞 {age_minutes} 分钟",
                        "detail": task.get("title") or "需要介入处理的阻塞任务。",
                        "severity": rule.get("severity", "warning"),
                        "status": "open",
                        "sourceType": "task",
                        "sourceId": task["id"],
                        "meta": {"ageMinutes": age_minutes, "triggerType": trigger_type},
                    },
                )
                triggered.append(alert)
        elif trigger_type == "critical_task_done":
            for task in task_index:
                updated_dt = parse_iso(task.get("updatedAt"))
                if str(task.get("state", "")).lower() not in TERMINAL_STATES or not updated_dt:
                    continue
                if updated_dt < now - timedelta(days=1):
                    continue
                haystack = f"{task.get('id', '')} {task.get('title', '')}".lower()
                if match_text and match_text not in haystack:
                    continue
                active_keys_by_rule[rule["id"]].add(task["id"])
                alert = store_upsert_automation_alert(
                    openclaw_dir,
                    {
                        "ruleId": rule["id"],
                        "eventKey": task["id"],
                        "title": f"关键任务 {task['id']} 已完成",
                        "detail": task.get("title") or "关键任务完成，建议同步通知。",
                        "severity": rule.get("severity", "critical"),
                        "status": "open",
                        "sourceType": "task",
                        "sourceId": task["id"],
                        "meta": {"triggerType": trigger_type},
                    },
                )
                triggered.append(alert)
        elif trigger_type == "agent_offline":
            for agent in agents:
                if agent.get("status") not in {"idle", "blocked"}:
                    continue
                if not agent.get("lastSeenAt"):
                    continue
                last_seen = parse_iso(agent.get("lastSeenAt"))
                if not last_seen:
                    continue
                age_minutes = int((now - last_seen).total_seconds() // 60)
                if age_minutes < threshold_minutes:
                    continue
                active_keys_by_rule[rule["id"]].add(agent["id"])
                alert = store_upsert_automation_alert(
                    openclaw_dir,
                    {
                        "ruleId": rule["id"],
                        "eventKey": agent["id"],
                        "title": f"Agent {agent['title']} 失去信号 {age_minutes} 分钟",
                        "detail": agent.get("focus") or "最近没有新的工作信号，请确认运行状态。",
                        "severity": rule.get("severity", "warning"),
                        "status": "open",
                        "sourceType": "agent",
                        "sourceId": agent["id"],
                        "meta": {"ageMinutes": age_minutes, "triggerType": trigger_type},
                    },
                )
                triggered.append(alert)

    for rule in rules:
        store_resolve_automation_alerts(openclaw_dir, rule.get("id"), active_keys_by_rule.get(rule.get("id"), set()))

    alerts = store_list_automation_alerts(openclaw_dir, limit=80)
    deliveries = store_list_notification_deliveries(openclaw_dir, limit=200)
    delivery_by_alert = defaultdict(list)
    for delivery in deliveries:
        delivery_by_alert[delivery.get("alertId")].append(delivery)

    for alert in alerts:
        rule = rule_map.get(alert.get("ruleId"))
        if not rule or alert.get("status") == "resolved":
            continue
        channel_ids = [item for item in rule.get("channelIds", []) if channels.get(item, {}).get("status") == "active"]
        any_success = False
        for channel_id in channel_ids:
            pair = (alert.get("id"), channel_id)
            prior_delivery = delivery_map.get(pair)
            cooldown_minutes = int(rule.get("cooldownMinutes") or 0)
            if prior_delivery:
                delivered_at = parse_iso(prior_delivery.get("deliveredAt"))
                within_cooldown = delivered_at and cooldown_minutes > 0 and now - delivered_at < timedelta(minutes=cooldown_minutes)
                if prior_delivery.get("outcome") == "success" and within_cooldown:
                    any_success = True
                    continue
            channel = channels.get(channel_id)
            if not channel:
                continue
            try:
                result = send_notification_message(channel, alert)
                outcome = "success" if result.get("ok") else "error"
                detail = result.get("detail", "")
            except Exception as error:
                outcome = "error"
                detail = str(error)
            delivery = store_save_notification_delivery(
                openclaw_dir,
                alert["id"],
                channel_id,
                outcome,
                detail=detail,
                meta={"channelType": channel.get("type", "")},
            )
            delivery_by_alert[alert.get("id")].append(delivery)
            delivery_map[pair] = delivery
            if outcome == "success":
                any_success = True
        if any_success and alert.get("status") != "notified":
            store_upsert_automation_alert(
                openclaw_dir,
                {
                    "id": alert["id"],
                    "ruleId": alert["ruleId"],
                    "eventKey": alert["eventKey"],
                    "title": alert["title"],
                    "detail": alert["detail"],
                    "severity": alert["severity"],
                    "status": "notified",
                    "sourceType": alert.get("sourceType", ""),
                    "sourceId": alert.get("sourceId", ""),
                    "triggeredAt": alert.get("triggeredAt", now_iso()),
                    "meta": alert.get("meta", {}),
                },
            )

    refreshed_alerts = store_list_automation_alerts(openclaw_dir, limit=80)
    refreshed_deliveries = store_list_notification_deliveries(openclaw_dir, limit=200)
    recent = []
    for alert in refreshed_alerts[:12]:
        deliveries_for_alert = [item for item in refreshed_deliveries if item.get("alertId") == alert.get("id")]
        recent.append(
            {
                **alert,
                "ruleName": (rule_map.get(alert.get("ruleId")) or {}).get("name", ""),
                "deliveries": [
                    {
                        **item,
                        "channelName": (channels.get(item.get("channelId")) or {}).get("name", item.get("channelId", "")),
                    }
                    for item in deliveries_for_alert
                ],
            }
        )
    return {
        "rules": rules,
        "channels": list(channels.values()),
        "alerts": recent,
        "summary": {
            "activeRules": sum(1 for item in rules if item.get("status") == "active"),
            "openAlerts": sum(1 for item in refreshed_alerts if item.get("status") in {"open", "error"}),
            "notifiedAlerts": sum(1 for item in refreshed_alerts if item.get("status") == "notified"),
            "activeChannels": sum(1 for item in channels.values() if item.get("status") == "active"),
        },
    }


def build_management_data(openclaw_dir, task_index, conversation_data, deliverables, agents, events, relays, now):
    task_map = {item.get("id"): item for item in task_index if item.get("id")}
    deliverable_map = {item.get("id"): item for item in deliverables if item.get("id")}
    session_map = {
        item.get("key"): item
        for item in (conversation_data.get("sessions", []) if isinstance(conversation_data, dict) else [])
        if item.get("key")
    }
    runs = []
    stage_counter = Counter()
    status_counter = Counter()
    risk_counter = Counter()
    for run in store_list_management_runs(openclaw_dir, limit=48):
        current_stage = next(
            (stage for stage in run.get("stages", []) if stage.get("key") == run.get("stageKey")),
            {},
        )
        stage_counter[run.get("stageKey", "unknown")] += 1
        status_counter[run.get("status", "active")] += 1
        risk_counter[run.get("riskLevel", "medium")] += 1
        runs.append(
            {
                **run,
                "updatedAgo": format_age(parse_iso(run.get("updatedAt")), now),
                "createdAgo": format_age(parse_iso(run.get("createdAt")), now),
                "stageLabel": current_stage.get("title") or run.get("stageKey", ""),
                "stageStatus": current_stage.get("status") or ("done" if run.get("status") == "complete" else run.get("status")),
                "linkedTask": task_map.get(run.get("linkedTaskId")),
                "linkedSession": session_map.get(run.get("linkedSessionKey")),
                "deliverable": deliverable_map.get(run.get("linkedTaskId")),
            }
        )
    health_data = cached_payload(
        ("management-health", str(openclaw_dir)),
        20,
        lambda: compute_agent_health_data(openclaw_dir, agents, task_index, deliverables, now),
    )
    reports = cached_payload(
        ("management-reports", str(openclaw_dir)),
        20,
        lambda: build_operational_reports(task_index, relays, events, runs, health_data, now),
    )
    automation = cached_payload(
        ("management-automation", str(openclaw_dir)),
        15,
        lambda: evaluate_automation_rules(openclaw_dir, task_index, agents, runs, now),
    )
    return {
        "summary": {
            "total": len(runs),
            "active": sum(1 for item in runs if item.get("status") == "active"),
            "blocked": sum(1 for item in runs if item.get("status") == "blocked"),
            "readyForRelease": sum(1 for item in runs if item.get("stageKey") == "release" and item.get("status") != "complete"),
            "completed": sum(1 for item in runs if item.get("status") == "complete"),
            "statusBreakdown": dict(status_counter),
            "stageBreakdown": dict(stage_counter),
            "riskBreakdown": dict(risk_counter),
        },
        "runs": runs,
        "agentHealth": health_data,
        "reports": reports,
        "automation": automation,
    }


def perform_skill_scaffold(
    openclaw_dir,
    slug,
    title,
    description,
    trigger_phrase,
    category,
    include_scripts=False,
    include_references=True,
    include_assets=False,
    mcp_server="",
):
    project_dir, cli_path = skills_cli_path(openclaw_dir)
    if not project_dir or not cli_path:
        raise RuntimeError("当前安装没有关联 skill 工具脚本，无法创建新技能。")
    args = [
        "scaffold",
        "--project-dir",
        str(project_dir),
        "--slug",
        slug,
        "--title",
        title,
        "--description",
        description,
        "--trigger-phrase",
        trigger_phrase,
        "--category",
        category,
        "--version",
        "1.0.0",
    ]
    if include_scripts:
        args.append("--include-scripts")
    if include_references:
        args.append("--include-references")
    if include_assets:
        args.append("--include-assets")
    if mcp_server:
        args.extend(["--mcp-server", mcp_server])
    result, output = run_python_script(cli_path, args, cwd=project_dir)
    if result.returncode != 0:
        raise RuntimeError(output or f"创建技能失败: {slug}")
    try:
        return json.loads(result.stdout or output or "{}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"技能脚手架输出异常: {error}") from error


def perform_skill_package(openclaw_dir, slug):
    project_dir, cli_path = skills_cli_path(openclaw_dir)
    if not project_dir or not cli_path:
        raise RuntimeError("当前安装没有关联 skill 工具脚本，无法打包技能。")
    result, output = run_python_script(
        cli_path,
        ["package", "--project-dir", str(project_dir), "--skill", slug],
        cwd=project_dir,
    )
    if result.returncode != 0:
        raise RuntimeError(output or f"打包技能失败: {slug}")
    try:
        return json.loads(result.stdout or output or "{}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"技能打包输出异常: {error}") from error


def perform_skill_publish(openclaw_dir, slug):
    project_dir, cli_path = skills_cli_path(openclaw_dir)
    if not project_dir or not cli_path:
        raise RuntimeError("当前安装没有关联 skill 工具脚本，无法发布技能到 OpenClaw。")
    result, output = run_python_script(
        cli_path,
        [
            "publish",
            "--project-dir",
            str(project_dir),
            "--openclaw-dir",
            str(Path(openclaw_dir).expanduser().resolve()),
            "--skill",
            slug,
        ],
        cwd=project_dir,
    )
    if result.returncode != 0:
        raise RuntimeError(output or f"发布技能失败: {slug}")
    try:
        return json.loads(result.stdout or output or "{}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"技能发布输出异常: {error}") from error


def parse_request_cookies(cookie_header):
    cookie = SimpleCookie()
    if cookie_header:
        cookie.load(cookie_header)
    return {name: morsel.value for name, morsel in cookie.items()}


def safe_next_path(path):
    if not path or not path.startswith("/"):
        return "/"
    if path.startswith("//") or path.startswith("/login"):
        return "/"
    return path


def resolve_frontend_dist(openclaw_dir, config=None, explicit_path=""):
    explicit = str(explicit_path or "").strip()
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        return candidate if candidate.exists() else None
    project_dir = resolve_project_dir(openclaw_dir, config=config)
    if not project_dir:
        return None
    candidate = (Path(project_dir) / "frontend" / "dist").resolve()
    return candidate if candidate.exists() else None


def parse_cors_origins(value):
    raw = str(value or "").strip()
    if not raw:
        return set(DEFAULT_FRONTEND_ORIGINS)
    return {item.strip() for item in raw.split(",") if item.strip()}


def guess_content_type(path):
    guessed, _encoding = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def render_login_html(openclaw_dir, next_path="/", error_message=""):
    config = load_config(openclaw_dir)
    metadata = load_project_metadata(openclaw_dir, config=config)
    theme_name = metadata.get("theme", "imperial")
    theme_style = THEME_STYLES.get(theme_name, THEME_STYLES["imperial"])
    theme_meta = THEME_CATALOG.get(theme_name, THEME_CATALOG["imperial"])
    router_agent_id = get_router_agent_id(config)
    kanban_cfg = load_kanban_config(openclaw_dir, router_agent_id)
    users = load_product_users(openclaw_dir)
    team_status = f"{len(users)} 个团队席位" if users else "尚未创建团队席位"
    auth_mode = "团队账号 + Token Fallback" if users else "Bootstrap 模式"
    bootstrap_help = (
        "当前已经启用团队账号。日常使用建议改走账号登录，Owner Token 仅保留给初始化和紧急接管。"
        if users
        else "当前还没有团队账号。请先使用 Owner Token 进入，在后台创建 owner / operator / viewer 席位。"
    )
    return LOGIN_TEMPLATE.format(
        bg=theme_style["bg"],
        bg2=theme_style["bg2"],
        ink=theme_style["ink"],
        muted=theme_style["muted"],
        accent=theme_style["accent"],
        accentStrong=theme_style["accentStrong"],
        accentSoft=theme_style["accentSoft"],
        line=theme_style["line"],
        ok=theme_style["ok"],
        danger=theme_style["danger"],
        theme_name=theme_meta["displayName"],
        owner_title=kanban_cfg.get("owner_title", "Mission Control"),
        theme_summary=theme_meta["summary"],
        next_path=safe_next_path(next_path),
        openclaw_dir=openclaw_dir,
        team_status=team_status,
        auth_mode=auth_mode,
        bootstrap_help=bootstrap_help,
        error_message=error_message or "",
        error_hidden="hidden" if not error_message else "",
    )


def find_product_user(openclaw_dir, username):
    normalized = normalize_username(username)
    return next((user for user in load_product_users(openclaw_dir) if user["username"] == normalized), None)


def session_for_client(session):
    if not session:
        return {"displayName": "Guest", "role": "viewer", "roleLabel": role_meta("viewer")["label"], "kind": "guest"}
    role = session.get("role", "viewer")
    return {
        "displayName": session.get("displayName") or session.get("username") or "User",
        "username": session.get("username", ""),
        "role": role,
        "roleLabel": role_meta(role)["label"],
        "kind": session.get("kind", "user"),
    }


def actor_from_session(session):
    client = session_for_client(session)
    return {
        "displayName": client["displayName"],
        "username": client.get("username", ""),
        "role": client["role"],
        "kind": client.get("kind", "user"),
    }


class CollaborationDashboardHandler(BaseHTTPRequestHandler):
    server_version = f"SanshengDashboard/{PRODUCT_VERSION}"
    SPA_ROUTES = {
        "/",
        "/login",
        "/overview",
        "/management",
        "/orchestration",
        "/context",
        "/agents",
        "/tasks",
        "/conversations",
        "/activity",
        "/themes",
        "/skills",
        "/openclaw",
        "/admin",
        "/collaboration-dashboard.html",
    }

    def log_message(self, format, *args):
        return

    def _cors_headers(self):
        origin = (self.headers.get("Origin") or "").strip()
        allowed = getattr(self.server, "cors_origins", set()) or set()
        if not origin or origin not in allowed:
            return []
        return [
            ("Access-Control-Allow-Origin", origin),
            ("Access-Control-Allow-Credentials", "true"),
            ("Vary", "Origin"),
        ]

    def _send_bytes(self, body, content_type, status=200, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        headers = list(self._cors_headers())
        headers.extend(extra_headers or [])
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def _send_json(self, payload, status=200, extra_headers=None):
        body = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status=status, extra_headers=extra_headers)

    def _send_preflight(self):
        headers = self._cors_headers()
        if not headers:
            self._send_bytes(b"Origin not allowed", "text/plain; charset=utf-8", status=403)
            return
        self.send_response(204)
        for key, value in headers:
            self.send_header(key, value)
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()

    def _auth_mode(self):
        auth_token = getattr(self.server, "dashboard_auth_token", "")
        if not auth_token:
            return "open"
        return "accounts" if load_product_users(self.server.openclaw_dir) else "token"

    def _auth_payload(self):
        session = self._session()
        return {
            "ok": bool(session),
            "session": session_for_client(session),
            "permissions": self._permissions(),
            "authMode": self._auth_mode(),
            "actionToken": expected_action_value(getattr(self.server, "dashboard_auth_token", "")) if session else "",
            "productVersion": PRODUCT_VERSION,
        }

    def _frontend_dist(self):
        return getattr(self.server, "frontend_dist", None)

    def _serve_frontend_asset(self, path):
        dist_dir = self._frontend_dist()
        if not dist_dir:
            return False
        relative = path.lstrip("/")
        if not relative:
            return False
        candidate = (dist_dir / relative).resolve()
        if dist_dir not in candidate.parents or not candidate.is_file():
            return False
        self._send_bytes(candidate.read_bytes(), f"{guess_content_type(candidate)}; charset=utf-8" if candidate.suffix in {'.html', '.js', '.mjs', '.css', '.json', '.svg'} else guess_content_type(candidate))
        return True

    def _serve_frontend_index(self):
        dist_dir = self._frontend_dist()
        if not dist_dir:
            return False
        index_path = dist_dir / "index.html"
        if not index_path.exists():
            return False
        self._send_bytes(index_path.read_bytes(), "text/html; charset=utf-8")
        return True

    def _serve_legacy_dashboard(self):
        if not self._require_auth(api=False):
            return
        data, _paths = self._bundle()
        self._send_bytes(render_html(data).encode("utf-8"), "text/html; charset=utf-8")

    def _runtime_data(self, data):
        config = load_config(self.server.openclaw_dir)
        project_dir = resolve_project_dir(self.server.openclaw_dir, config)
        permissions = self._permissions()
        include_sensitive_admin = self._can("auditView") or self._can("adminWrite")
        data["admin"] = build_admin_data(
            self.server.openclaw_dir,
            config,
            now_utc(),
            include_sensitive=include_sensitive_admin,
        )
        runtime = {
            "productVersion": PRODUCT_VERSION,
            "actionsEnabled": permissions.get("taskWrite") or permissions.get("themeWrite") or permissions.get("adminWrite"),
            "themeSwitchAvailable": bool(project_dir and (project_dir / "bin" / "switch_theme.py").exists() and permissions.get("themeWrite")),
            "actionToken": expected_action_value(getattr(self.server, "dashboard_auth_token", "")),
            "currentUser": session_for_client(self._session()),
            "permissions": permissions,
            "authMode": "accounts" if data.get("admin", {}).get("hasUsers") else "token",
        }
        data["runtime"] = runtime
        return data

    def _bundle(self):
        data, paths = build_dashboard_bundle(self.server.openclaw_dir, self.server.output_dir)
        return self._runtime_data(data), paths

    def _refreshed_bundle(self):
        clear_cached_payloads()
        return self._bundle()

    def _path(self):
        return urlsplit(self.path).path

    def _query(self):
        return parse_qs(urlsplit(self.path).query)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else "{}"
        return json.loads(raw or "{}")

    def _next_path(self):
        return safe_next_path(self._query().get("next", ["/"])[0])

    def _session(self):
        cached = getattr(self, "_cached_session", None)
        if cached is not None:
            return cached
        auth_token = getattr(self.server, "dashboard_auth_token", "")
        if not auth_token:
            session = {
                "kind": "open",
                "username": "local-open",
                "displayName": "Local Access",
                "role": "owner",
                "issuedAt": now_iso(),
                "expiresAt": (now_utc() + timedelta(hours=12)).isoformat().replace("+00:00", "Z"),
            }
            self._cached_session = session
            return session
        cookies = parse_request_cookies(self.headers.get("Cookie", ""))
        current = cookies.get(SESSION_COOKIE_NAME, "")
        session = decode_session_cookie(auth_token, current)
        self._cached_session = session
        return session

    def _is_authenticated(self):
        return self._session() is not None

    def _permissions(self):
        session = self._session()
        role = session.get("role", "viewer") if session else "viewer"
        return permissions_for_role(role)

    def _can(self, permission_key):
        return bool(self._permissions().get(permission_key))

    def _api_key_value(self):
        auth_header = str(self.headers.get("Authorization", "")).strip()
        if auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1].strip()
        return str(self.headers.get("X-API-Key", "")).strip()

    def _api_key_record(self):
        cached = getattr(self, "_cached_api_key_record", None)
        if cached is not None:
            return cached
        raw_key = self._api_key_value()
        if not raw_key:
            self._cached_api_key_record = None
            return None
        record = store_resolve_tenant_api_key(self.server.openclaw_dir, raw_key)
        if record:
            store_touch_tenant_api_key(self.server.openclaw_dir, record.get("id", ""))
        self._cached_api_key_record = record
        return record

    def _current_actor(self):
        session = self._session()
        if session:
            return actor_from_session(session)
        api_key = self._api_key_record()
        if api_key:
            return {
                "displayName": api_key.get("name") or api_key.get("prefix", "Tenant API Key"),
                "username": api_key.get("tenantId", "tenant-api"),
                "role": "owner",
                "kind": "api_key",
            }
        return {"displayName": "anonymous", "username": "anonymous", "role": "viewer", "kind": "anonymous"}

    def _rest_auth_context(self, required_scope="", tenant_ref=""):
        api_key = self._api_key_record()
        tenant = find_tenant_record(self.server.openclaw_dir, tenant_ref) if tenant_ref else None
        if api_key:
            if required_scope and not api_scope_allows(api_key.get("scopes", []), required_scope):
                self._send_json({"ok": False, "error": "permission_denied", "message": "API Key 没有访问当前资源的 scope。"}, status=403)
                return None
            if tenant and api_key.get("tenantId") != tenant.get("id"):
                self._send_json({"ok": False, "error": "permission_denied", "message": "API Key 不能访问其他租户的数据。"}, status=403)
                return None
            if tenant_ref and not tenant:
                self._send_json({"ok": False, "error": "not_found", "message": "租户不存在。"}, status=404)
                return None
            return {"mode": "api_key", "apiKey": api_key, "tenant": tenant}
        if not self._is_authenticated():
            self._send_json({"ok": False, "error": "auth_required", "message": "请先登录或提供 API Key。"}, status=401)
            return None
        if not (self._can("adminWrite") or self._can("auditView")):
            self._send_json({"ok": False, "error": "permission_denied", "message": "当前账号没有租户平台访问权限。"}, status=403)
            return None
        if tenant_ref and not tenant:
            self._send_json({"ok": False, "error": "not_found", "message": "租户不存在。"}, status=404)
            return None
        return {"mode": "session", "tenant": tenant}

    def _tenant_openclaw_dir(self, tenant):
        tenant_dir = tenant_primary_openclaw_dir(self.server.openclaw_dir, tenant)
        if not tenant_dir:
            raise RuntimeError("租户还没有绑定可用的 OpenClaw 安装。")
        if not tenant_dir.exists():
            raise RuntimeError(f"租户安装目录不存在：{tenant_dir}")
        return tenant_dir

    def _login_cookie_header(self, session_data):
        auth_token = getattr(self.server, "dashboard_auth_token", "")
        return (
            "Set-Cookie",
            f"{SESSION_COOKIE_NAME}={encode_session_cookie(auth_token, session_data)}; Max-Age={SESSION_COOKIE_MAX_AGE}; Path=/; HttpOnly; SameSite=Lax",
        )

    def _clear_cookie_header(self):
        return (
            "Set-Cookie",
            f"{SESSION_COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax",
        )

    def _require_action_token(self, payload):
        expected = expected_action_value(getattr(self.server, "dashboard_auth_token", ""))
        if not expected:
            return True
        provided = str((payload or {}).get("actionToken", "")).strip()
        if provided and hmac.compare_digest(provided, expected):
            return True
        self._send_json({"ok": False, "error": "invalid_action_token", "message": "操作令牌已失效，请刷新页面后重试。"}, status=403)
        return False

    def _require_capability(self, permission_key, message, status=403):
        if self._can(permission_key):
            return True
        self._send_json({"ok": False, "error": "permission_denied", "message": message}, status=status)
        return False

    def _audit(self, action, outcome="success", detail="", meta=None):
        return append_audit_event(
            self.server.openclaw_dir,
            action,
            self._current_actor(),
            outcome=outcome,
            detail=detail,
            meta=meta,
        )

    def _send_redirect(self, location, extra_headers=None):
        headers = [("Location", location)]
        headers.extend(extra_headers or [])
        self.send_response(302)
        for key, value in headers:
            self.send_header(key, value)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()

    def _require_auth(self, api=False):
        if self._is_authenticated():
            return True
        if api:
            body = json.dumps(
                {"error": "auth_required", "login": f"/login?next={quote(self._path())}"},
                ensure_ascii=False,
            ).encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8", status=401)
        else:
            self._send_redirect(f"/login?next={quote(self._path())}")
        return False

    def _build_session_data(self, kind, username, display_name, role):
        return {
            "kind": kind,
            "username": username,
            "displayName": display_name,
            "role": role,
            "issuedAt": now_iso(),
            "expiresAt": (now_utc() + timedelta(hours=12)).isoformat().replace("+00:00", "Z"),
        }

    def _authenticate_password(self, username, password):
        username = normalize_username(username)
        password = str(password or "").strip()
        user = find_product_user(self.server.openclaw_dir, username)
        if user and user.get("status") == "active" and verify_password(password, user.get("passwordHash", "")):
            session_data = self._build_session_data(
                "user",
                user["username"],
                user.get("displayName") or user["username"],
                user.get("role", "viewer"),
            )
            update_product_user_login(self.server.openclaw_dir, username)
            append_audit_event(
                self.server.openclaw_dir,
                "login",
                actor_from_session(session_data),
                detail="团队账号登录成功。",
                meta={"mode": "password"},
            )
            return session_data, None
        append_audit_event(
            self.server.openclaw_dir,
            "login",
            {"displayName": username or "unknown", "username": username, "role": "viewer", "kind": "anonymous"},
            outcome="denied",
            detail="团队账号登录失败。",
            meta={"mode": "password"},
        )
        return None, "团队账号或密码不正确，请重新输入。"

    def _authenticate_token(self, submitted):
        auth_token = getattr(self.server, "dashboard_auth_token", "")
        submitted = str(submitted or "").strip()
        if auth_token and hmac.compare_digest(submitted, auth_token):
            session_data = self._build_session_data("token", "owner-token", "Owner Token", "owner")
            append_audit_event(
                self.server.openclaw_dir,
                "login",
                actor_from_session(session_data),
                detail="Owner Token 登录成功。",
                meta={"mode": "token"},
            )
            return session_data, None
        append_audit_event(
            self.server.openclaw_dir,
            "login",
            {"displayName": "Owner Token", "username": "owner-token", "role": "owner", "kind": "anonymous"},
            outcome="denied",
            detail="Owner Token 登录失败。",
            meta={"mode": "token"},
        )
        return None, "Owner Token 不正确，请重新输入。"

    def _handle_auth_session_get(self):
        payload = self._auth_payload()
        payload["authenticated"] = payload["ok"]
        self._send_json(payload)

    def _handle_auth_login_json(self):
        try:
            payload = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "invalid_json", "message": "请求体不是合法 JSON。"}, status=400)
            return
        mode = str(payload.get("mode", "password") or "password").strip()
        if mode == "password":
            session_data, error_message = self._authenticate_password(payload.get("username", ""), payload.get("password", ""))
        else:
            session_data, error_message = self._authenticate_token(payload.get("token", ""))
        if not session_data:
            self._send_json({"ok": False, "error": "invalid_credentials", "message": error_message, "authMode": self._auth_mode()}, status=401)
            return
        self._cached_session = session_data
        response = self._auth_payload()
        response["ok"] = True
        self._send_json(response, extra_headers=[self._login_cookie_header(session_data)])

    def _handle_auth_logout_json(self):
        session = self._session()
        if session:
            append_audit_event(
                self.server.openclaw_dir,
                "logout",
                actor_from_session(session),
                detail="用户已退出 Mission Control。",
            )
        self._cached_session = None
        self._send_json({"ok": True}, extra_headers=[self._clear_cookie_header()])

    def _handle_login_get(self):
        if self._frontend_dist():
            self._serve_frontend_index()
            return
        if self._is_authenticated():
            self._send_redirect(self._next_path())
            return
        body = render_login_html(self.server.openclaw_dir, next_path=self._next_path()).encode("utf-8")
        self._send_bytes(body, "text/html; charset=utf-8")

    def _handle_login_post(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        payload = self.rfile.read(length).decode("utf-8", "replace")
        form = parse_qs(payload)
        mode = (form.get("mode", ["password"])[0] or "password").strip()
        next_path = safe_next_path((form.get("next", ["/"])[0] or "/"))
        if mode == "password":
            session_data, error_message = self._authenticate_password(form.get("username", [""])[0], form.get("password", [""])[0])
            if session_data:
                self._send_redirect(next_path, extra_headers=[self._login_cookie_header(session_data)])
                return
            body = render_login_html(
                self.server.openclaw_dir,
                next_path=next_path,
                error_message=error_message,
            ).encode("utf-8")
            self._send_bytes(body, "text/html; charset=utf-8", status=401)
            return

        session_data, error_message = self._authenticate_token(form.get("token", [""])[0])
        if session_data:
            self._send_redirect(next_path, extra_headers=[self._login_cookie_header(session_data)])
            return
        body = render_login_html(
            self.server.openclaw_dir,
            next_path=next_path,
            error_message=error_message,
        ).encode("utf-8")
        self._send_bytes(body, "text/html; charset=utf-8", status=401)

    def _handle_logout_post(self):
        session = self._session()
        length = int(self.headers.get("Content-Length", "0") or "0")
        payload = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        form = parse_qs(payload)
        next_path = safe_next_path((form.get("next", ["/login"])[0] or "/login"))
        append_audit_event(
            self.server.openclaw_dir,
            "logout",
            actor_from_session(session),
            detail="用户已退出 Mission Control。",
        )
        self._cached_session = None
        self._send_redirect(next_path, extra_headers=[self._clear_cookie_header()])

    def _handle_rest_get(self, path):
        try:
            if path == "/api/v1/tenants":
                context = self._rest_auth_context(required_scope="tenant:read")
                if not context:
                    return True
                tenant_admin = build_tenant_admin_data(self.server.openclaw_dir, now_utc())
                if context.get("mode") == "api_key":
                    tenant = context.get("tenant") or find_tenant_record(self.server.openclaw_dir, context["apiKey"].get("tenantId", ""))
                    items = [item for item in tenant_admin["items"] if item.get("id") == (tenant or {}).get("id")]
                else:
                    items = tenant_admin["items"]
                self._send_json({"ok": True, "tenants": items, "summary": tenant_admin["summary"]})
                return True

            parts = [segment for segment in path.split("/") if segment]
            if len(parts) < 5 or parts[:3] != ["api", "v1", "tenants"]:
                return False
            tenant_ref = parts[3]
            resource = parts[4]
            scope_map = {
                "dashboard": "dashboard:read",
                "tasks": "tasks:read",
                "agents": "agents:read",
                "management": "tenant:read",
            }
            context = self._rest_auth_context(required_scope=scope_map.get(resource, "tenant:read"), tenant_ref=tenant_ref)
            if not context:
                return True
            tenant = context.get("tenant")
            tenant_dir = self._tenant_openclaw_dir(tenant)
            dashboard = build_dashboard_data(tenant_dir)
            tenant_payload = {
                "id": tenant.get("id"),
                "name": tenant.get("name"),
                "slug": tenant.get("slug"),
                "status": tenant.get("status"),
                "primaryOpenclawDir": str(tenant_dir),
            }
            if resource == "dashboard":
                self._send_json({"ok": True, "tenant": tenant_payload, "dashboard": dashboard})
                return True
            if resource == "tasks":
                self._send_json({"ok": True, "tenant": tenant_payload, "tasks": dashboard.get("taskIndex", [])})
                return True
            if resource == "agents":
                self._send_json({"ok": True, "tenant": tenant_payload, "agents": dashboard.get("agents", [])})
                return True
            if resource == "management":
                self._send_json({"ok": True, "tenant": tenant_payload, "management": dashboard.get("management", {})})
                return True
            self._send_json({"ok": False, "error": "not_found", "message": "未知 REST 资源。"}, status=404)
            return True
        except RuntimeError as error:
            self._send_json({"ok": False, "error": "rest_failed", "message": str(error)}, status=400)
            return True

    def _handle_rest_post(self, path):
        try:
            parts = [segment for segment in path.split("/") if segment]
            if len(parts) < 5 or parts[:3] != ["api", "v1", "tenants"]:
                return False
            tenant_ref = parts[3]
            resource = parts[4]
            try:
                payload = self._read_json_body()
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "invalid_json", "message": "请求体不是合法 JSON。"}, status=400)
                return True
            context = self._rest_auth_context(required_scope="tasks:write", tenant_ref=tenant_ref)
            if not context:
                return True
            tenant = context.get("tenant")
            tenant_dir = self._tenant_openclaw_dir(tenant)
            if resource == "tasks":
                title = str(payload.get("title", "")).strip()
                remark = str(payload.get("remark", "")).strip()
                if not title:
                    self._send_json({"ok": False, "error": "missing_title", "message": "任务标题不能为空。"}, status=400)
                    return True
                task_id = perform_task_create(tenant_dir, title, remark=remark)
                self._audit(
                    "tenant_task_create",
                    detail=f"通过开放 API 为租户 {tenant.get('name', tenant.get('id', ''))} 创建任务 {task_id}",
                    meta={"tenantId": tenant.get("id", ""), "taskId": task_id, "title": title},
                )
                self._send_json(
                    {
                        "ok": True,
                        "tenant": {"id": tenant.get("id"), "name": tenant.get("name"), "slug": tenant.get("slug")},
                        "taskId": task_id,
                        "message": f"任务 {task_id} 已进入租户协同链路。",
                    }
                )
                return True
            self._send_json({"ok": False, "error": "not_found", "message": "未知 REST 写入资源。"}, status=404)
            return True
        except RuntimeError as error:
            self._send_json({"ok": False, "error": "rest_failed", "message": str(error)}, status=400)
            return True

    def _handle_action_post(self, path):
        try:
            payload = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "invalid_json", "message": "请求体不是合法 JSON。"}, status=400)
            return

        if not self._require_action_token(payload):
            return

        try:
            if path == "/api/actions/task/create":
                if not self._require_capability("taskWrite", "当前账号没有创建或推进任务的权限。"):
                    return
                title = str(payload.get("title", "")).strip()
                remark = str(payload.get("remark", "")).strip()
                if not title:
                    raise RuntimeError("任务标题不能为空。")
                task_id = perform_task_create(self.server.openclaw_dir, title, remark=remark)
                self._audit("task_create", detail=f"创建任务 {task_id}", meta={"taskId": task_id, "title": title})
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"任务 {task_id} 已创建，已经进入当前协同链路。",
                        "taskId": task_id,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/task/progress":
                if not self._require_capability("taskWrite", "当前账号没有推进任务的权限。"):
                    return
                task_id = str(payload.get("taskId", "")).strip()
                message = str(payload.get("message", "")).strip()
                todos = str(payload.get("todos", "")).strip()
                mark_doing = bool(payload.get("markDoing"))
                if not task_id or not message:
                    raise RuntimeError("任务编号和进展内容都不能为空。")
                perform_task_progress(self.server.openclaw_dir, task_id, message, todos=todos, mark_doing=mark_doing)
                self._audit(
                    "task_progress",
                    detail=f"同步任务 {task_id} 的进展",
                    meta={"taskId": task_id, "markDoing": mark_doing},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"任务 {task_id} 的最新进展已经同步。",
                        "taskId": task_id,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/task/block":
                if not self._require_capability("taskWrite", "当前账号没有标记阻塞的权限。"):
                    return
                task_id = str(payload.get("taskId", "")).strip()
                reason = str(payload.get("reason", "")).strip()
                if not task_id or not reason:
                    raise RuntimeError("请提供任务编号和阻塞原因。")
                perform_task_block(self.server.openclaw_dir, task_id, reason)
                self._audit("task_block", detail=f"标记任务 {task_id} 阻塞", meta={"taskId": task_id})
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"任务 {task_id} 已标记为阻塞。",
                        "taskId": task_id,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/task/done":
                if not self._require_capability("taskWrite", "当前账号没有完成任务的权限。"):
                    return
                task_id = str(payload.get("taskId", "")).strip()
                summary = str(payload.get("summary", "")).strip()
                output_path = str(payload.get("output", "")).strip()
                if not task_id:
                    raise RuntimeError("请提供任务编号。")
                perform_task_done(self.server.openclaw_dir, task_id, output_path=output_path, summary=summary)
                self._audit("task_done", detail=f"完成任务 {task_id}", meta={"taskId": task_id, "output": output_path})
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"任务 {task_id} 已完成并归档到交付列表。",
                        "taskId": task_id,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/management/run/create":
                if not self._require_capability("taskWrite", "当前账号没有创建端到端管理 Run 的权限。"):
                    return
                title = str(payload.get("title", "")).strip()
                if not title:
                    raise RuntimeError("管理 Run 标题不能为空。")
                owner = str(payload.get("owner", "")).strip() or session_for_client(self._session()).get("displayName", "Mission Control")
                run = store_create_management_run(
                    self.server.openclaw_dir,
                    {
                        "title": title,
                        "goal": str(payload.get("goal", "")).strip(),
                        "owner": owner,
                        "linkedTaskId": str(payload.get("linkedTaskId", "")).strip(),
                        "linkedAgentId": str(payload.get("linkedAgentId", "")).strip(),
                        "linkedSessionKey": str(payload.get("linkedSessionKey", "")).strip(),
                        "releaseChannel": str(payload.get("releaseChannel", "")).strip() or "manual",
                        "riskLevel": str(payload.get("riskLevel", "")).strip() or "medium",
                    },
                )
                self._audit(
                    "management_run_create",
                    detail=f"创建端到端管理 Run {run['title']}",
                    meta={"runId": run["id"], "linkedTaskId": run.get("linkedTaskId", "")},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"端到端管理 Run {run['title']} 已建立。",
                        "run": run,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/management/run/update":
                if not self._require_capability("taskWrite", "当前账号没有推进端到端管理 Run 的权限。"):
                    return
                run_id = str(payload.get("runId", "")).strip()
                action = str(payload.get("action", "")).strip().lower()
                if not run_id or not action:
                    raise RuntimeError("请提供 Run 编号和动作。")
                run = store_update_management_run(
                    self.server.openclaw_dir,
                    run_id,
                    action,
                    note=str(payload.get("note", "")).strip(),
                    risk_level=str(payload.get("riskLevel", "")).strip(),
                    linked_task_id=str(payload.get("linkedTaskId", "")).strip(),
                )
                self._audit(
                    "management_run_update",
                    detail=f"更新端到端管理 Run {run_id}",
                    meta={"runId": run_id, "action": action, "stageKey": run.get("stageKey", "")},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"端到端管理 Run {run.get('title', run_id)} 已更新。",
                        "run": run,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/management/rule/save":
                if not self._require_capability("taskWrite", "当前账号没有配置自动化规则的权限。"):
                    return
                name = str(payload.get("name", "")).strip()
                trigger_type = str(payload.get("triggerType", "")).strip()
                if not name or not trigger_type:
                    raise RuntimeError("请填写规则名称和触发类型。")
                rule = store_save_automation_rule(
                    self.server.openclaw_dir,
                    {
                        "id": str(payload.get("id", "")).strip(),
                        "name": name,
                        "description": str(payload.get("description", "")).strip(),
                        "status": str(payload.get("status", "")).strip() or "active",
                        "triggerType": trigger_type,
                        "thresholdMinutes": int(payload.get("thresholdMinutes") or 0),
                        "cooldownMinutes": int(payload.get("cooldownMinutes") or 60),
                        "severity": str(payload.get("severity", "")).strip() or "warning",
                        "matchText": str(payload.get("matchText", "")).strip(),
                        "channelIds": payload.get("channelIds") if isinstance(payload.get("channelIds"), list) else [],
                    },
                )
                self._audit(
                    "management_rule_save",
                    detail=f"保存自动化规则 {rule['name']}",
                    meta={"ruleId": rule["id"], "triggerType": rule["triggerType"]},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"自动化规则 {rule['name']} 已保存。",
                        "rule": rule,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/management/channel/save":
                if not self._require_capability("adminWrite", "当前账号没有配置通知渠道的权限。"):
                    return
                name = str(payload.get("name", "")).strip()
                channel_type = str(payload.get("type", "")).strip()
                if not name or not channel_type:
                    raise RuntimeError("请填写通知渠道名称和类型。")
                channel = store_save_notification_channel(
                    self.server.openclaw_dir,
                    {
                        "id": str(payload.get("id", "")).strip(),
                        "name": name,
                        "type": channel_type,
                        "status": str(payload.get("status", "")).strip() or "active",
                        "target": str(payload.get("target", "")).strip(),
                        "secret": str(payload.get("secret", "")).strip(),
                    },
                )
                self._audit(
                    "management_channel_save",
                    detail=f"保存通知渠道 {channel['name']}",
                    meta={"channelId": channel["id"], "type": channel["type"]},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"通知渠道 {channel['name']} 已保存。",
                        "channel": channel,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/management/channel/test":
                if not self._require_capability("adminWrite", "当前账号没有测试通知渠道的权限。"):
                    return
                channel = {
                    "id": str(payload.get("id", "")).strip() or "ad-hoc",
                    "name": str(payload.get("name", "")).strip() or "Test Channel",
                    "type": str(payload.get("type", "")).strip(),
                    "target": str(payload.get("target", "")).strip(),
                    "secret": str(payload.get("secret", "")).strip(),
                }
                if not channel["type"]:
                    raise RuntimeError("请先选择通知渠道类型。")
                result = send_notification_message(
                    channel,
                    {
                        "title": "Mission Control Test Ping",
                        "detail": "这是一条来自闭环运营中心的测试通知，说明渠道配置已经可用。",
                    },
                )
                self._audit(
                    "management_channel_test",
                    detail=f"测试通知渠道 {channel['name']}",
                    meta={"channelType": channel["type"], "target": summarize_notification_target(channel)},
                )
                self._send_json(
                    {
                        "ok": True,
                        "message": f"测试通知已发送到 {summarize_notification_target(channel)}。",
                        "result": result,
                    }
                )
                return

            if path == "/api/actions/management/bootstrap":
                if not self._require_capability("taskWrite", "当前账号没有初始化运营规则的权限。"):
                    return
                result = bootstrap_management_rules(self.server.openclaw_dir)
                self._audit(
                    "management_bootstrap",
                    detail="初始化默认闭环运营规则",
                    meta={"created": result["total"]},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"已补齐 {result['total']} 条默认运营规则。",
                        "result": result,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/management/report/export":
                if not self._require_capability("read", "当前账号没有导出运营周报的权限。"):
                    return
                report = export_management_weekly_report(self.server.openclaw_dir)
                self._audit(
                    "management_report_export",
                    detail="导出运营周报",
                    meta={"path": report["path"]},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"运营周报已导出到 {report['path']}。",
                        "report": report,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/orchestration/workflow/save":
                if not self._require_capability("taskWrite", "当前账号没有编辑协作编排的权限。"):
                    return
                workflow = store_save_orchestration_workflow(
                    self.server.openclaw_dir,
                    {
                        "id": str(payload.get("id", "")).strip(),
                        "name": str(payload.get("name", "")).strip(),
                        "description": str(payload.get("description", "")).strip(),
                        "status": str(payload.get("status", "")).strip() or "active",
                        "lanes": payload.get("lanes") if isinstance(payload.get("lanes"), list) else [],
                        "nodes": payload.get("nodes") if isinstance(payload.get("nodes"), list) else [],
                        "meta": payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
                    },
                )
                self._audit(
                    "orchestration_workflow_save",
                    detail=f"保存协作编排 {workflow['name']}",
                    meta={"workflowId": workflow["id"], "nodeCount": len(workflow.get("nodes", []))},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"协作编排 {workflow['name']} 已保存。",
                        "workflow": workflow,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/orchestration/policy/save":
                if not self._require_capability("taskWrite", "当前账号没有编辑动态路由策略的权限。"):
                    return
                policy = store_save_routing_policy(
                    self.server.openclaw_dir,
                    {
                        "id": str(payload.get("id", "")).strip(),
                        "name": str(payload.get("name", "")).strip(),
                        "status": str(payload.get("status", "")).strip() or "active",
                        "strategyType": str(payload.get("strategyType", "")).strip(),
                        "keyword": str(payload.get("keyword", "")).strip(),
                        "targetAgentId": str(payload.get("targetAgentId", "")).strip(),
                        "priorityLevel": str(payload.get("priorityLevel", "")).strip() or "normal",
                        "queueName": str(payload.get("queueName", "")).strip(),
                    },
                )
                self._audit(
                    "orchestration_policy_save",
                    detail=f"保存动态路由策略 {policy['name']}",
                    meta={"policyId": policy["id"], "strategyType": policy["strategyType"]},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"动态路由策略 {policy['name']} 已保存。",
                        "policy": policy,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/conversations/send":
                if not self._require_capability("conversationWrite", "当前账号没有发起或继续对话的权限。"):
                    return
                agent_id = str(payload.get("agentId", "")).strip()
                session_id = str(payload.get("sessionId", "")).strip()
                message = str(payload.get("message", "")).strip()
                thinking = str(payload.get("thinking", "")).strip() or "low"
                result = perform_conversation_send(
                    self.server.openclaw_dir,
                    agent_id=agent_id,
                    session_id=session_id,
                    message=message,
                    thinking=thinking,
                )
                self._audit(
                    "conversation_send",
                    detail=f"向 {agent_id} 发起对话",
                    meta={"agentId": agent_id, "sessionId": session_id or "main"},
                )
                data, _paths = self._refreshed_bundle()
                meta = ((result.get("result", {}) or {}).get("meta", {}) or {}).get("agentMeta", {}) or {}
                actual_agent_id = meta.get("agentId") or agent_id
                actual_session_id = meta.get("sessionId") or session_id
                conversation = load_conversation_transcript(self.server.openclaw_dir, actual_agent_id, actual_session_id)
                session = find_conversation_session(data.get("conversations", {}) or {}, actual_agent_id, actual_session_id)
                payloads = (result.get("result", {}) or {}).get("payloads", []) or []
                reply_preview = payloads[0].get("text", "") if payloads and isinstance(payloads[0], dict) else ""
                self._send_json(
                    {
                        "ok": True,
                        "message": reply_preview[:160] if reply_preview else f"已向 {actual_agent_id} 成功发送消息。",
                        "dashboard": data,
                        "conversation": conversation,
                        "session": session or {"agentId": actual_agent_id, "sessionId": actual_session_id},
                    }
                )
                return

            if path == "/api/actions/theme/switch":
                if not self._require_capability("themeWrite", "只有 Owner 可以切换主题。"):
                    return
                theme_name = str(payload.get("theme", "")).strip()
                if theme_name not in THEME_CATALOG:
                    raise RuntimeError(f"未知主题：{theme_name}")
                perform_theme_switch(self.server.openclaw_dir, theme_name)
                self._audit("theme_switch", detail=f"切换主题到 {theme_name}", meta={"theme": theme_name})
                self.server.dashboard_auth_token = resolve_dashboard_auth_token(self.server.openclaw_dir)
                data, _paths = self._refreshed_bundle()
                display_name = data.get("theme", {}).get("displayName", theme_name)
                self._send_json(
                    {
                        "ok": True,
                        "message": f"主题已切换到 {display_name}，产品上下文已经同步刷新。",
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/context-hub/install":
                if not self._require_capability("adminWrite", "只有 Owner 可以安装和维护 Context Hub CLI。"):
                    return
                result = perform_context_hub_install()
                self._audit("context_hub_install", detail="安装 Context Hub CLI")
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": "Context Hub CLI 已安装。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/context-hub/update":
                if not self._require_capability("adminWrite", "只有 Owner 可以刷新 Context Hub registry。"):
                    return
                result = perform_context_hub_update()
                self._audit("context_hub_update", detail="刷新 Context Hub registry")
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": "Context Hub registry 已刷新。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/context-hub/search":
                result = perform_context_hub_search(
                    query=str(payload.get("query", "")).strip(),
                    lang=str(payload.get("lang", "")).strip(),
                    tags=str(payload.get("tags", "")).strip(),
                    limit=int(payload.get("limit", 8) or 8),
                )
                self._audit("context_hub_search", detail="检索 Context Hub", meta={"query": str(payload.get("query", "")).strip()})
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": "Context Hub 检索已完成。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/context-hub/get":
                result = perform_context_hub_get(
                    entry_id=str(payload.get("id", "")).strip(),
                    lang=str(payload.get("lang", "")).strip(),
                    full=bool(payload.get("full")),
                    files=str(payload.get("files", "")).strip(),
                )
                self._audit("context_hub_get", detail=f"获取 Context Hub 文档 {result.get('id', '')}", meta={"id": result.get("id", "")})
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": "Context Hub 文档已获取。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/context-hub/annotate":
                if not self._require_capability("taskWrite", "只有 Operator / Owner 可以保存 Context Hub 注释。"):
                    return
                entry_id = str(payload.get("id", "")).strip()
                clear = bool(payload.get("clear"))
                result = perform_context_hub_annotate(
                    entry_id=entry_id,
                    note=str(payload.get("note", "")).strip(),
                    clear=clear,
                )
                self._audit("context_hub_annotate", detail=f"{'清除' if clear else '保存'} Context Hub annotation", meta={"id": entry_id})
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": "Context Hub annotation 已更新。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/context-hub/feedback":
                if not self._require_capability("adminWrite", "只有 Owner 可以发送 Context Hub feedback。"):
                    return
                labels = payload.get("labels", [])
                if isinstance(labels, str):
                    labels = [item.strip() for item in labels.split(",") if item.strip()]
                result = perform_context_hub_feedback(
                    entry_id=str(payload.get("id", "")).strip(),
                    rating=str(payload.get("rating", "")).strip(),
                    comment=str(payload.get("comment", "")).strip(),
                    labels=labels if isinstance(labels, list) else [],
                    lang=str(payload.get("lang", "")).strip(),
                    file_path=str(payload.get("file", "")).strip(),
                    agent=str(payload.get("agent", "")).strip(),
                    model=str(payload.get("model", "")).strip(),
                )
                self._audit("context_hub_feedback", detail="发送 Context Hub feedback", meta={"id": str(payload.get("id", "")).strip(), "rating": str(payload.get("rating", "")).strip()})
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": "Context Hub feedback 已发送。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/openclaw/gateway/start":
                if not self._require_capability("adminWrite", "只有 Owner 可以管理 Gateway 服务。"):
                    return
                result = perform_gateway_service_action(self.server.openclaw_dir, "start")
                self._audit("openclaw_gateway_start", detail="启动 Gateway 服务")
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": "Gateway 启动命令已执行。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/openclaw/gateway/restart":
                if not self._require_capability("adminWrite", "只有 Owner 可以管理 Gateway 服务。"):
                    return
                result = perform_gateway_service_action(self.server.openclaw_dir, "restart")
                self._audit("openclaw_gateway_restart", detail="重启 Gateway 服务")
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": "Gateway 重启命令已执行。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/openclaw/browser/start":
                if not self._require_capability("adminWrite", "只有 Owner 可以启动浏览器运行时。"):
                    return
                profile = str(payload.get("profile", "")).strip()
                result = perform_browser_start(self.server.openclaw_dir, profile=profile)
                self._audit("openclaw_browser_start", detail="启动 Browser 运行时", meta={"profile": profile})
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": "Browser 启动命令已执行。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/openclaw/browser/extension/install":
                if not self._require_capability("adminWrite", "只有 Owner 可以安装浏览器扩展。"):
                    return
                result = perform_browser_extension_action(self.server.openclaw_dir, "install")
                path_result = perform_browser_extension_action(self.server.openclaw_dir, "path")
                self._audit("openclaw_browser_extension_install", detail="安装 Browser Extension")
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": "Browser Extension 已安装到本地稳定目录。",
                        "result": {"install": result, "path": path_result},
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/openclaw/browser/profile/create":
                if not self._require_capability("adminWrite", "只有 Owner 可以创建浏览器 profile。"):
                    return
                result = perform_browser_create_profile(
                    self.server.openclaw_dir,
                    name=str(payload.get("name", "")).strip(),
                    driver=str(payload.get("driver", "")).strip() or "openclaw",
                    color=str(payload.get("color", "")).strip(),
                    cdp_url=str(payload.get("cdpUrl", "")).strip(),
                )
                self._audit("openclaw_browser_profile_create", detail=f"创建 Browser Profile {result['name']}", meta={"profile": result["name"]})
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": f"Browser profile {result['name']} 已创建。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/openclaw/browser/open":
                if not self._require_capability("adminWrite", "只有 Owner 可以控制本地浏览器工作台。"):
                    return
                profile = str(payload.get("profile", "")).strip()
                result = perform_browser_open(self.server.openclaw_dir, url=str(payload.get("url", "")).strip(), profile=profile)
                self._audit("openclaw_browser_open", detail="在 Browser 中打开页面", meta={"profile": profile, "url": result["url"]})
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": f"已在 Browser 中打开 {result['url']}。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/openclaw/browser/snapshot":
                if not self._require_capability("adminWrite", "只有 Owner 可以抓取浏览器快照。"):
                    return
                result = perform_browser_snapshot(
                    self.server.openclaw_dir,
                    profile=str(payload.get("profile", "")).strip(),
                    selector=str(payload.get("selector", "")).strip(),
                    target_id=str(payload.get("targetId", "")).strip(),
                    limit=int(payload.get("limit", 120) or 120),
                )
                self._audit("openclaw_browser_snapshot", detail="抓取 Browser Snapshot")
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": "Browser snapshot 已返回。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/openclaw/browser/plan":
                if not self._require_capability("adminWrite", "只有 Owner 可以执行浏览器动作计划。"):
                    return
                result = perform_browser_plan(
                    self.server.openclaw_dir,
                    steps=payload.get("steps", []),
                    profile=str(payload.get("profile", "")).strip(),
                )
                self._audit("openclaw_browser_plan", detail="执行 Browser 动作计划", meta={"steps": len(result.get("results", []))})
                data, _paths = self._refreshed_bundle()
                self._send_json({"ok": True, "message": f"Browser 动作计划已执行 {len(result.get('results', []))} 步。", "result": result, "dashboard": data})
                return

            if path == "/api/actions/admin/user/create":
                if not self._require_capability("adminWrite", "只有 Owner 可以管理团队席位。"):
                    return
                username = str(payload.get("username", "")).strip()
                display_name = str(payload.get("displayName", "")).strip()
                role = str(payload.get("role", "")).strip()
                password = str(payload.get("password", "")).strip()
                user = create_product_user(self.server.openclaw_dir, username, display_name, role, password)
                self._audit("user_create", detail=f"创建团队席位 {user['displayName']}", meta={"username": user["username"], "role": user["role"]})
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"团队账号 {user['displayName']} 已创建。",
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/admin/user/update_access":
                if not self._require_capability("adminWrite", "只有 Owner 可以调整团队席位。"):
                    return
                username = str(payload.get("username", "")).strip()
                role = str(payload.get("role", "")).strip()
                status = str(payload.get("status", "")).strip()
                user = update_product_user_access(self.server.openclaw_dir, username, role, status)
                self._audit(
                    "user_access_update",
                    detail=f"更新团队席位 {user['displayName']}",
                    meta={"username": user["username"], "role": user["role"], "status": user["status"]},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"团队席位 {user['displayName']} 已更新为 {user['roleLabel']} / {user['status']}。",
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/admin/user/reset_password":
                if not self._require_capability("adminWrite", "只有 Owner 可以重置团队账号密码。"):
                    return
                username = str(payload.get("username", "")).strip()
                password = str(payload.get("password", "")).strip()
                user = reset_product_user_password(self.server.openclaw_dir, username, password)
                self._audit(
                    "user_password_reset",
                    detail=f"重置团队账号 {user['displayName']} 的密码",
                    meta={"username": user["username"]},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"团队账号 {user['displayName']} 的密码已经重置。",
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/admin/instance/register":
                if not self._require_capability("adminWrite", "只有 Owner 可以登记和维护安装实例。"):
                    return
                target_dir = str(payload.get("openclawDir", "")).strip()
                label = str(payload.get("label", "")).strip()
                installation = register_installation(self.server.openclaw_dir, target_dir, label=label)
                self._audit(
                    "installation_register",
                    detail=f"登记安装实例 {installation['label']}",
                    meta={"openclawDir": installation["openclawDir"], "theme": installation.get("theme", "")},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"安装实例 {installation['label']} 已登记进控制平面。",
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/admin/instance/remove":
                if not self._require_capability("adminWrite", "只有 Owner 可以登记和维护安装实例。"):
                    return
                target_dir = str(payload.get("openclawDir", "")).strip()
                removed_dir = remove_installation(self.server.openclaw_dir, target_dir)
                self._audit(
                    "installation_remove",
                    detail=f"移除安装实例 {removed_dir}",
                    meta={"openclawDir": removed_dir},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": "安装实例已从控制平面移除。",
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/admin/tenant/save":
                if not self._require_capability("adminWrite", "只有 Owner 可以管理租户。"):
                    return
                name = str(payload.get("name", "")).strip()
                if not name:
                    raise RuntimeError("请先填写租户名称。")
                tenant = store_save_tenant(
                    self.server.openclaw_dir,
                    {
                        "id": str(payload.get("id", "")).strip(),
                        "name": name,
                        "slug": str(payload.get("slug", "")).strip(),
                        "status": str(payload.get("status", "")).strip() or "active",
                        "primaryOpenclawDir": str(payload.get("primaryOpenclawDir", "")).strip(),
                        "meta": payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
                    },
                )
                self._audit(
                    "tenant_save",
                    detail=f"保存租户 {tenant['name']}",
                    meta={"tenantId": tenant["id"], "slug": tenant.get("slug", "")},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"租户 {tenant['name']} 已保存。",
                        "tenant": tenant,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/admin/tenant/installation/save":
                if not self._require_capability("adminWrite", "只有 Owner 可以绑定租户安装。"):
                    return
                tenant_id = str(payload.get("tenantId", "")).strip()
                target_dir = str(payload.get("openclawDir", "")).strip()
                if not tenant_id or not target_dir:
                    raise RuntimeError("请先选择租户并填写 OpenClaw 目录。")
                installation = register_installation(
                    self.server.openclaw_dir,
                    target_dir,
                    label=str(payload.get("label", "")).strip(),
                )
                binding = store_save_tenant_installation(
                    self.server.openclaw_dir,
                    {
                        "tenantId": tenant_id,
                        "openclawDir": installation["openclawDir"],
                        "label": str(payload.get("bindingLabel", "")).strip() or installation["label"],
                        "role": str(payload.get("role", "")).strip() or "primary",
                    },
                )
                tenant = find_tenant_record(self.server.openclaw_dir, tenant_id)
                if tenant and (binding.get("role") == "primary" or not tenant.get("primaryOpenclawDir")):
                    tenant = store_save_tenant(
                        self.server.openclaw_dir,
                        {
                            **tenant,
                            "primaryOpenclawDir": installation["openclawDir"],
                        },
                    )
                self._audit(
                    "tenant_installation_save",
                    detail=f"绑定租户安装 {binding['label']}",
                    meta={"tenantId": tenant_id, "openclawDir": binding["openclawDir"], "role": binding.get("role", "")},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"租户安装 {binding['label']} 已绑定。",
                        "tenant": tenant,
                        "binding": binding,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/admin/tenant/api-key/create":
                if not self._require_capability("adminWrite", "只有 Owner 可以创建租户 API Key。"):
                    return
                tenant_id = str(payload.get("tenantId", "")).strip()
                name = str(payload.get("name", "")).strip()
                scopes = payload.get("scopes") if isinstance(payload.get("scopes"), list) else []
                if not tenant_id or not name:
                    raise RuntimeError("请先选择租户并填写 API Key 名称。")
                result = store_create_tenant_api_key(self.server.openclaw_dir, tenant_id, name, scopes=scopes or None)
                self._audit(
                    "tenant_api_key_create",
                    detail=f"创建租户 API Key {name}",
                    meta={"tenantId": tenant_id, "keyId": (result.get('key') or {}).get('id', '')},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"租户 API Key {name} 已生成，请立即妥善保存。",
                        "apiKey": result,
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/skills/scaffold":
                if not self._require_capability("adminWrite", "只有 Owner 可以创建和维护技能目录。"):
                    return
                slug = str(payload.get("slug", "")).strip()
                title = str(payload.get("title", "")).strip()
                description = str(payload.get("description", "")).strip()
                trigger_phrase = str(payload.get("triggerPhrase", "")).strip()
                category = str(payload.get("category", "")).strip() or "workflow-automation"
                mcp_server = str(payload.get("mcpServer", "")).strip()
                skill = perform_skill_scaffold(
                    self.server.openclaw_dir,
                    slug=slug,
                    title=title,
                    description=description,
                    trigger_phrase=trigger_phrase,
                    category=category,
                    include_scripts=bool(payload.get("includeScripts")),
                    include_references=payload.get("includeReferences", True) is not False,
                    include_assets=bool(payload.get("includeAssets")),
                    mcp_server=mcp_server,
                )
                self._audit(
                    "skill_scaffold",
                    detail=f"创建技能 {skill.get('slug', slug)}",
                    meta={"skill": skill.get("slug", slug), "category": category},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"技能 {skill.get('displayName', slug)} 已创建，并完成首次校验。",
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/skills/package":
                if not self._require_capability("adminWrite", "只有 Owner 可以打包和分发技能。"):
                    return
                slug = str(payload.get("slug", "")).strip()
                bundle = perform_skill_package(self.server.openclaw_dir, slug)
                self._audit(
                    "skill_package",
                    detail=f"打包技能 {slug}",
                    meta={"skill": slug, "archivePath": bundle.get("archivePath", "")},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"技能 {slug} 已打包到 {bundle.get('archivePath', '')}。",
                        "dashboard": data,
                    }
                )
                return

            if path == "/api/actions/skills/publish":
                if not self._require_capability("adminWrite", "只有 Owner 可以把技能发布到 OpenClaw。"):
                    return
                slug = str(payload.get("slug", "")).strip()
                if not slug:
                    raise RuntimeError("请先选择要发布的 skill。")
                published = perform_skill_publish(self.server.openclaw_dir, slug)
                self._audit(
                    "skill_publish",
                    detail=f"发布技能 {slug} 到 OpenClaw",
                    meta={"skill": slug, "targetPath": published.get("targetPath", "")},
                )
                data, _paths = self._refreshed_bundle()
                self._send_json(
                    {
                        "ok": True,
                        "message": f"技能 {slug} 已发布到 {published.get('targetPath', '')}。",
                        "dashboard": data,
                    }
                )
                return

            self._send_json({"ok": False, "error": "not_found", "message": "未知操作接口。"}, status=404)
        except RuntimeError as error:
            self._audit("action_error", outcome="denied", detail=str(error), meta={"path": path})
            self._send_json({"ok": False, "error": "action_failed", "message": str(error)}, status=400)
        except Exception as error:
            self._audit("action_error", outcome="error", detail=str(error), meta={"path": path})
            self._send_json({"ok": False, "error": "internal_error", "message": str(error)}, status=500)

    def do_GET(self):
        path = self._path()
        if self._serve_frontend_asset(path):
            return
        if path.startswith("/api/v1/"):
            if self._handle_rest_get(path):
                return
        if path == "/legacy-login":
            if self._is_authenticated():
                self._send_redirect("/")
                return
            body = render_login_html(self.server.openclaw_dir, next_path=self._next_path()).encode("utf-8")
            self._send_bytes(body, "text/html; charset=utf-8")
            return
        if path == "/legacy":
            self._serve_legacy_dashboard()
            return
        if path == "/login":
            self._handle_login_get()
            return
        if path == "/api/auth/session":
            self._handle_auth_session_get()
            return
        if self._frontend_dist() and path in self.SPA_ROUTES:
            self._serve_frontend_index()
            return
        if not self._require_auth(api=path.startswith("/api/") or path == "/events"):
            return
        if path in self.SPA_ROUTES:
            data, _paths = self._bundle()
            self._send_bytes(render_html(data).encode("utf-8"), "text/html; charset=utf-8")
            return
        if path in ("/api/dashboard", "/collaboration-dashboard.json"):
            data, _paths = self._bundle()
            body = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/api/agents":
            data, _paths = self._bundle()
            body = (json.dumps({"agents": data.get("agents", [])}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/api/tasks":
            data, _paths = self._bundle()
            body = (json.dumps({"tasks": data.get("taskIndex", [])}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/api/conversations":
            data, _paths = self._bundle()
            body = (json.dumps({"conversations": data.get("conversations", {})}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/api/conversations/transcript":
            agent_id = str(self._query().get("agentId", [""])[0] or "").strip()
            session_id = str(self._query().get("sessionId", [""])[0] or "").strip()
            if not agent_id or not session_id:
                self._send_json({"ok": False, "error": "missing_params", "message": "需要 agentId 和 sessionId。"}, status=400)
                return
            conversation = load_conversation_transcript(self.server.openclaw_dir, agent_id, session_id)
            self._send_json({"ok": True, "conversation": conversation})
            return
        if path == "/api/events":
            data, _paths = self._bundle()
            body = (json.dumps({"events": data.get("events", [])}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/api/themes":
            data, _paths = self._bundle()
            body = (json.dumps({"theme": data.get("theme", {}), "themeCatalog": data.get("themeCatalog", [])}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/api/skills":
            data, _paths = self._bundle()
            body = (json.dumps({"skills": data.get("skills", {})}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/api/context":
            data, _paths = self._bundle()
            body = (json.dumps({"contextHub": data.get("contextHub", {})}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/api/openclaw":
            data, _paths = self._bundle()
            body = (json.dumps({"openclaw": data.get("openclaw", {})}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/api/deliverables":
            data, _paths = self._bundle()
            body = (json.dumps({"deliverables": data.get("deliverables", [])}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/api/admin":
            if not self._can("auditView"):
                self._send_json({"ok": False, "error": "permission_denied", "message": "当前账号没有查看后台治理数据的权限。"}, status=403)
                return
            data, _paths = self._bundle()
            body = (json.dumps({"admin": data.get("admin", {})}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/events":
            self._serve_events()
            return
        self._send_bytes(b"Not found", "text/plain; charset=utf-8", status=404)

    def do_POST(self):
        path = self._path()
        if path.startswith("/api/v1/"):
            if self._handle_rest_post(path):
                return
        if path == "/login":
            self._handle_login_post()
            return
        if path == "/api/auth/login":
            self._handle_auth_login_json()
            return
        if path == "/api/auth/logout":
            self._handle_auth_logout_json()
            return
        if path == "/logout":
            self._handle_logout_post()
            return
        if not self._require_auth(api=path.startswith("/api/") or path == "/events"):
            return
        if path.startswith("/api/actions/"):
            self._handle_action_post(path)
            return
        self._send_bytes(b"Method not allowed", "text/plain; charset=utf-8", status=405)

    def do_OPTIONS(self):
        path = self._path()
        if path.startswith("/api/") or path == "/events":
            self._send_preflight()
            return
        self._send_bytes(b"Method not allowed", "text/plain; charset=utf-8", status=405)

    def _serve_events(self):
        if not self._is_authenticated():
            self._send_bytes(b"auth required", "text/plain; charset=utf-8", status=401)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Connection", "keep-alive")
        for key, value in self._cors_headers():
            self.send_header(key, value)
        self.end_headers()

        last_signature = None
        try:
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            while True:
                data, _paths = self._bundle()
                if data["signature"] != last_signature:
                    payload = json.dumps(
                        {"signature": data["signature"], "generatedAt": data["generatedAt"]},
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


def serve_dashboard(openclaw_dir, output_dir, port, live_interval, frontend_dist="", cors_origins=""):
    server = ThreadingHTTPServer(("127.0.0.1", port), CollaborationDashboardHandler)
    server.openclaw_dir = Path(openclaw_dir)
    server.output_dir = Path(output_dir) if output_dir else Path(openclaw_dir) / "dashboard"
    server.live_interval = live_interval
    server.dashboard_auth_token = resolve_dashboard_auth_token(server.openclaw_dir)
    server.frontend_dist = resolve_frontend_dist(server.openclaw_dir, explicit_path=frontend_dist)
    server.cors_origins = parse_cors_origins(cors_origins)
    build_dashboard_bundle(server.openclaw_dir, server.output_dir)
    if server.frontend_dist:
        print(f"Serving mission control API at http://127.0.0.1:{port}/api/dashboard")
        print(f"Serving separated frontend at http://127.0.0.1:{port}/")
        print(f"Legacy monolith remains available at http://127.0.0.1:{port}/legacy")
    else:
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
    parser.add_argument("--frontend-dist", default="")
    parser.add_argument("--cors-origins", default=",".join(sorted(DEFAULT_FRONTEND_ORIGINS)))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    openclaw_dir = infer_openclaw_dir(args.dir)
    data, paths = build_dashboard_bundle(openclaw_dir, args.output_dir or None)
    if not args.quiet:
        print(f"Generated dashboard HTML: {paths['html']}")
        print(f"Generated dashboard JSON: {paths['json']}")
    if args.serve:
        serve_dashboard(
            openclaw_dir,
            args.output_dir or None,
            args.port,
            args.live_interval,
            frontend_dist=args.frontend_dist,
            cors_origins=args.cors_origins,
        )


if __name__ == "__main__":
    main()
