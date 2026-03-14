#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_DIR="$HOME/.openclaw"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_FRONTEND=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      OPENCLAW_DIR="$2"
      shift 2
      ;;
    --project-dir)
      PROJECT_DIR="$2"
      shift 2
      ;;
    --build-frontend)
      BUILD_FRONTEND=1
      shift
      ;;
    --help)
      echo "用法: bash sync_runtime_assets.sh [--dir ~/.openclaw] [--project-dir /path/to/sansheng-liubu] [--build-frontend]"
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      exit 1
      ;;
  esac
done

OPENCLAW_DIR="$(python3 - "$OPENCLAW_DIR" <<'PY'
import os, sys
print(os.path.abspath(os.path.expanduser(sys.argv[1])))
PY
)"
PROJECT_DIR="$(python3 - "$PROJECT_DIR" <<'PY'
import os, sys
print(os.path.abspath(os.path.expanduser(sys.argv[1])))
PY
)"

CONFIG_PATH="$OPENCLAW_DIR/openclaw.json"
TEMPLATES_DIR="$PROJECT_DIR/templates/scripts"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "[✗] 缺少配置文件: $CONFIG_PATH" >&2
  exit 1
fi

if [[ ! -d "$TEMPLATES_DIR" ]]; then
  echo "[✗] 缺少模板目录: $TEMPLATES_DIR" >&2
  exit 1
fi

echo "[*] 同步运行时资源到: $OPENCLAW_DIR"
echo "[*] 仓库目录: $PROJECT_DIR"

PYTHONPATH="$PROJECT_DIR/bin${PYTHONPATH:+:$PYTHONPATH}" python3 - "$OPENCLAW_DIR" "$PROJECT_DIR" <<'PY'
import json, sys
from pathlib import Path

from project_metadata import load_project_metadata, sanitize_openclaw_config, write_project_metadata

openclaw_dir = Path(sys.argv[1]).resolve()
project_dir = str(Path(sys.argv[2]).resolve())
config_path = openclaw_dir / "openclaw.json"
config = json.loads(config_path.read_text())
metadata = load_project_metadata(openclaw_dir, existing_config=config)
metadata["projectDir"] = project_dir
write_project_metadata(openclaw_dir, metadata)
config_path.write_text(json.dumps(sanitize_openclaw_config(config), ensure_ascii=False, indent=2) + "\n")
PY

WORKSPACES=()
while IFS= read -r workspace; do
  [[ -n "$workspace" ]] && WORKSPACES+=("$workspace")
done < <(
  python3 - "$CONFIG_PATH" <<'PY'
import json, os, sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text())
for agent in config.get("agents", {}).get("list", []):
    workspace = os.path.abspath(os.path.expanduser(agent.get("workspace", "")))
    if workspace:
        print(workspace)
PY
)

for workspace in "${WORKSPACES[@]}"; do
  mkdir -p "$workspace/scripts" "$workspace/data"
  cp "$TEMPLATES_DIR/kanban_update.py" "$workspace/scripts/"
  cp "$TEMPLATES_DIR/file_lock.py" "$workspace/scripts/"
  cp "$TEMPLATES_DIR/dashboard_store.py" "$workspace/scripts/"
  cp "$TEMPLATES_DIR/refresh_live_data.py" "$workspace/scripts/"
  cp "$TEMPLATES_DIR/health_dashboard.py" "$workspace/scripts/"
  cp "$TEMPLATES_DIR/collaboration_dashboard.py" "$workspace/scripts/"
  if [[ ! -f "$workspace/data/tasks_source.json" ]]; then
    echo '[]' > "$workspace/data/tasks_source.json"
  fi
done

if [[ "$BUILD_FRONTEND" -eq 1 && -f "$PROJECT_DIR/bin/build_frontend.sh" ]]; then
  bash "$PROJECT_DIR/bin/build_frontend.sh" --project-dir "$PROJECT_DIR"
fi

FIRST_WORKSPACE="${WORKSPACES[0]:-}"
if [[ -n "$FIRST_WORKSPACE" && -f "$FIRST_WORKSPACE/scripts/collaboration_dashboard.py" ]]; then
  python3 "$FIRST_WORKSPACE/scripts/collaboration_dashboard.py" --dir "$OPENCLAW_DIR" --quiet || true
fi

echo "[✓] 运行时脚本同步完成"
