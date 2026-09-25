#!/bin/bash
# 从 hf-mirror.com 下载 GPT-SoVITS 中文推理所需预训练模型（可断点续传）
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$ROOT/models"          # 暂存目录，最终会被复制到 GPT_SoVITS/pretrained_models
HF="https://hf-mirror.com"
mkdir -p "$STAGE"

FILES="$ROOT/scripts/model_files.txt"

dl() {
  local rel="$1"
  local out="$STAGE/$rel"
  mkdir -p "$(dirname "$out")"
  # 已完整则跳过（curl -C - 会返回 416/继续）
  if [ -f "$out" ] && [ ! -f "$out.part" ]; then
    echo "SKIP(exists) $rel"
    return 0
  fi
  # 文件名里的 = 需要 URL 编码
  local enc
  enc=$(printf '%s' "$rel" | sed 's/=/\%3D/g')
  for attempt in 1 2 3 4 5; do
    echo "GET($attempt) $rel"
    if curl -sSL --fail --retry 2 --retry-delay 3 -m 3600 -C - \
        -o "$out.part" "$HF/lj1995/GPT-SoVITS/resolve/main/$enc"; then
      mv -f "$out.part" "$out"
      echo "OK $rel ($(du -h "$out" | cut -f1))"
      return 0
    fi
    sleep 3
  done
  echo "FAIL $rel"
  return 1
}
export -f dl
export STAGE HF

grep -v '^\s*$' "$FILES" | xargs -P 3 -I{} bash -c 'dl "$@"' _ {}

echo "=== download summary ==="
du -sh "$STAGE"
