#!/bin/bash
# 用「老母狮」微调权重做克隆合成（合成引擎，被桌面快捷方式调用）
# 用法:
#   say_laomushi.sh <台词文本文件> [输出目录] [参考音频] [参考文本文件]
#   say_laomushi.sh --batch <台词文件(每行一句)> [输出目录] [参考音频] [参考文本文件]
# 环境变量:
#   PREFIX   输出文件名前缀（默认 clone）
#   VARIANTS 变体数量，仅单条模式（默认 2；批量模式固定 1）
set -u
DEST="$HOME/GPT-SoVITS"
MODE="single"
if [ "${1:-}" = "--batch" ]; then MODE="batch"; shift; fi
TXT="${1:?用法: say_laomushi.sh [--batch] <台词文本文件> [输出目录] [参考音频] [参考文本文件]}"
OUT="${2:-$DEST/output}"
REF_WAV="${3:-}"
REF_TXT="${4:-}"

[ -n "$REF_WAV" ] || { for c in "$DEST/my_voice/ref.wav" "$DEST/test/ref.wav"; do [ -f "$c" ] && REF_WAV="$c" && break; done; }
[ -n "$REF_TXT" ] || { for c in "$DEST/my_voice/ref.txt" "$DEST/test/ref.txt"; do [ -f "$c" ] && REF_TXT="$c" && break; done; }
[ -f "$REF_WAV" ] || { echo "找不到参考音频，请放到 $DEST/my_voice/ref.wav"; exit 1; }
[ -f "$REF_TXT" ] || { echo "找不到参考文本，请放到 $DEST/my_voice/ref.txt"; exit 1; }

# 非 wav 参考音频自动转码（mp3/m4a/aiff/flac 都行）
case "$REF_WAV" in
  *.wav|*.WAV) ;;
  *)
    CONV="$DEST/output/.ref_converted.wav"
    mkdir -p "$(dirname "$CONV")"
    echo "参考音频不是 wav，先用 ffmpeg 转码：$(basename "$REF_WAV") -> $CONV"
    if "$DEST/venv/bin/ffmpeg" -y -loglevel error -i "$REF_WAV" -ac 1 -ar 32000 -c:a pcm_s16le "$CONV"; then
      REF_WAV="$CONV"
    else
      echo "❌ 转码失败，请改用 wav 格式的参考音频"; exit 1
    fi ;;
esac
[ -f "$TXT" ] || { echo "找不到台词文件: $TXT"; exit 1; }

HERE="$(cd "$(dirname "$0")" && pwd)"
PY_SCRIPT="$HERE/tts_clone.py"
[ -f "$PY_SCRIPT" ] || PY_SCRIPT="$DEST/tts_clone.py"

mkdir -p "$OUT"
export PATH="$DEST/venv/bin:$PATH"
export PYTHONPATH="$DEST:$DEST/GPT_SoVITS"
export HF_ENDPOINT="https://hf-mirror.com"
export NLTK_DATA="$DEST/nltk_data"
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export PYTORCH_ENABLE_MPS_FALLBACK=1
export language="zh_CN"
export version="v2Pro"
export gpt_path="$DEST/GPT_weights_v2Pro/laomushi-e20.ckpt"
export sovits_path="$DEST/SoVITS_weights_v2Pro/laomushi_v2_e16.pth"

ARGS=(--out-dir "$OUT" --ref-wav "$REF_WAV" --ref-text-file "$REF_TXT" --ref-lang 中文 --text-lang 中文 --prefix "${PREFIX:-clone}")
if [ "$MODE" = "batch" ]; then
  ARGS+=(--batch-file "$TXT")
else
  ARGS+=(--text-file "$TXT" --variants "${VARIANTS:-2}")
fi

cd "$DEST" || exit 1
exec "$DEST/venv/bin/python" "$PY_SCRIPT" "${ARGS[@]}"
