#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  三省六部 · 安装验证脚本
#  用法: bash validate.sh [--dir ~/.openclaw]
# ============================================================

OPENCLAW_DIR="${1:-$HOME/.openclaw}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; ERRORS=$((ERRORS + 1)); }

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

# 3. SOUL.md for all workspaces
echo ""
echo "--- SOUL.md ---"
SOUL_COUNT=0
SOUL_MISSING=0
for ws in "$OPENCLAW_DIR"/workspace-*/; do
  agent=$(basename "$ws" | sed 's/workspace-//')
  if [[ -f "$ws/SOUL.md" ]]; then
    SOUL_COUNT=$((SOUL_COUNT + 1))
  else
    fail "缺少 SOUL.md: $agent"
    SOUL_MISSING=$((SOUL_MISSING + 1))
  fi
done
ok "SOUL.md: $SOUL_COUNT 个 (缺失 $SOUL_MISSING 个)"

# 4. ORG-STRUCTURE.md
echo ""
echo "--- 共享上下文 ---"
ORG_COUNT=0
for ws in "$OPENCLAW_DIR"/workspace-*/; do
  [[ -f "$ws/shared-context/ORG-STRUCTURE.md" ]] && ORG_COUNT=$((ORG_COUNT + 1))
done
ok "ORG-STRUCTURE.md: $ORG_COUNT 个"

# 5. kanban_config.json
KANBAN_CFG_COUNT=0
for ws in "$OPENCLAW_DIR"/workspace-*/; do
  [[ -f "$ws/data/kanban_config.json" ]] && KANBAN_CFG_COUNT=$((KANBAN_CFG_COUNT + 1))
done
ok "kanban_config.json: $KANBAN_CFG_COUNT 个"

# 6. Scripts
echo ""
echo "--- 脚本 ---"
SCRIPT_OK=0
for ws in "$OPENCLAW_DIR"/workspace-*/; do
  if [[ -f "$ws/scripts/kanban_update.py" ]] && [[ -f "$ws/scripts/file_lock.py" ]]; then
    SCRIPT_OK=$((SCRIPT_OK + 1))
  fi
done
ok "看板脚本: $SCRIPT_OK 个 workspace 已部署"

# 7. tasks_source.json
echo ""
echo "--- 看板数据 ---"
TASKS_COUNT=0
for ws in "$OPENCLAW_DIR"/workspace-*/; do
  [[ -f "$ws/data/tasks_source.json" ]] && TASKS_COUNT=$((TASKS_COUNT + 1))
done
ok "tasks_source.json: $TASKS_COUNT 个"

# Summary
echo ""
echo "=== 验证结果 ==="
if [[ $ERRORS -eq 0 ]]; then
  ok "全部通过 (${WARNINGS} 个警告)"
else
  fail "${ERRORS} 个错误, ${WARNINGS} 个警告"
fi
echo ""
exit $ERRORS
