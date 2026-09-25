#!/bin/bash
# 容器入口：准备权重目录 → 按需下载模型 → 启动 UI
set -e

REPO_ROOT="${REPO_ROOT:-/repo}"
PORT="${PORT:-8000}"

echo "=============================================="
echo "  声音工坊 · GPT-SoVITS 语音克隆 UI"
echo "  仓库目录: $REPO_ROOT"
echo "  监听端口: $PORT"
echo "=============================================="

# 把 /data/weights/* 里的权重目录链接进仓库（GPT_weights_v2Pro / SoVITS_weights_v2Pro ...）
if [ -d /data/weights ]; then
  for d in /data/weights/*/; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    case "$name" in
      GPT_weights*|SoVITS_weights*)
        target="$REPO_ROOT/$name"
        if [ -d "$target" ] && [ ! -L "$target" ]; then
          if [ -z "$(ls -A "$target" 2>/dev/null)" ]; then
            rmdir "$target" 2>/dev/null || true
          else
            echo "  ⚠️  $name 在镜像里已存在且非空，跳过链接（用镜像内的权重）"
            continue
          fi
        fi
        ln -sfn "$d" "$target"
        echo "  权重目录: $name -> $d"
        ;;
      *) echo "  （忽略 $name：目录名需以 GPT_weights 或 SoVITS_weights 开头）" ;;
    esac
  done
fi

# 模型缺失时自动下载（AUTO_FETCH=0 可关闭）
if [ "${AUTO_FETCH:-1}" = "1" ]; then
  python /app/voiceui/fetch_assets.py --repo "$REPO_ROOT" --only-missing || {
    echo "⚠️  模型下载未全部成功，容器仍会启动；可在日志里看到缺哪些文件。"
  }
fi

mkdir -p "$REPO_ROOT/GPT_SoVITS/pretrained_models" "$REPO_ROOT/GPT_SoVITS/text" "$REPO_ROOT/nltk_data"

exec python -m uvicorn main:app --host 0.0.0.0 --port "$PORT"
