#!/usr/bin/env python3
"""用 macOS 内置语音生成候选参考音频（正确解析 say -v ? 的语音名与语种列）。"""
import os
import re
import subprocess
import sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(WS, "test", "voices")
FFMPEG = os.path.join(WS, "venv", "bin", "ffmpeg")
TEXT = "各位听众朋友大家好，欢迎收听今天的科技新闻节目。"
WANT = sys.argv[1:] or ["zh_CN", "zh_TW", "zh_HK"]

os.makedirs(OUT, exist_ok=True)
raw = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout

cands, seen = [], set()
for line in raw.splitlines():
    m = re.match(r"^(.*?)\s+(zh_(?:CN|TW|HK))\b", line)
    if not m:
        continue
    name, loc = m.group(1).strip(), m.group(2)
    if loc not in WANT or name in seen:
        continue
    seen.add(name)
    cands.append((name, loc))

print("解析到 %d 个候选语音" % len(cands))
for name, loc in cands:
    safe = re.sub(r"[^\w\u4e00-\u9fff]+", "_", name).strip("_")[:30] or loc
    aiff = os.path.join(OUT, "%s.aiff" % safe)
    wav = os.path.join(OUT, "%s.wav" % safe)
    r = subprocess.run(["say", "-v", name, "-o", aiff, TEXT], capture_output=True)
    if r.returncode != 0 or not os.path.exists(aiff):
        print("FAIL  %-26s %-6s %s" % (name, loc, (r.stderr.decode(errors="ignore") or "").strip()[:60]))
        continue
    r2 = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", aiff,
                         "-ac", "1", "-ar", "32000", "-c:a", "pcm_s16le", wav], capture_output=True)
    if r2.returncode != 0 or not os.path.exists(wav):
        print("FAIL(转码) %-22s %s" % (name, r2.stderr.decode(errors="ignore")[:60]))
        continue
    dur = os.path.getsize(wav) / (32000 * 2)
    print("OK    %-26s %-6s %5.2fs  %s" % (name, loc, dur, os.path.basename(wav)))
    os.remove(aiff)
