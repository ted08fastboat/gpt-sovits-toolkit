#!/bin/bash
# GPT-SoVITS 冒烟测试：用参考音频做零样本/微调合成，验证环境可用
# 用法: smoke_test.sh [应用目录] [版本: v2Pro|v2ProPlus|v2|v4]
set -u
DEST="$HOME/GPT-SoVITS"
APP="${1:-$DEST}"
VER="${2:-v2Pro}"

if [ -x "$APP/venv/bin/python" ]; then VENVBIN="$APP/venv/bin"; else
  echo "❌ 找不到 $APP/venv/bin/python"; exit 1
fi
TDIR="$APP/test"
[ -f "$TDIR/ref.wav" ] || { echo "❌ 找不到参考音频 $TDIR/ref.wav"; exit 1; }
[ -f "$TDIR/ref.txt" ] || { echo "❌ 找不到参考文本 $TDIR/ref.txt"; exit 1; }
[ -f "$TDIR/target.txt" ] || printf '%s' "这是一句环境自检用的测试语音。" > "$TDIR/target.txt"
OUT="${3:-$TDIR/out-$VER}"

case "$VER" in
  v2Pro|v2ProPlus) GPT="$APP/GPT_SoVITS/pretrained_models/s1v3.ckpt"; SOVITS="$APP/GPT_SoVITS/pretrained_models/v2Pro/s2G$VER.pth" ;;
  v2)  GPT="$APP/GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"; SOVITS="$APP/GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth" ;;
  v4)  GPT="$APP/GPT_SoVITS/pretrained_models/s1v3.ckpt"; SOVITS="$APP/GPT_SoVITS/pretrained_models/gsv-v4-pretrained/s2Gv4.pth" ;;
  *) echo "未知版本 $VER"; exit 2 ;;
esac

export PATH="$VENVBIN:$PATH"
export PYTHONPATH="$APP:$APP/GPT_SoVITS:${PYTHONPATH:-}"
export HF_ENDPOINT="https://hf-mirror.com"
export NLTK_DATA="${NLTK_DATA:-$APP/nltk_data}"
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export PYTORCH_ENABLE_MPS_FALLBACK=1
export language=zh_CN
export version="$VER"
export gpt_path="$GPT"
export sovits_path="$SOVITS"

mkdir -p "$OUT"
cd "$APP" || exit 1
echo "== 版本=$VER =="
"$VENVBIN/python" GPT_SoVITS/inference_cli.py \
  --gpt_model "$GPT" --sovits_model "$SOVITS" \
  --ref_audio "$TDIR/ref.wav" --ref_text "$TDIR/ref.txt" \
  --ref_language 中文 --target_text "$TDIR/target.txt" --target_language 中文 \
  --output_path "$OUT"
ls -l "$OUT/output.wav" 2>/dev/null && echo "✅ 冒烟测试通过" || echo "❌ 未生成 output.wav"
