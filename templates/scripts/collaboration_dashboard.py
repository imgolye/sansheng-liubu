#!/usr/bin/env python3
"""Generate and serve a visual collaboration dashboard for all agents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import Counter, defaultdict
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

THEME_CATALOG = {
    "imperial": {
        "displayName": "三省六部",
        "tagline": "层级清晰，适合复杂任务编排",
        "bestFor": "个人玩家、极客、强流程任务",
        "summary": "强调审议、调度和六部协作，适合希望把复杂任务拆成正式流转的人。",
    },
    "corporate": {
        "displayName": "企业组织",
        "tagline": "更像 CEO / VP / Team 的现代协同方式",
        "bestFor": "企业团队、正式场景、跨职能配合",
        "summary": "用更贴近公司组织的命名和职责，让多 Agent 协同更容易被业务团队理解。",
    },
    "startup": {
        "displayName": "创业团队",
        "tagline": "扁平直接，适合小团队高速迭代",
        "bestFor": "创业公司、产品开发、小规模团队",
        "summary": "减少流程负担，让 PM、全栈、测试、运营等角色快速接力推进。",
    },
}


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
      --shadow: 0 26px 80px rgba(46, 31, 21, 0.12);
      --shadow-soft: 0 12px 28px rgba(46, 31, 21, 0.08);
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; }
    body {
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 0% 0%, rgba(255,255,255,0.7), transparent 32%),
        radial-gradient(circle at 100% 0%, rgba(255,255,255,0.4), transparent 28%),
        linear-gradient(155deg, var(--bg), var(--bg2));
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
      padding: 28px;
      border-radius: 30px;
      border: 1px solid var(--line);
      background:
        linear-gradient(130deg, color-mix(in srgb, var(--panel) 88%, white 12%), rgba(255,255,255,0.55)),
        radial-gradient(circle at 100% 0%, color-mix(in srgb, var(--accentSoft) 72%, white 28%), transparent 42%);
      box-shadow: var(--shadow);
    }
    .hero::after {
      content: "";
      position: absolute;
      right: -96px;
      top: -84px;
      width: 280px;
      height: 280px;
      border-radius: 50%;
      background: radial-gradient(circle, color-mix(in srgb, var(--accentSoft) 78%, white 22%), transparent 64%);
      opacity: 0.78;
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
      margin: 14px 0 12px;
      font-family: "Fraunces", "Times New Roman", serif;
      font-size: clamp(2.5rem, 4vw, 5rem);
      line-height: 0.94;
      max-width: 11ch;
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
      border-radius: 999px;
      padding: 11px 16px;
      background: var(--accent);
      color: #fffaf3;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 12px 26px rgba(130, 73, 24, 0.18);
      transition: transform 140ms ease-out, box-shadow 140ms ease-out, background 140ms ease-out;
      text-decoration: none;
    }
    .button:hover { transform: translateY(-1px); }
    .button.secondary {
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      box-shadow: none;
      border: 1px solid var(--line);
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
      border-radius: 20px;
      background: rgba(255,255,255,0.6);
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
      font-family: "Fraunces", "Times New Roman", serif;
      font-size: clamp(1.8rem, 2.5vw, 3rem);
    }
    .metric-note {
      margin-top: 6px;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.55;
    }
    .panel {
      overflow: hidden;
      border-radius: 26px;
      border: 1px solid var(--line);
      background: var(--panel);
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
      font-family: "Fraunces", "Times New Roman", serif;
      font-size: 1.4rem;
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
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.54);
    }
    .relay-path {
      font-weight: 700;
      line-height: 1.45;
    }
    .relay-count {
      margin-top: 8px;
      font-family: "Fraunces", "Times New Roman", serif;
      font-size: 2rem;
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
      border-radius: 20px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.58);
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
      border-radius: 999px;
      font-size: 0.82rem;
      font-weight: 700;
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
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.62);
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
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
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
      font-family: "Fraunces", "Times New Roman", serif;
      font-size: 2rem;
      line-height: 1;
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
      width: min(1720px, calc(100vw - 24px));
      margin: 12px auto 28px;
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      gap: 18px;
      align-items: start;
    }
    .rail {
      position: sticky;
      top: 12px;
      display: grid;
      gap: 14px;
      align-self: start;
    }
    .brand-card,
    .rail-panel,
    .topbar {
      border-radius: 26px;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow-soft);
    }
    .brand-card,
    .rail-panel {
      padding: 18px;
    }
    .brand-card h2 {
      margin: 12px 0 8px;
      font-family: "Fraunces", "Times New Roman", serif;
      font-size: 2rem;
      line-height: 0.95;
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
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,0.62);
      padding: 13px 14px;
      color: var(--ink);
      cursor: pointer;
      font-weight: 700;
      transition: transform 140ms ease-out, border-color 140ms ease-out, background 140ms ease-out;
    }
    .nav-link span {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 0.88rem;
      font-weight: 500;
    }
    .nav-link:hover { transform: translateY(-1px); }
    .nav-link[data-active="true"] {
      background: color-mix(in srgb, var(--accentSoft) 36%, white 64%);
      border-color: color-mix(in srgb, var(--accent) 28%, var(--line));
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
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.58);
    }
    .rail-kv strong,
    .status-card strong {
      display: block;
      margin-top: 6px;
      font-size: 1.1rem;
    }
    .workspace-shell {
      min-width: 0;
      display: grid;
      gap: 18px;
    }
    .topbar {
      padding: 18px 20px;
      display: grid;
      grid-template-columns: auto minmax(260px, 1fr) auto;
      gap: 16px;
      align-items: center;
    }
    .topbar-title {
      margin-top: 6px;
      font-family: "Fraunces", "Times New Roman", serif;
      font-size: 2rem;
      line-height: 0.95;
    }
    .search-shell {
      display: flex;
      align-items: center;
    }
    .search-input {
      width: 100%;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      padding: 13px 18px;
      outline: none;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.55);
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
      border-radius: 20px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.62);
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
      border-radius: 999px;
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      padding: 8px 12px;
      font-weight: 700;
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
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.7);
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
      border-radius: 999px;
      border: 1px solid var(--line);
      font-size: 0.8rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      background: rgba(255,255,255,0.7);
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
    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 28%, transparent); }
      70% { box-shadow: 0 0 0 12px color-mix(in srgb, currentColor 0%, transparent); }
      100% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 0%, transparent); }
    }
    @media (max-width: 1240px) {
      .app-shell { grid-template-columns: 1fr; }
      .rail { position: static; }
      .topbar { grid-template-columns: 1fr; }
      .overview-grid, .split-grid { grid-template-columns: 1fr; }
      .status-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .relay-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .main-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 760px) {
      .shell { width: min(100vw - 18px, 1480px); margin: 10px auto 26px; }
      .app-shell { width: min(100vw - 14px, 1720px); margin: 8px auto 22px; }
      .hero { padding: 22px 18px 20px; border-radius: 24px; }
      .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .relay-grid { grid-template-columns: 1fr; }
      .status-strip { grid-template-columns: 1fr 1fr; }
      .agent-facts, .drawer-grid { grid-template-columns: 1fr 1fr; }
      .panel-head { padding: 18px 18px 10px; }
      .agent-grid, .task-list, .event-feed { padding: 16px; }
      .event-feed::before { left: 16px; }
      .event { padding-left: 20px; }
      .event::before { left: -15px; }
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
  <div class="app-shell">
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
          <button class="nav-link" data-view="activity">活动时间线<span>handoff 与 progress 的完整动态</span></button>
          <button class="nav-link" data-view="themes">主题中心<span>当前组织主题与产品运行命令</span></button>
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
          <input class="search-input" id="global-search" type="search" placeholder="搜索 Agent、任务、事件、交付物">
        </div>
        <div class="topbar-tools">
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

        <section class="view" data-view="agents" hidden>
          <div class="status-strip" id="agent-status-strip"></div>
          <section class="panel">
            <div class="panel-head">
              <div>
                <h2 class="panel-title">Agent 运营台</h2>
                <p class="panel-subtitle">完整查看每个 Agent 的状态、焦点、在手任务和最近协同信号。</p>
              </div>
            </div>
            <div class="agent-grid" id="agents-page-grid"></div>
          </section>
        </section>

        <section class="view" data-view="tasks" hidden>
          <section class="panel">
            <div class="panel-head">
              <div>
                <h2 class="panel-title">交付执行台</h2>
                <p class="panel-subtitle">按阶段筛选任务，打开任务回放，直接追踪产出与阻塞。</p>
              </div>
              <div class="filter-row" id="task-filter-row"></div>
            </div>
            <div class="task-list" id="tasks-page-list"></div>
          </section>

          <div class="split-grid">
            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2 class="panel-title">交付物</h2>
                  <p class="panel-subtitle">展示已完成任务和其输出路径，方便把多 Agent 产出当成可管理资产。</p>
                </div>
              </div>
              <div class="deliverable-list" id="deliverables-list"></div>
            </section>

            <section class="panel">
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
      activity: {
        title: "活动时间线",
        subtitle: "按时间追踪 handoff 与 progress，快速还原协同路径。",
      },
      themes: {
        title: "主题中心",
        subtitle: "把组织主题、运行命令和当前上下文放进一个统一入口。",
      },
    };

    const refs = {
      navLinks: Array.from(document.querySelectorAll(".nav-link")),
      views: Array.from(document.querySelectorAll(".view")),
      viewTitle: document.getElementById("view-title"),
      viewSubtitle: document.getElementById("view-subtitle"),
      globalSearch: document.getElementById("global-search"),
      metricGrid: document.getElementById("metric-grid"),
      overviewRelayGrid: document.getElementById("overview-relay-grid"),
      overviewAgentGrid: document.getElementById("overview-agent-grid"),
      overviewTaskList: document.getElementById("overview-task-list"),
      overviewEventFeed: document.getElementById("overview-event-feed"),
      agentStatusStrip: document.getElementById("agent-status-strip"),
      agentsPageGrid: document.getElementById("agents-page-grid"),
      taskFilterRow: document.getElementById("task-filter-row"),
      tasksPageList: document.getElementById("tasks-page-list"),
      deliverablesList: document.getElementById("deliverables-list"),
      taskCommandList: document.getElementById("task-command-list"),
      activityRelayGrid: document.getElementById("activity-relay-grid"),
      activityEventFeed: document.getElementById("activity-event-feed"),
      currentThemeSummary: document.getElementById("current-theme-summary"),
      themeGrid: document.getElementById("theme-grid"),
      themeCommandList: document.getElementById("theme-command-list"),
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
        "/activity": "activity",
        "/themes": "themes",
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
        refs.themeGrid.append(card);
      });
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
      renderCommandCards(refs.railCommandList, (state.commands || []).slice(0, 2), "暂无快速动作。");
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
      renderStatusStrip();
      renderAgentsInto(refs.agentsPageGrid, filteredAgents(), "当前没有匹配的 Agent。");
    }

    function renderTasksView() {
      renderTaskFilters();
      renderTasksInto(refs.tasksPageList, filteredTasks(), "当前没有匹配的任务。");
      renderDeliverables();
      renderCommandCards(refs.taskCommandList, state.commands || [], "当前没有可用命令。");
    }

    function renderActivityView() {
      renderRelaysInto(refs.activityRelayGrid, state.relays || [], "最近 24 小时还没有形成 handoff 网络。");
      renderEventsInto(refs.activityEventFeed, filteredEvents(), "当前没有匹配的活动事件。");
    }

    function renderThemesView() {
      renderThemes();
      renderCommandCards(refs.themeCommandList, state.commands || [], "当前没有主题相关命令。");
    }

    function renderAll() {
      renderMeta();
      applyViewState();
      renderOverview();
      renderAgentsView();
      renderTasksView();
      renderActivityView();
      renderThemesView();
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
    agents = load_agents(config)
    router_agent_id = get_router_agent_id(config)
    kanban_cfg = load_kanban_config(openclaw_dir, router_agent_id)
    now = now_utc()
    tasks = merge_tasks(openclaw_dir, config)
    theme_name = config.get("sanshengLiubu", {}).get("theme", "imperial")
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

    return {
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "generatedAgo": "刚刚",
        "openclawDir": str(openclaw_dir),
        "routerAgentId": router_agent_id,
        "theme": {
            "name": theme_name,
            "displayName": config.get("sanshengLiubu", {}).get("displayName", theme_name),
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


class CollaborationDashboardHandler(BaseHTTPRequestHandler):
    server_version = "SanshengDashboard/1.6"

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
        if path in ("/", "/overview", "/agents", "/tasks", "/activity", "/themes", "/collaboration-dashboard.html"):
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
        if path == "/api/deliverables":
            data, _paths = self._bundle()
            body = (json.dumps({"deliverables": data.get("deliverables", [])}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/events":
            self._serve_events()
            return
        self._send_bytes(b"Not found", "text/plain; charset=utf-8", status=404)

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
