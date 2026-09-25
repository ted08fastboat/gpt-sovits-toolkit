#!/bin/bash
# 从视频里挑一段干净人声，做成 GPT-SoVITS 的参考音频
# 用法: video_to_ref.sh <视频文件> [目标秒数=6] [输出路径，默认 ~/GPT-SoVITS/参考音频/ref.wav]
set -u
WS="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/GPT-SoVITS"
VID="${1:?用法: video_to_ref.sh <视频文件> [目标秒数] [输出路径]}"
LEN="${2:-6}"
OUT="${3:-$DEST/参考音频/ref.wav}"
TMP="$(mktemp -d)"
mkdir -p "$(dirname "$OUT")"

echo "===== 视频信息 ====="
"$DEST/venv/bin/ffmpeg" -hide_banner -i "$VID" 2>&1 | grep -E "Duration|Stream" | head -6

echo
echo "===== 抽取音轨（32kHz 单声道） ====="
"$DEST/venv/bin/ffmpeg" -y -loglevel error -i "$VID" -vn -ac 1 -ar 32000 -c:a pcm_s16le "$TMP/full.wav" \
  || { echo "❌ 抽取失败"; rm -rf "$TMP"; exit 1; }
"$DEST/venv/bin/python" -c "
import soundfile as sf; d,sr=sf.read('$TMP/full.wav')
print('音轨时长 %.1f 秒，采样率 %d' % (len(d)/sr, sr))"

echo
echo "===== 选段（目标 $LEN 秒） ====="
"$DEST/venv/bin/python" "$WS/scripts/pick_speech.py" "$TMP/full.wav" "$OUT" "$LEN"
rc=$?
rm -rf "$TMP"
exit $rc
