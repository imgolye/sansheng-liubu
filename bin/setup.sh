#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  三省六部 · OpenClaw 多 Agent 初始化工具
#  用法: bash setup.sh [--theme imperial|corporate|startup]
# ============================================================

VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEMPLATES_DIR="$PROJECT_DIR/templates"
THEMES_DIR="$PROJECT_DIR/themes"

# ---------- 默认值 ----------
THEME="imperial"
OPENCLAW_DIR="$HOME/.openclaw"
TASK_PREFIX="JJC"

# ---------- 颜色 ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }
ask()   { echo -en "${CYAN}[?]${NC} $1 "; }

# ---------- 参数解析 ----------
while [[ $# -gt 0 ]]; do
  case $1 in
    --theme)  THEME="$2"; shift 2 ;;
    --dir)    OPENCLAW_DIR="$2"; shift 2 ;;
    --prefix) TASK_PREFIX="$2"; shift 2 ;;
    --help)   echo "用法: setup.sh [--theme imperial|corporate|startup] [--dir ~/.openclaw] [--prefix JJC]"; exit 0 ;;
    *)        warn "未知参数: $1"; shift ;;
  esac
done

# ---------- 前置检查 ----------
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  三省六部 · 多 Agent 系统 v${VERSION}        ║"
echo "║  Multi-Agent Orchestration for OpenClaw  ║"
echo "╚══════════════════════════════════════════╝"
echo ""

if ! command -v openclaw &>/dev/null; then
  error "未检测到 openclaw CLI。请先安装: npm install -g openclaw"
fi

OPENCLAW_VERSION=$(openclaw --version 2>/dev/null | head -1 || echo "unknown")
info "OpenClaw 版本: $OPENCLAW_VERSION"
info "主题: $THEME"
info "安装目录: $OPENCLAW_DIR"
echo ""

# ---------- 加载主题 ----------
THEME_FILE="$THEMES_DIR/$THEME/theme.json"
if [[ ! -f "$THEME_FILE" ]]; then
  error "主题文件不存在: $THEME_FILE (可选: imperial, corporate, startup)"
fi

# 用 python3 解析主题 JSON
eval "$(python3 -c "
import json, sys
with open('$THEME_FILE') as f:
    t = json.load(f)
roles = t['roles']
print(f'ROLE_ROUTER=\"{roles[\"router\"][\"title\"]}\"')
print(f'ROLE_PLANNER=\"{roles[\"planner\"][\"title\"]}\"')
print(f'ROLE_REVIEWER=\"{roles[\"reviewer\"][\"title\"]}\"')
print(f'ROLE_DISPATCHER=\"{roles[\"dispatcher\"][\"title\"]}\"')
print(f'ROLE_OWNER=\"{t[\"owner_title\"]}\"')
print(f'AGENT_ROUTER=\"{roles[\"router\"][\"agent_id\"]}\"')
print(f'AGENT_PLANNER=\"{roles[\"planner\"][\"agent_id\"]}\"')
print(f'AGENT_REVIEWER=\"{roles[\"reviewer\"][\"agent_id\"]}\"')
print(f'AGENT_DISPATCHER=\"{roles[\"dispatcher\"][\"agent_id\"]}\"')
# departments
deps = roles.get('departments', {})
dep_ids = []
dep_titles = []
for k, v in deps.items():
    dep_ids.append(v['agent_id'])
    dep_titles.append(v['title'])
print(f'DEP_IDS=({\" \".join(dep_ids)})')
print(f'DEP_TITLES=({\" \".join([repr(x) for x in dep_titles])})')
")"

ALL_AGENTS=("$AGENT_ROUTER" "$AGENT_PLANNER" "$AGENT_REVIEWER" "$AGENT_DISPATCHER" "${DEP_IDS[@]}")

# ---------- 交互式配置 ----------
echo "=== 频道配置 ==="

ask "启用飞书? (y/n) [y]:"
read -r ENABLE_FEISHU; ENABLE_FEISHU="${ENABLE_FEISHU:-y}"

ask "启用 Telegram? (y/n) [n]:"
read -r ENABLE_TG; ENABLE_TG="${ENABLE_TG:-n}"

ask "启用 QQ 机器人? (y/n) [n]:"
read -r ENABLE_QQ; ENABLE_QQ="${ENABLE_QQ:-n}"

FEISHU_APP_ID="" FEISHU_APP_SECRET=""
TG_BOT_TOKEN=""
QQ_APP_ID="" QQ_CLIENT_SECRET=""

if [[ "$ENABLE_FEISHU" == "y" ]]; then
  ask "飞书 App ID:"; read -r FEISHU_APP_ID
  ask "飞书 App Secret:"; read -rs FEISHU_APP_SECRET; echo ""
fi

if [[ "$ENABLE_TG" == "y" ]]; then
  ask "Telegram Bot Token:"; read -rs TG_BOT_TOKEN; echo ""
  ask "Telegram 代理 (留空跳过):"; read -r TG_PROXY
fi

