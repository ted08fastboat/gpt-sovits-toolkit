#!/bin/bash
# 带重试地推送到 GitHub（国内网络经常抖动，单次 push 容易超时）
set -u
export PATH="$HOME/.local/bin:$PATH"
cd "/Users/zhengjiezhou/Documents/deepseek agent/gptsovits/repo" || exit 1
for i in 1 2 3 4 5 6; do
  echo "=== 第 $i 次尝试 $(date '+%H:%M:%S') ==="
  if GIT_TERMINAL_PROMPT=0 git push origin main 2>&1 | tail -3; then
    if git ls-remote origin main >/dev/null 2>&1; then
      LOCAL=$(git rev-parse HEAD)
      REMOTE=$(git ls-remote origin main 2>/dev/null | awk '{print $1}')
      if [ "$LOCAL" = "$REMOTE" ]; then
        echo "✅ 推送成功并已核对：$LOCAL"
        exit 0
      fi
      echo "  远端为 $REMOTE，本地为 $LOCAL，继续重试…"
    fi
  fi
  sleep 15
done
echo "❌ 多次重试仍失败（网络原因），本地提交已就绪，稍后手动执行：git push origin main"
exit 1
