#!/bin/bash
# 停止本机运行的声音工坊（uvicorn main:app）
set -u
PATTERN="uvicorn main:app"
PIDS="$(pgrep -f "$PATTERN" 2>/dev/null || true)"
if [ -z "$PIDS" ]; then
  echo "没有在运行的声音工坊实例"
  exit 0
fi
echo "正在停止: $PIDS"
kill $PIDS 2>/dev/null || true
sleep 2
LEFT="$(pgrep -f "$PATTERN" 2>/dev/null || true)"
if [ -n "$LEFT" ]; then
  echo "强制结束: $LEFT"
  kill -9 $LEFT 2>/dev/null || true
fi
echo "已停止"
