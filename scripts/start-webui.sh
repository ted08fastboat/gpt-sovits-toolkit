#!/bin/bash
# GPT-SoVITS WebUI 启动脚本 (macOS arm64, CPU 推理)
# 用法: ./start-webui.sh        默认中文界面
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"

export PATH="$ROOT/venv/bin:$PATH"          # 提供 ffmpeg
export PYTHONPATH="$ROOT:$ROOT/GPT_SoVITS"
export HF_ENDPOINT="https://hf-mirror.com"  # 国内镜像，防自动下载卡住
export NLTK_DATA="$ROOT/nltk_data"
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1   # torch 2.6 加载旧权重兼容
export PYTORCH_ENABLE_MPS_FALLBACK=1
export GRADIO_ANALYTICS_ENABLED=False
export language="${1:-zh_CN}"

echo "=============================================="
echo " GPT-SoVITS WebUI"
echo " 地址: http://127.0.0.1:9874"
echo " 首次加载模型约 1-2 分钟，请耐心等待"
echo " 停止服务: 在此终端按 Control-C"
echo "=============================================="
exec python -I webui.py "$language"
