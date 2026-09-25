#!/bin/bash
# 双击启动「声音工坊」本地 UI（后台运行 + 自动打开浏览器）
UI="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8000}"
LOG="/tmp/voiceui.log"

if curl -s -o /dev/null -m 2 "http://127.0.0.1:$PORT/api/state"; then
  echo "声音工坊已在运行：http://127.0.0.1:$PORT"
  open "http://127.0.0.1:$PORT"
  read -r -p "按回车关闭本窗口…" _
  exit 0
fi

cd "$UI" || exit 1
echo "正在启动声音工坊…（首次会加载模型，约 1 分钟）"
nohup ./run_local.sh > "$LOG" 2>&1 &

for i in $(seq 1 90); do
  sleep 1
  if curl -s -o /dev/null -m 2 "http://127.0.0.1:$PORT/api/state"; then break; fi
done

if curl -s -o /dev/null -m 2 "http://127.0.0.1:$PORT/api/state"; then
  echo "✅ 已启动：http://127.0.0.1:$PORT"
  open "http://127.0.0.1:$PORT"
else
  echo "❌ 启动失败，日志：$LOG"
  tail -20 "$LOG"
fi
echo
echo "停止服务：pkill -f 'uvicorn main:app'"
read -r -p "按回车关闭本窗口（服务会继续在后台运行）…" _
