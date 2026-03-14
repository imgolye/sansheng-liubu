#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR=""
INSTALL_DEPS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir)
      PROJECT_DIR="$2"
      shift 2
      ;;
    --install)
      INSTALL_DEPS=1
      shift
      ;;
    --help)
      echo "用法: bash build_frontend.sh [--project-dir /path/to/repo] [--install]"
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(dirname "$SCRIPT_DIR")}"
FRONTEND_DIR="$PROJECT_DIR/frontend"

if [[ ! -d "$FRONTEND_DIR" || ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "[!] 未找到 frontend/package.json，跳过前端构建。"
  exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[!] 未检测到 npm，暂时无法构建前端。你仍然可以继续使用 /legacy。"
  exit 0
fi

cd "$FRONTEND_DIR"

if [[ ! -d node_modules ]]; then
  if [[ "$INSTALL_DEPS" -eq 1 ]]; then
    echo "[*] frontend/node_modules 不存在，开始安装依赖..."
    npm install
  else
    echo "[!] frontend/node_modules 不存在，跳过构建。"
    echo "    如需启用新的前后端分离界面，请运行: cd $FRONTEND_DIR && npm install && npm run build"
    exit 0
  fi
fi

echo "[*] 构建前端..."
npm run build
echo "[✓] 前端构建完成: $FRONTEND_DIR/dist"
