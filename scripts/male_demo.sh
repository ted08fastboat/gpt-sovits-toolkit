#!/bin/bash
# 男声方案对比实验：同一句台词，分别用「老母狮微调权重」与「官方 v2ProPlus 底模」
# 配上系统内置男声参考音频（Rocko / Reed），输出到桌面「男声试听」文件夹
set -u
WS="/Users/zhengjiezhou/Documents/deepseek agent/gptsovits"
DEST="$HOME/GPT-SoVITS"
OUT="$HOME/Desktop/GPT-SoVITS一键克隆/男声试听"
VOICES="$WS/test/voices"
LINES="$WS/test/male_lines.txt"
REF_TXT="$WS/test/male_ref.txt"
mkdir -p "$OUT"

printf '%s\n' "老牧师的许英博不要玩原神了" "大家好，我是新来的配音员，今天给大家讲一个有趣的故事。" > "$LINES"
printf '%s' "各位听众朋友大家好，欢迎收听今天的科技新闻节目。" > "$REF_TXT"

run_pair() { # $1=标签 $2=gpt $3=sovits $4=参考音频 $5=版本env
  local label="$1" gpt="$2" sovits="$3" ref="$4" ver="$5"
  echo "=== $label ==="
  echo "    gpt=$gpt"
  echo "    sovits=$sovits"
  echo "    ref=$(basename "$ref")"
  ( cd "$DEST" && env PATH="$DEST/venv/bin:$PATH" PYTHONPATH="$DEST:$DEST/GPT_SoVITS" \
      HF_ENDPOINT="https://hf-mirror.com" NLTK_DATA="$DEST/nltk_data" \
      TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 PYTORCH_ENABLE_MPS_FALLBACK=1 \
      language=zh_CN version="$ver" gpt_path="$gpt" sovits_path="$sovits" \
      "$DEST/venv/bin/python" "$DEST/tts_clone.py" \
        --batch-file "$LINES" --out-dir "$OUT" --ref-wav "$ref" --ref-text-file "$REF_TXT" \
        --ref-lang 中文 --text-lang 中文 --prefix "$label" 2>&1 ) \
    | grep -E "✅|\[[0-9]+/[0-9]+\]|完成|Traceback|Error" || true
}

LAOMUSHI_GPT="$DEST/GPT_weights_v2Pro/laomushi-e20.ckpt"
LAOMUSHI_SOVITS="$DEST/SoVITS_weights_v2Pro/laomushi_v2_e16.pth"
BASE_GPT="$DEST/GPT_SoVITS/pretrained_models/s1v3.ckpt"
BASE_SOVITS="$DEST/GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth"

run_pair "老母狮_男声Rocko"    "$LAOMUSHI_GPT" "$LAOMUSHI_SOVITS" "$VOICES/Rocko_中文_中国大陆.wav" v2Pro
run_pair "底模_男声Rocko"      "$BASE_GPT"     "$BASE_SOVITS"     "$VOICES/Rocko_中文_中国大陆.wav" v2ProPlus
run_pair "底模_男声Reed"       "$BASE_GPT"     "$BASE_SOVITS"     "$VOICES/Reed_中文_中国大陆.wav"  v2ProPlus

echo
echo "=== 产物 ==="
ls -1 "$OUT"/*.wav 2>/dev/null | sed "s|.*/||"
