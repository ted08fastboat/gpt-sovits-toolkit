#!/bin/bash
# ============================================================
#  GPT-SoVITS 批量克隆 · 老母狮音色
#  读同目录下的「台词.txt」，一行一句，整批只加载一次模型
#  结果存到「输出音频/batch_001.wav, batch_002.wav …」
# ============================================================
set -u
PKG="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/GPT-SoVITS"
OUTDIR="$PKG/输出音频"
LINES="$PKG/台词.txt"
mkdir -p "$OUTDIR"

echo "============================================================"
echo "  GPT-SoVITS 批量克隆 · 老母狮音色"
echo "============================================================"

if [ ! -f "$LINES" ]; then
  printf '%s\n' "# 一行一句，以 # 开头的行会被忽略" "你好，这是第一句。" "这是第二句。" > "$LINES"
  echo "已生成示例台词文件：$LINES"
  echo "请用文本编辑器写好后，再次双击本文件。"
  open -t "$LINES" 2>/dev/null
  read -r -p "按回车关闭窗口…" _ ; exit 0
fi

REF_WAV=""; REF_TXT=""
for d in "$PKG/参考音频" "$DEST/my_voice" "$DEST/test"; do
  for ext in wav mp3 m4a aiff flac WAV MP3; do
    if [ -f "$d/ref.$ext" ] && [ -f "$d/ref.txt" ]; then
      REF_WAV="$d/ref.$ext"; REF_TXT="$d/ref.txt"; break 2
    fi
  done
done
if [ -z "$REF_WAV" ]; then
  echo "⚠️  没找到参考音频：请放 $PKG/参考音频/ref.wav 和 ref.txt"
  read -r -p "按回车关闭窗口…" _ ; exit 1
fi

echo "台词文件: $LINES"
n=$(grep -cvE '^\s*(#|$)' "$LINES" || true)
echo "参考音频: $REF_WAV"
echo "待合成句数: $n"
echo "输出目录: $OUTDIR"
echo
echo "开始合成…（每句约 20~40 秒，CPU 推理）"
echo

touch "$PKG/.start_mark"
PREFIX="${PREFIX:-batch}" "$DEST/say_laomushi.sh" --batch "$LINES" "$OUTDIR" "$REF_WAV" "$REF_TXT"
RC=$?
NEW=$(find "$OUTDIR" -name '*.wav' -newer "$PKG/.start_mark" 2>/dev/null | wc -l | tr -d ' ')
rm -f "$PKG/.start_mark"
if [ "$NEW" -eq 0 ]; then
  echo
  echo "❌ 没有生成音频（引擎退出码 $RC），请把上面的报错发我。"
  read -r -p "按回车关闭窗口…" _ ; exit 1
fi
[ "$RC" -eq 0 ] || echo "（提示：引擎退出码 $RC，但音频已正常生成，可忽略。已生成 $((AFTER-BEFORE)) 个）"

echo
echo "✅ 全部完成，音频在：$OUTDIR"
[ "${NOPLAY:-0}" = "1" ] || open "$OUTDIR" 2>/dev/null
echo
read -r -p "按回车关闭窗口…" _
