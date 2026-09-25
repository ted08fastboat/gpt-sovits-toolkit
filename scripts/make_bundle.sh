#!/bin/bash
# 打离线整合包：GPT-SoVITS 完整环境 + 桌面包 + 安装器 → 桌面 tar.gz
set -u
WS="$(cd "$(dirname "$0")/.." && pwd)"
NAME="GPT-SoVITS离线包-macOS-arm64"
OUT="$HOME/Desktop/$NAME.tar.gz"
TMP="$(mktemp -d)"
TMPLINK="$HOME/Desktop/$NAME"

install -m 755 "$WS/scripts/安装.command" "$TMP/安装.command"
install -m 644 "$WS/scripts/安装说明.txt" "$TMP/安装说明.txt"

echo "== 打包内容 =="
du -sh "$HOME/GPT-SoVITS" "$HOME/Desktop/GPT-SoVITS一键克隆"
echo "== 输出: $OUT =="

rm -f "$OUT"
tar -v -czf "$OUT" \
  --exclude='GPT-SoVITS/user_weights' \
  --exclude='GPT-SoVITS/__pycache__' \
  --exclude='*/__pycache__' \
  --exclude='GPT-SoVITS/TEMP' \
  --exclude='GPT-SoVITS/webui.log' \
  --exclude='GPT-SoVITS/install*.log' \
  --exclude='GPT-SoVITS/test/out-verify' \
  --exclude='.DS_Store' \
  -C "$HOME" GPT-SoVITS \
  -C "$HOME/Desktop" GPT-SoVITS一键克隆 \
  -C "$TMP" 安装.command 安装说明.txt 2>/tmp/bundle_tar.log

rc=$?
echo "tar exit=$rc"
ls -lh "$OUT" 2>/dev/null
echo "== 校验 =="
shasum -a 256 "$OUT" | tee "$HOME/Desktop/$NAME.sha256.txt"
rm -rf "$TMP"
