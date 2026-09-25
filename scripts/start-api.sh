#!/bin/bash
# GPT-SoVITS HTTP API 启动脚本 (api_v2, 默认 127.0.0.1:9880)
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"

export PATH="$ROOT/venv/bin:$PATH"
export PYTHONPATH="$ROOT:$ROOT/GPT_SoVITS"
export HF_ENDPOINT="https://hf-mirror.com"
export NLTK_DATA="$ROOT/nltk_data"
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

echo "API 文档: http://127.0.0.1:9880/docs"
exec python -I api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml
