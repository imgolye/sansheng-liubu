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
    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 28%, transparent); }
      70% { box-shadow: 0 0 0 12px color-mix(in srgb, currentColor 0%, transparent); }
      100% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 0%, transparent); }
    }
    @media (max-width: 1240px) {
      .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .relay-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .main-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 760px) {
      .shell { width: min(100vw - 18px, 1480px); margin: 10px auto 26px; }
      .hero { padding: 22px 18px 20px; border-radius: 24px; }
      .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .relay-grid { grid-template-columns: 1fr; }
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
  <div class="shell">
    <section class="hero">
      <div class="eyebrow">Multi-Agent Mission Control</div>
      <h1>用户终于能看到协同，甚至能点开回放。</h1>
      <p class="lede">你不只是在看汇总指标。点任意 Agent 卡片可以打开最近信号与在手任务，点任务卡片可以展开完整接力回放。这样用户能分辨系统是在真正协同推进，还是只是静态排队。</p>
      <div class="hero-meta">
        <span>主题：<strong id="theme-name"></strong></span>
        <span>主理人：<strong id="owner-title"></strong></span>
        <span>生成时间：<strong id="generated-at"></strong></span>
        <span>安装目录：<strong id="install-dir"></strong></span>
      </div>
      <div class="hero-tools">
        <button class="button" id="refresh-now">立即刷新</button>
        <button class="button secondary" id="toggle-refresh">暂停实时刷新</button>
        <a class="button secondary" href="./collaboration-dashboard.json">查看 JSON 快照</a>
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
            <p class="panel-subtitle">点开任意 Agent 看它最近的信号、接到的任务和手上在忙什么。</p>
          </div>
        </div>
        <div class="agent-grid" id="agent-grid"></div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">任务河道</h2>
            <p class="panel-subtitle">点开任务看 todo、当前负责人和完整协同回放。</p>
          </div>
        </div>
        <div class="task-list" id="task-list"></div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">信号时间线</h2>
            <p class="panel-subtitle">最近发生的 handoff 与 progress。点击事件可以直接跳到任务回放。</p>
          </div>
        </div>
        <div class="event-feed" id="event-feed"></div>
      </section>
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
    const refs = {
      metricGrid: document.getElementById("metric-grid"),
      relayGrid: document.getElementById("relay-grid"),
      agentGrid: document.getElementById("agent-grid"),
      taskList: document.getElementById("task-list"),
      eventFeed: document.getElementById("event-feed"),
      generatedAt: document.getElementById("generated-at"),
      themeName: document.getElementById("theme-name"),
      ownerTitle: document.getElementById("owner-title"),
      installDir: document.getElementById("install-dir"),
      refreshNow: document.getElementById("refresh-now"),
      toggleRefresh: document.getElementById("toggle-refresh"),
      liveIndicator: document.getElementById("live-indicator"),
      scrim: document.getElementById("scrim"),
      drawer: document.getElementById("drawer"),
      drawerKicker: document.getElementById("drawer-kicker"),
      drawerTitle: document.getElementById("drawer-title"),
      drawerBody: document.getElementById("drawer-body"),
      drawerClose: document.getElementById("drawer-close"),
    };

    const supportsHttp = location.protocol.startsWith("http");
    let paused = false;
    let eventSource = null;
    let reconnectTimer = null;
    let lastSyncAt = Date.now();
    let connectionMode = supportsHttp ? "connecting" : "snapshot";
    let fetchInFlight = false;
    let selection = { kind: null, id: null };

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

    function renderMetrics() {
      clearNode(refs.metricGrid);
      const metrics = [
        ["活跃任务", state.metrics.activeTasks, "还在推进中的任务数量"],
        ["活跃 Agent", state.metrics.activeAgents, "当前正在处理或等待结果的 Agent"],
        ["阻塞任务", state.metrics.blockedTasks, "需要用户介入或额外资源的任务"],
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

    function renderRelays() {
      clearNode(refs.relayGrid);
      if (!(state.relays || []).length) {
        refs.relayGrid.append(el("div", "empty", "最近 24 小时还没有足够的接力记录。先运行几轮任务，协同图就会出现。"));
        return;
      }

      state.relays.forEach((relay) => {
        const card = el("div", "relay");
        card.append(el("div", "relay-path", `${relay.from} → ${relay.to}`));
        card.append(el("div", "relay-count", `${relay.count} 次`));
        card.append(el("div", "relay-meta", `最近一次：${relay.lastAgo}`));
        refs.relayGrid.append(card);
      });
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

    function renderAgents() {
      clearNode(refs.agentGrid);
      (state.agents || []).forEach((agent) => {
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

        const focus = el("div", "focus");
        focus.textContent = agent.focus || "当前没有明确的 progress signal，可以继续观察下一次任务推进。";
        card.append(focus);

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

        refs.agentGrid.append(card);
      });
    }

    function renderTasks() {
      clearNode(refs.taskList);
      if (!(state.tasks || []).length) {
        refs.taskList.append(el("div", "empty", "当前没有活跃任务。可以先发起一个明确任务，系统会在这里展示协同过程。"));
        return;
      }

      state.tasks.forEach((task) => {
        const card = el("article", `task-card${task.blocked ? " blocked" : ""}`);
        attachOpenTask(card, task.id);

        const head = el("div", "task-head");
        const titleWrap = el("div");
        titleWrap.append(el("div", "task-title", task.title));
        titleWrap.append(el("div", "task-sub", `${task.id} · 当前负责人：${task.currentAgentLabel || task.org || "未知"} · ${task.updatedAgo}`));
        head.append(titleWrap);
        head.append(el("div", "status-pill status-standby", task.state));
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

        refs.taskList.append(card);
      });
    }

    function renderEvents() {
      clearNode(refs.eventFeed);
      if (!(state.events || []).length) {
        refs.eventFeed.append(el("div", "empty", "还没有 progress 或 handoff 事件。"));
        return;
      }

      state.events.forEach((event) => {
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
        refs.eventFeed.append(item);
      });
    }

    function renderMeta() {
      refs.generatedAt.textContent = formatClock(state.generatedAt);
      refs.themeName.textContent = state.theme.displayName;
      refs.ownerTitle.textContent = state.ownerTitle;
      refs.installDir.textContent = state.openclawDir;
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
      if (!selection.kind || !selection.id) {
        return;
      }
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

    function renderAll() {
      renderMeta();
      renderMetrics();
      renderRelays();
      renderAgents();
      renderTasks();
      renderEvents();
      syncDrawer();
    }

    async function fetchLatestDashboard(reason = "manual") {
      if (!supportsHttp || paused || fetchInFlight) {
        return;
      }
      fetchInFlight = true;
      try {
        const response = await fetch(`./api/dashboard?_=${Date.now()}`, { cache: "no-store" });
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
      if (!supportsHttp || paused) {
        return;
      }
      if (!window.EventSource) {
        connectionMode = "snapshot";
        return;
      }
      disconnectLive();
      connectionMode = "connecting";
      setLiveStatus("正在建立实时连接...", "warn");
      eventSource = new EventSource("./events");
      eventSource.addEventListener("dashboard", async () => {
        await fetchLatestDashboard("stream");
      });
      eventSource.onopen = () => {
        connectionMode = "live";
        lastSyncAt = Date.now();
      };
      eventSource.onerror = () => {
        if (paused) {
          return;
        }
        connectionMode = "degraded";
        disconnectLive();
        reconnectTimer = setTimeout(() => connectLive(), 4000);
      };
    }

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

    setInterval(() => {
      if (paused) {
        return;
      }
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
      } else if (connectionMode === "paused") {
        setLiveStatus("实时刷新已暂停", "paused");
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
            "todo": todo,
            "todoItems": todo_items,
            "route": task_route(task),
            "blocked": state == "blocked",
            "active": state not in TERMINAL_STATES,
            "replay": list(reversed(replay[-24:])),
        }
        task_index.append(task_record)

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
        "taskIndex": task_index[:72],
        "events": global_events[:42],
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
    server_version = "SanshengDashboard/1.5"

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
            self._send_bytes(render_html(data).encode("utf-8"), "text/html; charset=utf-8")
            return
        if path in ("/api/dashboard", "/collaboration-dashboard.json"):
            data, _paths = self._bundle()
            body = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
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
