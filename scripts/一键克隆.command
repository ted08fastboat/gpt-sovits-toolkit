#!/bin/bash
# ============================================================
#  GPT-SoVITS 一键克隆 · 老母狮音色
#  双击运行 → 输入台词 → 自动合成 → 自动播放 → 存到「输出音频」
#  也可命令行用: ./一键克隆.command "你的台词"
# ============================================================
set -u
PKG="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/GPT-SoVITS"
OUTDIR="$PKG/输出音频"
mkdir -p "$OUTDIR"

# 参考音频优先级：本包 参考音频/ → ~/GPT-SoVITS/my_voice/ → 内置示例音
REF_WAV=""; REF_TXT=""
for d in "$PKG/参考音频" "$DEST/my_voice" "$DEST/test"; do
  for ext in wav mp3 m4a aiff flac WAV MP3; do
    if [ -f "$d/ref.$ext" ] && [ -f "$d/ref.txt" ]; then
      REF_WAV="$d/ref.$ext"; REF_TXT="$d/ref.txt"; break 2
    fi
  done
done

echo "============================================================"
echo "  GPT-SoVITS 一键克隆 · 老母狮音色"
echo "============================================================"

if [ ! -x "$DEST/say_laomushi.sh" ]; then
  echo "❌ 找不到合成引擎 $DEST/say_laomushi.sh"
  read -r -p "按回车关闭窗口…" _ ; exit 1
fi
if [ -z "$REF_WAV" ]; then
  echo "⚠️  没找到参考音频。请准备 3~10 秒干净人声："
  echo "    音频 → $PKG/参考音频/ref.wav"
  echo "    文字 → $PKG/参考音频/ref.txt（这段音频的准确文字）"
  echo "    （用老母狮本人的声音，效果最好）"
  read -r -p "按回车关闭窗口…" _ ; exit 1
fi
echo "参考音频: $REF_WAV"
echo "音色权重: laomushi-e20.ckpt + laomushi_v2_e16.pth (v2Pro)"
echo "输出目录: $OUTDIR"

TEXT="${1:-}"
if [ -z "$TEXT" ]; then
  echo
  echo "请输入要合成的台词，回车开始："
  printf '> '
  read -r TEXT
fi
if [ -z "$TEXT" ]; then
  echo "没有输入台词，退出。"
  read -r -p "按回车关闭窗口…" _ ; exit 1
fi

SAFE=$(printf '%s' "$TEXT" | /usr/bin/python3 -c "import re,sys; s=re.sub(r'[^\w\u4e00-\u9fff]','',sys.stdin.read()); print(s[:12])" 2>/dev/null)
[ -n "$SAFE" ] || SAFE="clone"
TMP="$PKG/.line.txt"
printf '%s' "$TEXT" > "$TMP"
touch "$PKG/.start_mark"

echo
echo "台词: $TEXT"
echo "正在合成…（CPU 推理，短句约 40 秒，长句更久，请稍候）
（默认只输出「默认」版本；想出多变体：VARIANTS=3 ./一键克隆.command \"台词\"）"
echo
PREFIX="$SAFE" VARIANTS="${VARIANTS:-1}" "$DEST/say_laomushi.sh" "$TMP" "$OUTDIR" "$REF_WAV" "$REF_TXT"
RC=$?
rm -f "$TMP"
NEW=$(find "$OUTDIR" -name '*.wav' -newer "$PKG/.start_mark" 2>/dev/null | wc -l | tr -d ' ')
rm -f "$PKG/.start_mark"
if [ "$NEW" -eq 0 ]; then
  echo
  echo "❌ 没有生成音频（引擎退出码 $RC），请把上面的报错发我。"
  read -r -p "按回车关闭窗口…" _ ; exit 1
fi
[ "$RC" -eq 0 ] || echo "（提示：引擎退出码 $RC，但音频已正常生成，可忽略）"

echo
echo "✅ 完成，音频在：$OUTDIR"
ls -1t "$OUTDIR"/*.wav 2>/dev/null | head -4 | while read -r f; do echo "   • $(basename "$f")"; done

PLAY=$(ls -1t "$OUTDIR"/"$SAFE"*v1-默认.wav 2>/dev/null | head -1)
[ -n "$PLAY" ] || PLAY=$(ls -1t "$OUTDIR"/*.wav 2>/dev/null | head -1)
if [ -n "$PLAY" ] && [ "${NOPLAY:-0}" != "1" ]; then
  echo
  echo "▶ 播放: $(basename "$PLAY")"
  afplay "$PLAY"
fi
[ "${NOPLAY:-0}" = "1" ] || open "$OUTDIR" 2>/dev/null
echo
read -r -p "按回车关闭窗口…" _
