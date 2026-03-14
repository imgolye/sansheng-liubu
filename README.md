# 三省六部 — OpenClaw 多 Agent 编排系统

[![Release](https://img.shields.io/github/v/release/imgolye/sansheng-liubu?label=release)](https://github.com/imgolye/sansheng-liubu/releases/latest)

一键部署 11 个协作 AI Agent，模拟组织架构处理复杂任务。

## 1.4.0 亮点

现在不只是能跑多 Agent，还能让用户看到协同正在发生：

```bash
python3 ~/.openclaw/workspace-your-router-id/scripts/collaboration_dashboard.py --serve
```

这一版新增：
- 协同态势看板：看到谁在执行、谁在等待、任务如何接力
- HTML + JSON 双输出：适合浏览器查看，也适合后续接系统面板
- 本地实时 Web 面板：`--serve` 会启动带 SSE 推送的常驻监控页
- 运行中切换主题：`bash bin/switch_theme.sh --theme startup`
- 自动迁移：保留现有频道、模型、网关 token、任务板和 workspace 产物

## 架构

```
用户（老板/CEO/皇上）
  └─ 路由 Agent ── 消息分拣、建任务、回奏
        ├─ 简报 Agent ── 每日情报
        └─ 规划 Agent ── 方案设计
              ├─ 审议 Agent ── 重大任务把关
              └─ 调度 Agent ── 派发执行
                    ├─ 工程部 ── 开发/架构
                    ├─ 运维部 ── 部署/安全
                    ├─ 数据部 ── 分析/报表
                    ├─ 内容部 ── 文档/对外
                    ├─ 质量部 ── 测试/审查
                    └─ 行政部 ── 人事/管理
```

## 快速开始

```bash
git clone https://github.com/imgolye/sansheng-liubu.git
cd sansheng-liubu
bash bin/setup.sh
bash bin/validate.sh   # 验证安装
```

安装向导会交互式询问：
1. 配置频道（飞书 / Telegram / QQ）
2. 选择模型

主题通过 `--theme` 指定，默认是 `imperial`：

```bash
bash bin/setup.sh --theme corporate
```

## 5 分钟上手

### 1. 安装到默认目录

```bash
bash bin/setup.sh
```

默认会写入 `~/.openclaw`。

### 2. 安装完成后立即验证

```bash
bash bin/validate.sh --dir ~/.openclaw
openclaw config validate
```

通过标准：
- `validate.sh` 显示 11 个 agent 文件完整
- `openclaw config validate` 返回 `Config valid`

### 3. 启动网关

```bash
openclaw gateway run
```

另开一个终端检查：

```bash
openclaw gateway health
```

### 4. 查看运行状态

```bash
# imperial 主题示例
python3 ~/.openclaw/workspace-taizi/scripts/health_dashboard.py
```

如果你希望自动识别当前主题的路由 agent，可以直接运行：

```bash
ROUTER_ID=$(python3 - <<'PY'
import json
from pathlib import Path

config = json.loads((Path.home() / ".openclaw" / "openclaw.json").read_text())
agents = config.get("agents", {}).get("list", [])
router_id = next((a["id"] for a in agents if a.get("default")), agents[0]["id"] if agents else "taizi")
print(router_id)
PY
)
python3 ~/.openclaw/workspace-${ROUTER_ID}/scripts/health_dashboard.py
```

如果你使用的是 `startup` 或 `corporate` 主题，请把 `workspace-taizi` 替换成对应路由 agent 的 workspace，例如：
- `startup` → `workspace-secretary`
- `corporate` → `workspace-assistant`

示例输出：

```text
======================================================================
  Health Dashboard  |  2026-03-14 07:34:00
======================================================================

--- Agent 状态 ---
  Agent        名称         模型                       工作区活动        会话活动
  assistant    EA         openai-codex/gpt-5.4     8分钟前         无记录
  vp_strategy  VP Strategy openai-codex/gpt-5.4     8分钟前         无记录
  ...

--- 活跃任务 (0) ---
  无活跃任务
```

如果你想看到“每个 Agent 正在干什么、最近怎么接力”，可以打开协同态势看板：

```bash
python3 ~/.openclaw/workspace-${ROUTER_ID}/scripts/collaboration_dashboard.py
python3 ~/.openclaw/workspace-${ROUTER_ID}/scripts/collaboration_dashboard.py --serve
```

`--serve` 会启动本地实时面板，默认地址：

```text
http://127.0.0.1:18890/collaboration-dashboard.html
```

它会通过 Server-Sent Events 实时接收任务与协同变化，不再整页重载。

生成结果默认在：

```text
~/.openclaw/dashboard/collaboration-dashboard.html
~/.openclaw/dashboard/collaboration-dashboard.json
```

### 5. 首次使用建议

- 先发一条简单消息，确认路由 Agent 能正常接收并回复
- 再发一条明确任务，确认会自动建任务并流转到规划/执行链路
- 若升级过 OpenClaw，建议补跑一次 `openclaw gateway health`

## 三套主题

| 主题 | 风格 | 适合场景 |
|------|------|----------|
| `imperial` | 皇帝朝廷、三省六部 | 个人玩家、极客 |
| `corporate` | CEO → VP → Teams | 企业团队、正式场合 |
| `startup` | 老板 → PM → 全栈 | 创业公司、小团队 |

```bash
# 指定主题
bash bin/setup.sh --theme corporate
```

## 运行中切换主题

已有安装不需要重装，可以直接切换：

```bash
bash bin/switch_theme.sh --theme startup
```

如果你的 OpenClaw 不在默认目录：

```bash
bash bin/switch_theme.sh --theme corporate --dir /path/to/.openclaw
```

切换时会：
- 备份当前 `openclaw.json` 和 `.env` 到 `backups/theme-switch-*`
- 保留现有频道配置、模型配置、Gateway token 和任务前缀
- 迁移任务看板、Agent 会话目录以及 workspace 里的非模板文件
- 重新生成新主题的 `SOUL.md`、`kanban_config.json` 和 `openclaw.json`

如果你希望切换时顺便改任务前缀，可以加：

```bash
bash bin/switch_theme.sh --theme corporate --task-prefix TASK
```

## 核心特性

- **任务分级 S/A/B**：重大任务走审议流程，简单任务直达执行
- **串联/并行调度**：支持 工程→测试→部署 链式执行
- **实时看板**：全程进度可视，每个 Agent 主动上报状态
- **协同态势视图**：直接看到谁在执行、谁在等待、任务如何接力流转
- **异常升级**：阻塞自动逐级上报
- **安全加固**：secrets 环境变量化、per-agent 沙箱、工具白名单
- **多语言支持**：主题配置 `language: "en"` 自动生成英文 SOUL.md 和看板标签
- **安装验证**：`validate.sh` 一键检查所有文件/配置是否完整

## 目录结构

```
sansheng-liubu/
├── bin/
│   ├── setup.sh              # 交互式安装脚本
│   ├── switch_theme.sh       # 已安装环境切换主题
│   ├── switch_theme.py       # 主题切换与迁移逻辑
│   ├── render_templates.py   # SOUL.md / kanban_config / HEARTBEAT 渲染
│   ├── generate_config.py    # openclaw.json 生成
│   ├── theme_utils.py        # 主题 schema 校验 / 迁移辅助
│   └── validate.sh           # 安装后验证
├── templates/
│   └── scripts/              # 运行时脚本（部署到每个 workspace）
│       ├── kanban_update.py   # 看板任务管理（自动加载 kanban_config.json）
│       ├── file_lock.py       # 原子文件锁
│       ├── refresh_live_data.py
│       └── health_dashboard.py # 健康看板（自动加载 agent 列表）
├── themes/
│   ├── imperial/theme.json   # 皇帝朝廷主题
│   ├── corporate/theme.json  # 现代企业主题
│   └── startup/theme.json    # 创业团队主题
└── README.md
```

## 前置要求

- [OpenClaw](https://getopenclaw.ai) >= 2026.3.12
- Python 3.10+
- 至少一个频道（飞书/Telegram/QQ）的 Bot Token

## 自定义主题

复制任意主题 JSON 修改即可：

```bash
cp themes/imperial/theme.json themes/my-team/theme.json
# 编辑 agent_id、title、description 等
bash bin/setup.sh --theme my-team
```

## License

MIT

## Changelog

See [CHANGELOG.md](./CHANGELOG.md) for version upgrade records.