if [[ "$ENABLE_QQ" == "y" ]]; then
  ask "QQ Bot App ID:"; read -r QQ_APP_ID
  ask "QQ Bot Client Secret:"; read -rs QQ_CLIENT_SECRET; echo ""
fi

echo ""
echo "=== 模型配置 ==="
ask "主模型 (如 openai-codex/gpt-5.4) [openai-codex/gpt-5.4]:"
read -r PRIMARY_MODEL; PRIMARY_MODEL="${PRIMARY_MODEL:-openai-codex/gpt-5.4}"

ask "轻量模型 (用于审议/简报) [zai/glm-5]:"
read -r LIGHT_MODEL; LIGHT_MODEL="${LIGHT_MODEL:-zai/glm-5}"

echo ""
info "开始安装..."

# ---------- 创建目录结构 ----------
mkdir -p "$OPENCLAW_DIR"/{skills,logs,credentials}
chmod 700 "$OPENCLAW_DIR" "$OPENCLAW_DIR/credentials"

for agent in "${ALL_AGENTS[@]}"; do
  mkdir -p "$OPENCLAW_DIR/workspace-$agent"/{scripts,data,shared-context,skills}
  mkdir -p "$OPENCLAW_DIR/agents/$agent/agent"
done

info "目录结构已创建 (${#ALL_AGENTS[@]} 个 agent)"

# ---------- 复制核心脚本 ----------
for agent in "${ALL_AGENTS[@]}"; do
  cp "$TEMPLATES_DIR/scripts/kanban_update.py" "$OPENCLAW_DIR/workspace-$agent/scripts/"
  cp "$TEMPLATES_DIR/scripts/file_lock.py" "$OPENCLAW_DIR/workspace-$agent/scripts/"
  cp "$TEMPLATES_DIR/scripts/refresh_live_data.py" "$OPENCLAW_DIR/workspace-$agent/scripts/"
done
info "看板脚本已部署到所有 workspace"

# ---------- 复制共享上下文 ----------
for agent in "${ALL_AGENTS[@]}"; do
  cp "$TEMPLATES_DIR/shared-context/ORG-STRUCTURE.md" "$OPENCLAW_DIR/workspace-$agent/shared-context/"
done
info "共享上下文已同步"

# ---------- 生成 SOUL.md (使用模板引擎) ----------
python3 "$PROJECT_DIR/bin/render_templates.py" \
  --theme "$THEME_FILE" \
  --openclaw-dir "$OPENCLAW_DIR" \
  --primary-model "$PRIMARY_MODEL" \
  --light-model "$LIGHT_MODEL" \
  --task-prefix "$TASK_PREFIX"
info "SOUL.md / AGENTS.md 已生成"

# ---------- 生成 openclaw.json ----------
python3 "$PROJECT_DIR/bin/generate_config.py" \
  --theme "$THEME_FILE" \
  --openclaw-dir "$OPENCLAW_DIR" \
  --primary-model "$PRIMARY_MODEL" \
  --light-model "$LIGHT_MODEL" \
  --feishu-app-id "$FEISHU_APP_ID" \
  --feishu-app-secret "$FEISHU_APP_SECRET" \
  --tg-bot-token "$TG_BOT_TOKEN" \
  --tg-proxy "${TG_PROXY:-}" \
  --qq-app-id "$QQ_APP_ID" \
  --qq-client-secret "$QQ_CLIENT_SECRET" \
  --task-prefix "$TASK_PREFIX"
info "openclaw.json 已生成"

# ---------- 写入 .env ----------
cat > "$OPENCLAW_DIR/.env" << ENVEOF
# 三省六部 Secrets — 请勿提交版本控制
FEISHU_APP_SECRET=${FEISHU_APP_SECRET}
TELEGRAM_BOT_TOKEN=${TG_BOT_TOKEN}
QQBOT_CLIENT_SECRET=${QQ_CLIENT_SECRET}
GATEWAY_AUTH_TOKEN=$(openssl rand -hex 24)
ENVEOF
chmod 600 "$OPENCLAW_DIR/.env"
info "Secrets 已写入 .env (权限 600)"

# ---------- 初始化看板数据 ----------
for agent in "${ALL_AGENTS[@]}"; do
  echo '[]' > "$OPENCLAW_DIR/workspace-$agent/data/tasks_source.json"
done
info "看板数据已初始化"

# ---------- 权限加固 ----------
chmod 600 "$OPENCLAW_DIR/openclaw.json"
info "文件权限已加固"

# ---------- 验证 ----------
echo ""
echo "=== 安装完成 ==="
info "Agent 数量: ${#ALL_AGENTS[@]}"
info "主题: $THEME"
info "配置文件: $OPENCLAW_DIR/openclaw.json"
echo ""
echo "下一步:"
echo "  1. 启动网关:  openclaw gateway run"
echo "  2. 健康检查:  openclaw gateway health"
echo "  3. 安全审计:  openclaw security audit"
echo ""
echo "发送消息给机器人即可开始使用！"
