#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  三省六部 · 安装验证脚本
#  用法: bash validate.sh [--dir ~/.openclaw] [~/.openclaw]
# ============================================================

OPENCLAW_DIR="$HOME/.openclaw"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      OPENCLAW_DIR="$2"
      shift 2
      ;;
    --help)
      echo "用法: bash validate.sh [--dir ~/.openclaw] [~/.openclaw]"
      exit 0
      ;;
    *)
      OPENCLAW_DIR="$1"
      shift
      ;;
  esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; ERRORS=$((ERRORS + 1)); }
summary_fail() { echo -e "${RED}[✗]${NC} $*"; }

ERRORS=0
WARNINGS=0

echo ""
echo "=== 三省六部 · 安装验证 ==="
echo "检查目录: $OPENCLAW_DIR"
echo ""

# 1. openclaw.json
echo "--- 配置文件 ---"
if [[ -f "$OPENCLAW_DIR/openclaw.json" ]]; then
  ok "openclaw.json 存在"
  AGENT_COUNT=$(python3 -c "import json; d=json.load(open('$OPENCLAW_DIR/openclaw.json')); print(len(d.get('agents',{}).get('list',[])))" 2>/dev/null || echo "0")
  if [[ "$AGENT_COUNT" -ge 10 ]]; then
    ok "Agent 数量: $AGENT_COUNT"
  else
    fail "Agent 数量过少: $AGENT_COUNT (预期 ≥ 10)"
  fi
else
  fail "openclaw.json 不存在"
fi

# 2. .env
if [[ -f "$OPENCLAW_DIR/.env" ]]; then
  PERMS=$(stat -f "%Lp" "$OPENCLAW_DIR/.env" 2>/dev/null || stat -c "%a" "$OPENCLAW_DIR/.env" 2>/dev/null || echo "?")
  if [[ "$PERMS" == "600" ]]; then
    ok ".env 权限正确 (600)"
  else
    warn ".env 权限: $PERMS (建议 600)"; WARNINGS=$((WARNINGS + 1))
  fi
else
  warn ".env 不存在 (可能无 secrets 配置)"; WARNINGS=$((WARNINGS + 1))
fi

# 3-7. 按 openclaw.json 中的 agent 清单逐项核验
echo ""
echo "--- Agent 文件完整性 ---"

AGENT_ROWS=()
if [[ -f "$OPENCLAW_DIR/openclaw.json" ]]; then
  while IFS= read -r row; do
    AGENT_ROWS+=("$row")
  done < <(
    python3 - <<'PY' "$OPENCLAW_DIR/openclaw.json"
import json, sys
with open(sys.argv[1]) as f:
    config = json.load(f)
for agent in config.get("agents", {}).get("list", []):
    print("\t".join([
        agent["id"],
        agent.get("workspace", ""),
        agent.get("agentDir", ""),
    ]))
PY
  )
fi

SOUL_COUNT=0
ORG_COUNT=0
KANBAN_CFG_COUNT=0
SCRIPT_OK=0
TASKS_COUNT=0

for row in "${AGENT_ROWS[@]}"; do
  IFS=$'\t' read -r agent workspace agentdir <<< "$row"

  if [[ -z "$workspace" || ! -d "$workspace" ]]; then
    fail "缺少 workspace 目录: $agent (${workspace:-未配置})"
    continue
  fi
  if [[ -z "$agentdir" || ! -d "$agentdir" ]]; then
    fail "缺少 agentDir 目录: $agent (${agentdir:-未配置})"
  fi

  if [[ -f "$workspace/SOUL.md" ]]; then
    SOUL_COUNT=$((SOUL_COUNT + 1))
  else
    fail "缺少 SOUL.md: $agent"
  fi

  if [[ -f "$workspace/shared-context/ORG-STRUCTURE.md" ]]; then
    ORG_COUNT=$((ORG_COUNT + 1))
  else
    fail "缺少 ORG-STRUCTURE.md: $agent"
  fi

  if [[ -f "$workspace/data/kanban_config.json" ]]; then
    KANBAN_CFG_COUNT=$((KANBAN_CFG_COUNT + 1))
  else
    fail "缺少 kanban_config.json: $agent"
  fi

  if [[ -f "$workspace/scripts/kanban_update.py" ]] && [[ -f "$workspace/scripts/file_lock.py" ]] && [[ -f "$workspace/scripts/refresh_live_data.py" ]] && [[ -f "$workspace/scripts/health_dashboard.py" ]]; then
    SCRIPT_OK=$((SCRIPT_OK + 1))
  else
    fail "缺少看板脚本: $agent"
  fi

  if [[ -f "$workspace/data/tasks_source.json" ]]; then
    TASKS_COUNT=$((TASKS_COUNT + 1))
  else
    fail "缺少 tasks_source.json: $agent"
  fi
done

ok "SOUL.md: $SOUL_COUNT 个"
ok "ORG-STRUCTURE.md: $ORG_COUNT 个"
ok "kanban_config.json: $KANBAN_CFG_COUNT 个"
ok "看板脚本: $SCRIPT_OK 个 workspace 已部署"
ok "tasks_source.json: $TASKS_COUNT 个"

# Summary
echo ""
echo "=== 验证结果 ==="
if [[ $ERRORS -eq 0 ]]; then
  ok "全部通过 (${WARNINGS} 个警告)"
else
  summary_fail "${ERRORS} 个错误, ${WARNINGS} 个警告"
fi
echo ""
exit $ERRORS
