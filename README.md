# 三省六部 — OpenClaw 多 Agent 编排系统

[![Release](https://img.shields.io/github/v/release/imgolye/sansheng-liubu?label=release)](https://github.com/imgolye/sansheng-liubu/releases/latest)

一键部署 11 个协作 AI Agent，模拟组织架构处理复杂任务。

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
1. 选择主题（皇帝朝廷 / 现代企业 / 创业团队）
2. 配置频道（飞书 / Telegram / QQ）
3. 选择模型

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

## 核心特性

- **任务分级 S/A/B**：重大任务走审议流程，简单任务直达执行
- **串联/并行调度**：支持 工程→测试→部署 链式执行
- **实时看板**：全程进度可视，每个 Agent 主动上报状态
- **异常升级**：阻塞自动逐级上报
- **安全加固**：secrets 环境变量化、per-agent 沙箱、工具白名单
- **多语言支持**：主题配置 `language: "en"` 自动生成英文 SOUL.md 和看板标签
- **安装验证**：`validate.sh` 一键检查所有文件/配置是否完整

## 目录结构

```
sansheng-liubu/
├── bin/
│   ├── setup.sh              # 交互式安装脚本
│   ├── render_templates.py   # SOUL.md / kanban_config / HEARTBEAT 渲染
│   ├── generate_config.py    # openclaw.json 生成
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
