#!/bin/bash
# DrumAI Studio 一键启动（macOS）
# 双击运行：启动后端（127.0.0.1:8000）与前端（127.0.0.1:5173），随后打开浏览器。
# 停止：在两个终端窗口里各按 Ctrl+C，或直接关掉窗口。
# 首次使用前需先按 README 的 Development 一节装好后端与前端依赖，
# 并给本文件一次执行权限：chmod +x start.command
set -u
cd "$(dirname "$0")"

if [ ! -d "backend/.venv" ]; then
  echo "缺少 backend/.venv：请先按 README 的 Development 一节装好后端，再双击本文件。"
  read -p "按回车退出。"
  exit 1
fi
if [ ! -d "frontend/node_modules" ]; then
  echo "缺少 frontend/node_modules：请先在 frontend 里跑一次 npm install，再双击本文件。"
  read -p "按回车退出。"
  exit 1
fi

# 释放上次残留的服务占用的端口（只动 8000 / 5173）
kill $(lsof -ti:8000) 2>/dev/null || true
kill $(lsof -ti:5173) 2>/dev/null || true
sleep 1

ROOT="$(pwd)"
osascript -e "tell application \"Terminal\" to do script \"cd '$ROOT/backend' && source .venv/bin/activate && exec uvicorn app.main:app --reload --host 127.0.0.1 --port 8000\""
osascript -e "tell application \"Terminal\" to do script \"cd '$ROOT/frontend' && exec npm run dev\""

echo "正在等前端起来…"
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null http://127.0.0.1:5173/; then
    break
  fi
  sleep 1
done
open http://127.0.0.1:5173/
echo "已打开 http://127.0.0.1:5173/（后端与前端各在一个终端窗口里，关掉窗口即停止）"
