#!/bin/bash
# 用 funasr 识别参考音频的文字，写到同目录 ref.txt
# 用法: asr_ref.sh [参考音频路径] [输出文本路径]
set -u
DEST="$HOME/GPT-SoVITS"
WAV="${1:-$DEST/参考音频/ref.wav}"
OUTTXT="${2:-$(dirname "$WAV")/ref.txt}"
TMP="$(mktemp -d)"
mkdir -p "$TMP/in" "$TMP/out"

# 转 16k 单声道（ASR 标准输入），并用 ASCII 文件名避免路径编码问题
"$DEST/venv/bin/ffmpeg" -y -loglevel error -i "$WAV" -ac 1 -ar 16000 -c:a pcm_s16le "$TMP/in/ref.wav" \
  || { echo "❌ 转码失败"; rm -rf "$TMP"; exit 1; }

echo "===== 正在识别（首次会从 ModelScope 下载模型，约 1GB） ====="
cd "$DEST" || exit 1
env PATH="$DEST/venv/bin:$PATH" HF_ENDPOINT="https://hf-mirror.com" \
  "$DEST/venv/bin/python" tools/asr/funasr_asr.py -i "$TMP/in" -o "$TMP/out" -s large -l zh 2>&1 | tail -8

TXT=$(cat "$TMP/out/ref.txt" 2>/dev/null | tr -d '\r\n')
if [ -z "$TXT" ]; then
  echo "❌ 没拿到识别结果，检查上面的报错"; ls -la "$TMP/out" 2>/dev/null; rm -rf "$TMP"; exit 1
fi
printf '%s' "$TXT" > "$OUTTXT"
echo
echo "识别结果: $TXT"
echo "已写入: $OUTTXT"
rm -rf "$TMP"
