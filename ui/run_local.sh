#!/bin/bash
# 声音工坊 · 本地启动（macOS 原生，不使用 Docker）
# 默认复用已有环境 ~/GPT-SoVITS 与桌面「GPT-SoVITS一键克隆」里的参考音色/输出目录
set -u
UI_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="${DEST:-$HOME/GPT-SoVITS}"
PKG="$HOME/Desktop/GPT-SoVITS一键克隆"

export REPO_ROOT="$DEST"
# 默认用安装目录下的参考音/输出（不要用 ~/Desktop、~/Downloads、~/Documents：
# 这些是 macOS 隐私保护目录，后台进程可能读不到）
export REF_DIR="${REF_DIR:-$DEST/参考音频}"
export OUT_DIR="${OUT_DIR:-$DEST/输出音频}"
export PATH="$DEST/venv/bin:$PATH"
export PYTHONPATH="$DEST:$DEST/GPT_SoVITS"
export HF_ENDPOINT="https://hf-mirror.com"
export NLTK_DATA="$DEST/nltk_data"
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export PYTORCH_ENABLE_MPS_FALLBACK=1
export PRELOAD="${PRELOAD:-1}"
export PORT="${PORT:-8000}"

cd "$UI_DIR/app" || exit 1
echo "============================================================"
echo "  声音工坊 · GPT-SoVITS 本地 UI"
echo "  地址: http://127.0.0.1:$PORT    （关闭本窗口即停止）"
echo "  参考音色目录: $REF_DIR"
echo "  输出目录    : $OUT_DIR"
echo "============================================================"
exec "$DEST/venv/bin/python" -m uvicorn main:app --host 127.0.0.1 --port "$PORT"
