#!/bin/bash
# 用「示例音色」微调权重做克隆合成（合成引擎，被桌面快捷方式调用）
# 用法:
#   say.sh <台词文本文件> [输出目录] [参考音频] [参考文本文件]
#   say.sh --batch <台词文件(每行一句)> [输出目录] [参考音频] [参考文本文件]
# 环境变量:
#   PREFIX   输出文件名前缀（默认 clone）
#   VARIANTS 变体数量，仅单条模式（默认 2；批量模式固定 1）
set -u
DEST="$HOME/GPT-SoVITS"
MODE="single"
if [ "${1:-}" = "--batch" ]; then MODE="batch"; shift; fi
TXT="${1:?用法: say.sh [--batch] <台词文本文件> [输出目录] [参考音频] [参考文本文件]}"
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
# 自动发现权重：按 v2ProPlus → v2Pro → v4 → v3 → v2 → v1 的顺序找第一个可用的
# 也可以用环境变量 gpt_path / sovits_path / version 手动指定
find_weight() {   # $1=扩展名 ckpt|pth
  for d in GPT_weights_v2ProPlus SoVITS_weights_v2ProPlus GPT_weights_v2Pro SoVITS_weights_v2Pro \
           GPT_weights_v4 SoVITS_weights_v4 GPT_weights_v3 SoVITS_weights_v3 \
           GPT_weights_v2 SoVITS_weights_v2 GPT_weights SoVITS_weights; do
    case "$d" in *SoVITS*) [ "$1" = "pth" ] || continue ;; *) [ "$1" = "ckpt" ] || continue ;; esac
    [ -d "$DEST/$d" ] || continue
    f="$(ls -1 "$DEST/$d"/*.$1 2>/dev/null | head -1)"
    [ -n "$f" ] && { echo "$f"; return 0; }
  done
  return 1
}
if [ -z "${gpt_path:-}" ]; then
  gpt_path="$(find_weight ckpt)" || { echo "❌ 没找到 GPT 权重（放在 \$DEST/GPT_weights_v2Pro 等目录下）"; exit 1; }
fi
if [ -z "${sovits_path:-}" ]; then
  sovits_path="$(find_weight pth)" || { echo "❌ 没找到 SoVITS 权重（放在 \$DEST/SoVITS_weights_v2Pro 等目录下）"; exit 1; }
fi
if [ -z "${version:-}" ]; then
  case "$(dirname "$sovits_path")" in
    *v2ProPlus*) version="v2ProPlus" ;;
    *v2Pro*)     version="v2Pro" ;;
    *v4*)        version="v4" ;;
    *v3*)        version="v3" ;;
    *v2*)        version="v2" ;;
    *)           version="v1" ;;
  esac
fi
export version gpt_path sovits_path
echo "权重: $(basename "$gpt_path") + $(basename "$sovits_path")  (version=$version)"

ARGS=(--out-dir "$OUT" --ref-wav "$REF_WAV" --ref-text-file "$REF_TXT" --ref-lang 中文 --text-lang 中文 --prefix "${PREFIX:-clone}")
if [ "$MODE" = "batch" ]; then
  ARGS+=(--batch-file "$TXT")
else
  ARGS+=(--text-file "$TXT" --variants "${VARIANTS:-2}")
fi

cd "$DEST" || exit 1
exec "$DEST/venv/bin/python" "$PY_SCRIPT" "${ARGS[@]}"
