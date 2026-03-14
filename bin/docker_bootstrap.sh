#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OPENCLAW_DIR="${OPENCLAW_DIR:-/data/openclaw}"
BOOTSTRAP_THEME="${BOOTSTRAP_THEME:-imperial}"
PORT="${PORT:-18890}"
CORS_ORIGINS="${CORS_ORIGINS:-http://127.0.0.1:5173,http://localhost:5173}"

mkdir -p "$OPENCLAW_DIR"

if [[ ! -f "$OPENCLAW_DIR/openclaw.json" ]]; then
  echo "[*] No OpenClaw state found, bootstrapping theme: $BOOTSTRAP_THEME"
  printf 'n\nn\nn\n\n\n' | bash "$PROJECT_DIR/bin/setup.sh" --dir "$OPENCLAW_DIR" --theme "$BOOTSTRAP_THEME"
fi

bash "$PROJECT_DIR/bin/sync_runtime_assets.sh" --dir "$OPENCLAW_DIR" --project-dir "$PROJECT_DIR"

ROUTER_ID="$(
  python3 - "$OPENCLAW_DIR/openclaw.json" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
agents = config.get("agents", {}).get("list", [])
router = next((item.get("id", "") for item in agents if item.get("default")), "")
if not router and agents:
    router = agents[0].get("id", "")
print(router or "taizi")
PY
)"

exec python3 "$OPENCLAW_DIR/workspace-$ROUTER_ID/scripts/collaboration_dashboard.py" \
  --dir "$OPENCLAW_DIR" \
  --serve \
  --port "$PORT" \
  --frontend-dist "$PROJECT_DIR/frontend/dist" \
  --cors-origins "$CORS_ORIGINS"
